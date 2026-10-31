"""End-to-end tests for the Studio `StateGraph` and FastAPI SSE endpoints (zero external services)."""

import json
from typing import Any

from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
import pytest

from rift.adapters.memory import FakeSandboxProvider, InMemoryStorageProvider
from rift.api.builds import create_app
from rift.core.domain.gdd import (
    AcceptanceCriterion,
    FilePlanItem,
    GameBrief,
    GameDesignDoc,
    Question,
    ReviewIssue,
    ReviewVerdict,
)
from rift.core.ports.sandbox import ExecResult
from rift.core.studio.graph import build_studio_graph
from rift.core.studio.nodes import AgentFactories
from rift.core.studio.sandbox_lifecycle import WORKSPACE


def _usage(total: int) -> dict[str, int]:
    return {"input_tokens": total // 2, "output_tokens": total - total // 2, "total_tokens": total}


def _sample_brief(genre: str = "Shooter") -> GameBrief:
    return GameBrief(
        title="Neon Drift",
        genre=genre,
        elevator_pitch="Dodge and blast glowing drifters in a neon arena.",
        core_loop="Move with WASD/arrows, fire with Space, survive escalating waves.",
        controls=["WASD / Arrows: move", "Space: shoot", "P: pause", "R: restart"],
        win_condition="Endless — beat your high score",
        lose_condition="Lose all 3 lives",
        art_style="Neon synthwave vector shapes",
        session_length_minutes=3,
        assumptions=["3 lives with 1.2s invulnerability"],
        out_of_scope=["Online leaderboard — no backend"],
    )


def _sample_gdd() -> GameDesignDoc:
    return GameDesignDoc(
        title="Neon Drift",
        mechanics=[
            "Movement: 280 px/s clamped to 960x540",
            "Shooting: 1 bullet every 160 ms at 620 px/s",
        ],
        entities=[
            "Player ship — 32px cyan triangle, 3 lives",
            "Drifter — 30px magenta diamond, 90 px/s down, 100 pts",
        ],
        levels_or_waves=["Every 20s spawn interval *= 0.9 (floor 350ms)"],
        hud_and_menus=["Top-left: Score", "Top-right: Lives", "R to restart"],
        palette_hex=["#0b1021", "#00e5ff", "#ff2bd6", "#ffffff"],
        file_plan=[
            FilePlanItem(path="src/main.ts", purpose="Game boot + window.__RIFT__"),
            FilePlanItem(path="src/config.ts", purpose="All tuning numbers"),
            FilePlanItem(path="src/scenes/GameScene.ts", purpose="Main gameplay"),
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC1",
                description="Game boots with zero console errors and ready=true",
                check="runtime",
            ),
            AcceptanceCriterion(
                id="AC2",
                description="Pressing ArrowRight increases playerX",
                check="runtime",
            ),
            AcceptanceCriterion(
                id="AC3",
                description="Destroying a Drifter increases score by 100",
                check="runtime",
            ),
        ],
    )


class ScriptedPlanAgent:
    def __init__(self, *, ask_once: bool = True) -> None:
        self.ask_once = ask_once

    async def ainvoke(self, inp: dict[str, Any], config: Any = None) -> dict[str, Any]:
        genre = "Shooter"
        if self.ask_once:
            answers = interrupt(
                {
                    "type": "clarification",
                    "questions": [
                        Question(
                            id="genre",
                            question="Which genre do you want?",
                            options=["Shooter", "Platformer", "Puzzle"],
                        ).model_dump()
                    ],
                }
            )
            genre = answers.get("genre", "Shooter")
        return {
            "structured_response": _sample_brief(genre),
            "messages": [AIMessage(content="Brief ready", usage_metadata=_usage(120))],
        }


class ScriptedDesignAgent:
    async def ainvoke(self, inp: dict[str, Any], config: Any = None) -> dict[str, Any]:
        return {
            "structured_response": _sample_gdd(),
            "messages": [AIMessage(content="GDD ready", usage_metadata=_usage(200))],
        }


class ScriptedCoderAgent:
    """Writes `dist/index.html` and screenshots into the fake sandbox."""

    def __init__(self, sandbox: FakeSandboxProvider, sandbox_id: str) -> None:
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id

    async def ainvoke(self, inp: dict[str, Any], config: Any = None) -> dict[str, Any]:
        html = (
            "<!doctype html><html><body><canvas></canvas>"
            "<script>window.__RIFT__={ready:true,state:()=>({score:100}),errors:[]};</script>"
            + ("<!-- pad -->" * 20)
            + "</body></html>"
        ).encode("utf-8")
        await self.sandbox.write_file(
            self.sandbox_id, html, f"{WORKSPACE}/dist/index.html"
        )
        await self.sandbox.write_file(
            self.sandbox_id, b"\x89PNG\r\n\x1a\nfake", f"{WORKSPACE}/screenshot_t0.png"
        )
        return {
            "messages": [
                AIMessage(
                    content="BUILD: pass\nFILES: src/scenes/GameScene.ts\nDONE: implemented game",
                    usage_metadata=_usage(500),
                )
            ]
        }


class ScriptedReviewAgent:
    def __init__(self, verdicts: list[ReviewVerdict]) -> None:
        self._verdicts = list(verdicts)
        self.calls = 0

    async def ainvoke(self, inp: dict[str, Any], config: Any = None) -> dict[str, Any]:
        idx = min(self.calls, len(self._verdicts) - 1)
        self.calls += 1
        return {
            "structured_response": self._verdicts[idx],
            "messages": [AIMessage(content="Reviewed", usage_metadata=_usage(150))],
        }


def _make_exec_hook(*, fail_first_tsc: bool = False, always_fail_tsc: bool = False):
    tsc_calls = {"n": 0}

    def hook(sandbox_id: str, cmd: list[str]) -> ExecResult | None:
        joined = " ".join(cmd)
        if "tsc --noEmit" in joined:
            tsc_calls["n"] += 1
            if always_fail_tsc or (fail_first_tsc and tsc_calls["n"] == 1):
                return ExecResult(
                    stdout="",
                    stderr="src/scenes/GameScene.ts(12,5): error TS2322: Type 'string' is not assignable to type 'number'.",
                    exit_code=2,
                )
            return ExecResult(stdout="", stderr="", exit_code=0)
        if "pnpm build" in joined:
            return ExecResult(stdout="built in 1.0s", stderr="", exit_code=0)
        if "verify_game.py" in joined:
            verdict = {
                "passed": True,
                "boots": True,
                "canvas_present": True,
                "interactive": True,
                "errors": [],
                "screenshots": [f"{WORKSPACE}/screenshot_t0.png"],
                "state_t0": {"score": 0},
                "state_t1": {"score": 100},
            }
            return ExecResult(stdout=json.dumps(verdict), stderr="", exit_code=0)
        return None

    return hook


@pytest.mark.asyncio
async def test_full_studio_graph_hitl_verify_retry_and_reviewer_loop() -> None:
    sandbox = FakeSandboxProvider(exec_hook=_make_exec_hook(fail_first_tsc=True))
    storage = InMemoryStorageProvider()
    reviewer = ScriptedReviewAgent(
        [
            ReviewVerdict(
                approved=False,
                summary="AC3 fails: score does not increase on Drifter kill.",
                issues=[
                    ReviewIssue(
                        severity="major",
                        criterion_id="AC3",
                        file="src/scenes/GameScene.ts",
                        problem="onHit destroys enemy without adding score",
                        fix_instruction="Add 100 to this.score and update bridge.set({score})",
                    )
                ],
            ),
            ReviewVerdict(
                approved=True,
                summary="All acceptance criteria (AC1-AC3) pass.",
                issues=[],
            ),
        ]
    )
    agents = AgentFactories(
        plan=lambda: ScriptedPlanAgent(ask_once=True),
        design=ScriptedDesignAgent,
        code=lambda sid: ScriptedCoderAgent(sandbox, sid),
        review=lambda sid: reviewer,
    )
    graph = build_studio_graph(
        sandbox=sandbox,
        storage=storage,
        agents=agents,
        checkpointer=InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "bld_e2e_1"}}
    initial = {
        "org_id": "org_1",
        "project_id": "proj_1",
        "build_id": "bld_e2e_1",
        "prompt": "make me a space game",
        "round": 0,
        "max_rounds": 4,
        "tokens_used": 0,
        "token_budget": 250_000,
    }

    try:
        # Phase A: runs planner and pauses on `ask_user` interrupt BEFORE creating any sandbox
        paused = await graph.ainvoke(initial, cfg)
        assert "__interrupt__" in paused
        assert paused["__interrupt__"][0].value["type"] == "clarification"
        assert sandbox.created == []  # zero sandbox cost while waiting for the human!

        # Phase B: resume with human's answer -> designer -> provision ->
        # Round 1 (verify fails -> coder) -> Round 2 (verify passes -> reviewer requests change -> coder) ->
        # Round 3 (verify passes -> reviewer approves -> publish -> cleanup)
        final = await graph.ainvoke(Command(resume={"genre": "Arcade Shooter"}), cfg)

        assert final["status"] == "published"
        assert final["brief"]["genre"] == "Arcade Shooter"
        assert final["round"] == 3
        assert reviewer.calls == 2  # skipped on round 1 when verify failed!
        assert len(final["review_history"]) == 2
        assert final["sandbox_id"] is None  # cleaned up
        assert sandbox.alive == set()
        assert final["artifact_key"] == "builds/bld_e2e_1/index.html"
        assert final["published_url"] == "https://cdn.test/builds/bld_e2e_1/index.html"
        assert "builds/bld_e2e_1/index.html" in storage.objects
        assert "builds/bld_e2e_1/screenshot_t0.png" in storage.objects
        assert "builds/bld_e2e_1/source.tgz" in storage.objects
        assert final["tokens_used"] > 0
    finally:
        sandbox.cleanup()


@pytest.mark.asyncio
async def test_verify_failure_exhausts_rounds_and_cleans_up() -> None:
    sandbox = FakeSandboxProvider(exec_hook=_make_exec_hook(always_fail_tsc=True))
    storage = InMemoryStorageProvider()
    reviewer = ScriptedReviewAgent(
        [ReviewVerdict(approved=True, summary="Unused", issues=[])]
    )
    agents = AgentFactories(
        plan=lambda: ScriptedPlanAgent(ask_once=False),
        design=ScriptedDesignAgent,
        code=lambda sid: ScriptedCoderAgent(sandbox, sid),
        review=lambda sid: reviewer,
    )
    graph = build_studio_graph(
        sandbox=sandbox,
        storage=storage,
        agents=agents,
        checkpointer=InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "bld_fail_1"}}
    try:
        final = await graph.ainvoke(
            {
                "org_id": "org_1",
                "project_id": "proj_1",
                "build_id": "bld_fail_1",
                "prompt": "make a shooter",
                "round": 0,
                "max_rounds": 2,
                "tokens_used": 0,
                "token_budget": 250_000,
            },
            cfg,
        )
        assert final["status"] == "failed"
        assert final["round"] == 2
        assert reviewer.calls == 0
        assert final["sandbox_id"] is None
        assert sandbox.alive == set()
        assert "automated checks still failing" in (final.get("error") or "")
    finally:
        sandbox.cleanup()


@pytest.mark.asyncio
async def test_fastapi_sse_start_pending_and_answer_flow() -> None:
    sandbox = FakeSandboxProvider(exec_hook=_make_exec_hook(fail_first_tsc=False))
    storage = InMemoryStorageProvider()
    reviewer = ScriptedReviewAgent(
        [ReviewVerdict(approved=True, summary="All good.", issues=[])]
    )
    agents = AgentFactories(
        plan=lambda: ScriptedPlanAgent(ask_once=True),
        design=ScriptedDesignAgent,
        code=lambda sid: ScriptedCoderAgent(sandbox, sid),
        review=lambda sid: reviewer,
    )
    graph = build_studio_graph(
        sandbox=sandbox,
        storage=storage,
        agents=agents,
        checkpointer=InMemorySaver(),
    )
    app = create_app(graph=graph)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Start build -> streams until interrupt
            resp1 = await client.post(
                "/builds",
                json={
                    "org_id": "org_1",
                    "project_id": "proj_1",
                    "build_id": "bld_api_1",
                    "prompt": "make a game",
                },
            )
            assert resp1.status_code == 200
            assert "event: interrupt" in resp1.text

            # 2. Check /pending while paused
            pending = (await client.get("/builds/bld_api_1/pending")).json()
            assert pending["awaiting_input"] is True
            assert pending["interrupts"][0]["questions"][0]["id"] == "genre"

            # 3. Submit answers -> finishes and publishes
            resp2 = await client.post(
                "/builds/bld_api_1/answers",
                json={"answers": {"genre": "Puzzle"}},
            )
            assert resp2.status_code == 200
            assert "event: done" in resp2.text
            assert "https://cdn.test/builds/bld_api_1/index.html" in resp2.text
    finally:
        sandbox.cleanup()
