"""FastAPI entrypoint & SSE streaming for Rift builds (the composition root)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
from typing import Any
import uuid

from fastapi import APIRouter, FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from rift.adapters.daytona import DaytonaSandboxProvider
from rift.adapters.memory import FakeSandboxProvider, InMemoryStorageProvider
from rift.adapters.r2 import R2StorageProvider
from rift.config import get_settings
from rift.core.agents import default_agent_factories
from rift.core.studio.graph import build_studio_graph
from rift.core.studio.nodes import AgentFactories
from rift.core.studio.state import StudioState
from rift.memory.checkpointer import open_checkpointer

router = APIRouter(prefix="/builds", tags=["builds"])


class StartBuildRequest(BaseModel):
    org_id: str = "org_default"
    project_id: str
    prompt: str = Field(min_length=2)
    build_id: str | None = None
    parent_build_id: str | None = None
    source_key: str | None = None
    gdd: dict[str, Any] | None = None
    brief: dict[str, Any] | None = None


class AnswerQuestionsRequest(BaseModel):
    answers: dict[str, str]


def thread_config(build_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": build_id}, "recursion_limit": 100}


async def stream_graph_events(
    graph: Any, build_id: str, graph_input: Any
) -> AsyncIterator[dict[str, str]]:
    """Drive `graph.astream(...)` and yield SSE event dicts for both start and resume."""
    cfg = thread_config(build_id)
    async for mode, chunk in graph.astream(
        graph_input,
        cfg,
        stream_mode=["updates", "custom"],
        durability="sync",
    ):
        if mode == "custom":
            yield {"event": "progress", "data": json.dumps(chunk)}
        elif isinstance(chunk, dict) and "__interrupt__" in chunk:
            intr = chunk["__interrupt__"][0]
            payload = intr.value if isinstance(intr.value, dict) else {"value": intr.value}
            yield {
                "event": "interrupt",
                "data": json.dumps({"id": getattr(intr, "id", None), **payload}),
            }
            return
        elif isinstance(chunk, dict):
            for node_name, update in chunk.items():
                keys = list(update.keys()) if isinstance(update, dict) else []
                status = update.get("status") if isinstance(update, dict) else None
                yield {
                    "event": "node",
                    "data": json.dumps(
                        {"node": node_name, "keys": keys, "status": status}
                    ),
                }

    snapshot = await graph.aget_state(cfg)
    final = snapshot.values if snapshot else {}
    yield {
        "event": "done",
        "data": json.dumps(
            {
                "build_id": build_id,
                "status": final.get("status"),
                "published_url": final.get("published_url"),
                "artifact_key": final.get("artifact_key"),
                "error": final.get("error"),
            }
        ),
    }


@router.post("")
async def start_build(body: StartBuildRequest, request: Request) -> EventSourceResponse:
    s = get_settings()
    build_id = body.build_id or f"bld_{uuid.uuid4().hex[:12]}"
    initial: StudioState = {
        "org_id": body.org_id,
        "project_id": body.project_id,
        "build_id": build_id,
        "parent_build_id": body.parent_build_id,
        "prompt": body.prompt,
        "status": "planning",
        "round": 0,
        "max_rounds": s.max_attempts,
        "tokens_used": 0,
        "token_budget": s.token_budget,
        "messages": [{"role": "user", "content": body.prompt}],
    }
    if body.source_key:
        initial["source_key"] = body.source_key
    if body.gdd:
        initial["gdd"] = body.gdd
    if body.brief:
        initial["brief"] = body.brief

    graph = request.app.state.graph
    return EventSourceResponse(stream_graph_events(graph, build_id, initial))


@router.post("/{build_id}/answers")
async def answer_questions(
    build_id: str, body: AnswerQuestionsRequest, request: Request
) -> EventSourceResponse:
    graph = request.app.state.graph
    st = await graph.aget_state(thread_config(build_id))
    if not st or not st.next or not any(t.interrupts for t in st.tasks):
        raise HTTPException(
            status_code=409, detail="Build is not awaiting human clarification"
        )
    return EventSourceResponse(
        stream_graph_events(graph, build_id, Command(resume=body.answers))
    )


@router.get("/{build_id}/pending")
async def get_pending(build_id: str, request: Request) -> dict[str, Any]:
    graph = request.app.state.graph
    st = await graph.aget_state(thread_config(build_id))
    if not st or not st.values:
        raise HTTPException(status_code=404, detail="Build thread not found")
    interrupts = [i.value for t in st.tasks for i in t.interrupts]
    return {
        "build_id": build_id,
        "awaiting_input": bool(interrupts),
        "interrupts": interrupts,
        "next": list(st.next),
        "status": st.values.get("status"),
        "published_url": st.values.get("published_url"),
    }


def create_app(
    *,
    graph: Any | None = None,
    use_in_memory: bool = False,
    agents: AgentFactories | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Pass `graph=...` or `use_in_memory=True` in tests to run without external services.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if graph is not None:
            app.state.graph = graph
            yield
            return
        if use_in_memory:
            sandbox = FakeSandboxProvider()
            storage = InMemoryStorageProvider()
            app.state.graph = build_studio_graph(
                sandbox=sandbox,
                storage=storage,
                agents=agents or default_agent_factories(sandbox),
                checkpointer=InMemorySaver(),
            )
            try:
                yield
            finally:
                sandbox.cleanup()
            return

        s = get_settings()
        sandbox = DaytonaSandboxProvider.from_settings(s)
        storage = R2StorageProvider.from_settings(s)
        async with open_checkpointer(s.database_url) as saver:
            app.state.graph = build_studio_graph(
                sandbox=sandbox,
                storage=storage,
                agents=agents or default_agent_factories(sandbox),
                checkpointer=saver,
            )
            try:
                yield
            finally:
                await sandbox.aclose()

    app = FastAPI(title="Rift Studio API", lifespan=lifespan)
    if graph is not None:
        app.state.graph = graph
    app.include_router(router)
    return app
