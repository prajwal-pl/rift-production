import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import add_messages
from langgraph.graph.message import AnyMessage

StudioStatus = Literal[
    "queued",
    "planning",
    "awaiting_input",
    "designing",
    "building",
    "verifying",
    "reviewing",
    "published",
    "failed",
    "budget_exceeded",
]

TERMINAL_STATUSES: frozenset[str] = frozenset({"published", "failed", "budget_exceeded"})


class StudioState(TypedDict, total=False):
    # ── identity / tenancy ────────────────────────────────────────────
    org_id: str
    project_id: str
    build_id: str  # also the LangGraph thread_id
    parent_build_id: str | None  # set for refinement builds

    # ── LAYER 1: shared conversation / hand-off log ───────────────────
    prompt: str
    messages: Annotated[list[AnyMessage], add_messages]

    # ── LAYER 2: structured artifacts passed between agents ───────────
    brief: dict[str, Any]  # GameBrief (planner -> designer)
    gdd: dict[str, Any]  # GameDesignDoc (designer -> coder, reviewer)
    verify_report: dict[str, Any] | None  # deterministic facts (verify -> coder/reviewer)
    review: dict[str, Any] | None  # latest ReviewVerdict (reviewer -> coder)
    review_history: Annotated[list[dict[str, Any]], operator.add]  # append-only
    coder_summary: str | None  # what the coder did last round

    # ── LAYER 3: environment pointers (NOT file contents) ─────────────
    sandbox_id: str | None
    source_key: str | None  # R2 key of the latest source tarball
    files: dict[str, str]  # manifest: path -> sha256
    artifact_key: str | None  # R2 key of the published index.html
    published_url: str | None

    # ── control & budgets ─────────────────────────────────────────────
    round: int  # number of coder runs so far
    max_rounds: int
    tokens_used: Annotated[int, operator.add]  # nodes return DELTAS
    token_budget: int
    status: StudioStatus
    error: str | None
