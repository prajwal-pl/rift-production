"""Studio `StateGraph` nodes and prompt-view builders for each agent."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.types import Command

from rift.core.domain.gdd import ReviewVerdict
from rift.core.ports.sandbox import SandboxProvider
from rift.core.ports.storage import StorageProvider
from rift.core.studio.routing import decide_after_review
from rift.core.studio.sandbox_lifecycle import (
    WORKSPACE,
    ensure_sandbox,
    snapshot_source,
    teardown,
)
from rift.core.studio.state import StudioState
from rift.verify.runner import run_build, run_verify


@dataclass(frozen=True)
class AgentFactories:
    plan: Callable[[], Any]  # () -> compiled agent
    design: Callable[[], Any]  # () -> compiled agent
    code: Callable[[str], Any]  # sandbox_id -> compiled agent (may block if using sync SDK)
    review: Callable[[str], Any]  # sandbox_id -> compiled agent


def _text(msg: AnyMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "") for block in content if isinstance(block, dict)
    )


def _tokens(messages: list[AnyMessage]) -> int:
    """Sum `total_tokens` across `usage_metadata` on returned `AIMessage`s."""
    return sum(
        (getattr(m, "usage_metadata", None) or {}).get("total_tokens", 0)
        for m in messages
    )


def _note(agent: str, text: str) -> AIMessage:
    return AIMessage(content=text, name=agent)


class StudioNodes:
    def __init__(
        self,
        *,
        sandbox: SandboxProvider,
        storage: StorageProvider,
        agents: AgentFactories,
    ) -> None:
        self.sandbox = sandbox
        self.storage = storage
        self.agents = agents

    # ── 1. PLANNER (agent + HITL `ask_user`) ──────────────────────────────
    async def planner(self, state: StudioState) -> dict[str, Any]:
        # No side effects above `ainvoke`: this node re-executes from line 1 on HITL resume.
        agent = self.agents.plan()
        result = await agent.ainvoke(
            {"messages": [HumanMessage(state["prompt"])]},
            config={"recursion_limit": 40},
        )
        brief = result["structured_response"]  # GameBrief
        assumptions = "; ".join(brief.assumptions) or "none"
        return {
            "brief": brief.model_dump(),
            "status": "designing",
            "messages": [
                _note(
                    "planner",
                    f"Brief ready: \"{brief.title}\" ({brief.genre}). Assumptions: {assumptions}",
                )
            ],
            "tokens_used": _tokens(result.get("messages", [])),
        }

    # ── 2. DESIGNER (agent -> GameDesignDoc) ──────────────────────────────
    async def designer(self, state: StudioState) -> dict[str, Any]:
        task = (
            f"User request:\n{state['prompt']}\n\n"
            f"Approved brief (JSON):\n{json.dumps(state['brief'], indent=2)}"
        )
        agent = self.agents.design()
        result = await agent.ainvoke({"messages": [HumanMessage(task)]})
        gdd = result["structured_response"]  # GameDesignDoc
        return {
            "gdd": gdd.model_dump(),
            "status": "building",
            "messages": [
                _note(
                    "designer",
                    f"GDD ready: {len(gdd.file_plan)} files, "
                    f"{len(gdd.acceptance_criteria)} acceptance criteria.",
                )
            ],
            "tokens_used": _tokens(result.get("messages", [])),
        }

    # ── 3. PROVISION (deterministic sandbox creation + starter seed) ──────
    async def provision(self, state: StudioState) -> dict[str, Any]:
        sid, _ = await ensure_sandbox(self.sandbox, self.storage, state)
        return {"sandbox_id": sid, "status": "building"}

    # ── 4. CODER (Deep Agent bound to the sandbox) ────────────────────────
    async def coder(self, state: StudioState) -> dict[str, Any]:
        sid, _ = await ensure_sandbox(self.sandbox, self.storage, state)
        agent = await asyncio.to_thread(self.agents.code, sid)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(coder_task(state))]},
            config={"recursion_limit": 250},
        )
        msgs = result.get("messages", [])
        summary = _text(msgs[-1]) if msgs else "Completed round."
        key, manifest = await snapshot_source(
            self.sandbox, self.storage, sid, state["build_id"]
        )
        round_num = state.get("round", 0) + 1
        return {
            "sandbox_id": sid,
            "source_key": key,
            "files": manifest,
            "coder_summary": summary,
            "round": round_num,
            "review": None,
            "verify_report": None,
            "status": "verifying",
            "messages": [_note("coder", f"Round {round_num}: {summary[:500]}")],
            "tokens_used": _tokens(msgs),
        }

    # ── 5. VERIFY (deterministic — zero LLM calls) ────────────────────────
    async def verify(self, state: StudioState) -> dict[str, Any]:
        sid, _ = await ensure_sandbox(self.sandbox, self.storage, state)
        report = await run_verify(self.sandbox, sid)
        return {
            "sandbox_id": sid,
            "verify_report": report,
            "status": "reviewing" if report["passed"] else "building",
            "messages": [
                _note(
                    "verify",
                    "PASSED"
                    if report["passed"]
                    else f"FAILED: {len(report['errors'])} error(s)",
                )
            ],
        }

    # ── 6. REVIEWER (read-only agent; returns Command with atomic goto) ───
    async def reviewer(
        self, state: StudioState
    ) -> Command[Literal["coder", "publish", "fail"]]:
        sid, _ = await ensure_sandbox(self.sandbox, self.storage, state)
        agent = self.agents.review(sid)
        result = await agent.ainvoke(
            {"messages": [HumanMessage(review_task(state))]},
            config={"recursion_limit": 40},
        )
        verdict: ReviewVerdict = result["structured_response"]
        msgs = result.get("messages", [])
        tokens = _tokens(msgs)
        budget_view: StudioState = {
            **state,
            "tokens_used": state.get("tokens_used", 0) + tokens,
        }
        goto = decide_after_review(verdict, budget_view)
        prefix = "APPROVED. " if verdict.approved else "CHANGES REQUESTED. "
        return Command(
            goto=goto,
            update={
                "sandbox_id": sid,
                "review": verdict.model_dump(),
                "review_history": [
                    {"round": state.get("round", 0), **verdict.model_dump()}
                ],
                "status": "building" if goto == "coder" else "reviewing",
                "messages": [_note("reviewer", prefix + verdict.summary)],
                "tokens_used": tokens,
            },
        )

    # ── 7a. PUBLISH (deterministic upload to R2) ──────────────────────────
    async def publish(self, state: StudioState) -> dict[str, Any]:
        sid, recreated = await ensure_sandbox(self.sandbox, self.storage, state)
        if recreated:
            await run_build(self.sandbox, sid)
        html = await self.sandbox.read_file(sid, f"{WORKSPACE}/dist/index.html")
        if not 100 < len(html) < 20_000_000:
            raise RuntimeError(f"suspicious index.html size: {len(html)} bytes")
        key = f"builds/{state['build_id']}/index.html"
        await self.storage.upload_file(
            key, html, content_type="text/html; charset=utf-8"
        )
        for shot in (state.get("verify_report") or {}).get("screenshots", []):
            try:
                png = await self.sandbox.read_file(sid, shot)
                shot_name = shot.rsplit("/", 1)[-1]
                await self.storage.upload_file(
                    f"builds/{state['build_id']}/{shot_name}",
                    png,
                    content_type="image/png",
                )
            except FileNotFoundError:
                pass
        url = self.storage.get_public_url(key)
        return {
            "sandbox_id": sid,
            "artifact_key": key,
            "published_url": url,
            "status": "published",
            "messages": [_note("publish", f"Published: {url}")],
        }

    # ── 7b. FAIL (terminal failure summary) ───────────────────────────────
    async def fail(self, state: StudioState) -> dict[str, Any]:
        over_budget = state.get("tokens_used", 0) >= state.get(
            "token_budget", 250_000
        )
        why = failure_reason(state)
        return {
            "status": "budget_exceeded" if over_budget else "failed",
            "error": why,
            "messages": [_note("system", f"Build stopped: {why}")],
        }

    # ── 8. CLEANUP (shared exit for publish AND fail) ─────────────────────
    async def cleanup(self, state: StudioState) -> dict[str, Any]:
        return await teardown(self.sandbox, self.storage, state)


# ── Pure view-builders for agent tasks ────────────────────────────────────────
def coder_task(state: StudioState) -> str:
    parts = [f"## Game Design Document (JSON)\n{json.dumps(state['gdd'], indent=2)}"]
    rnd = state.get("round", 0)
    if rnd == 0 and not state.get("review") and not state.get("verify_report"):
        parts.append(
            "## Task\nImplement the whole game in /workspace following `file_plan`. "
            "Run `pnpm exec tsc --noEmit && pnpm build` and fix all errors before you finish. "
            "Output must be a single-file `dist/index.html` with no external assets or network access."
        )
    else:
        parts.append(
            f"## Task — revision round {rnd + 1}\n"
            "The game already exists in /workspace. Make ONLY the changes listed below, "
            "then run `pnpm exec tsc --noEmit && pnpm build` again. Do not rewrite working code."
        )
        parts.append(
            f"## What you did last round\n{state.get('coder_summary') or '(no summary)'}"
        )
        if vr := state.get("verify_report"):
            if not vr.get("passed", True):
                errs = "\n".join(f"- {e[:1500]}" for e in vr.get("errors", []))
                parts.append(f"## Automated checks FAILED (fix first)\n{errs}")
        if rv := state.get("review"):
            issues = "\n".join(
                f"- [{i['severity']}] {i.get('criterion_id') or ''} {i.get('file') or ''}: "
                f"{i['problem']}\n  -> {i['fix_instruction']}"
                for i in rv.get("issues", [])
            )
            parts.append(f"## Reviewer feedback\n{rv['summary']}\n{issues}")
    return "\n\n".join(parts)


def review_task(state: StudioState) -> str:
    gdd = state["gdd"]
    criteria = "\n".join(
        f"- {c['id']} ({c['check']}): {c['description']}"
        for c in gdd["acceptance_criteria"]
    )
    prior = ""
    if state.get("review_history"):
        last = state["review_history"][-1]
        prior = (
            "\n## Issues you raised last round (verify they are FIXED; do not re-raise fixed ones)\n"
            + "\n".join(
                f"- [{i['severity']}] {i['problem']}" for i in last.get("issues", [])
            )
        )
    return (
        f"## Acceptance criteria\n{criteria}\n\n"
        f"## Automated verification (already PASSED)\n{json.dumps(state.get('verify_report'), indent=2)}\n\n"
        f"## Coder's summary of this round\n{state.get('coder_summary')}\n{prior}\n\n"
        "Inspect the code with your tools, then return your verdict."
    )


def failure_reason(state: StudioState) -> str:
    if vr := state.get("verify_report"):
        if not vr.get("passed"):
            return "automated checks still failing: " + "; ".join(
                e[:200] for e in vr.get("errors", [])[:3]
            )
    if rv := state.get("review"):
        blockers = [
            i["problem"]
            for i in rv.get("issues", [])
            if i.get("severity") == "blocker"
        ]
        if blockers:
            return "unresolved blockers: " + "; ".join(blockers[:3])
    return "round or token budget exhausted"
