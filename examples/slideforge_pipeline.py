"""SlideForge: tiny runnable version of the Rift pipeline pattern (no LLMs)."""
import asyncio
import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

# ── fake "environment" and "storage" (stand-ins for Daytona / R2) ──────────────────────────────
WORKSPACES: dict[str, dict[str, str]] = {}   # workspace_id -> {path: content}
STORAGE: dict[str, str] = {}                 # key -> content


class DeckState(TypedDict, total=False):
    deck_id: str
    topic: str
    audience: str
    outline: list[str]
    workspace_id: str | None
    source_key: str | None
    check: dict[str, Any] | None
    critique: dict[str, Any] | None
    round: int
    max_rounds: int
    log: Annotated[list[str], operator.add]
    status: str
    url: str | None


def ensure_workspace(state: DeckState) -> str:
    wid = state.get("workspace_id")
    if wid and wid in WORKSPACES:
        return wid
    wid = f"ws_{len(WORKSPACES) + 1}"
    WORKSPACES[wid] = {}
    if key := state.get("source_key"):
        WORKSPACES[wid]["slides.md"] = STORAGE[key]          # restore
    return wid


# ── nodes ────────────────────────────────────────────────────────────────────────────────────
def interviewer(state: DeckState) -> dict:
    answers = interrupt({"questions": [{"id": "audience", "question": "Who is the audience?",
                                        "options": ["Execs", "Engineers", "Students"]}]})
    return {"audience": answers["audience"], "log": [f"interviewer: audience={answers['audience']}"]}


def outliner(state: DeckState) -> dict:
    return {"outline": [f"{state['topic']} – part {i}" for i in range(1, 6)],
            "log": ["outliner: 5-point outline"]}


def provision(state: DeckState) -> dict:
    return {"workspace_id": ensure_workspace(state), "status": "building"}


def writer(state: DeckState) -> dict:
    wid = ensure_workspace(state)
    n = 2 + 2 * state.get("round", 0)                       # round0=2, round1=4, round2=6 slides
    slides = [f"# {s}" for s in state["outline"][:n]] + [f"# Extra {i}" for i in range(max(0, n - 5))]
    if state.get("round", 0) == 0:
        slides[0] += "\nTODO write this"
    WORKSPACES[wid]["slides.md"] = "\n---\n".join(slides)
    key = f"decks/{state['deck_id']}/source.md"
    STORAGE[key] = WORKSPACES[wid]["slides.md"]
    return {"workspace_id": wid, "source_key": key, "round": state.get("round", 0) + 1,
            "check": None, "critique": None, "log": [f"writer: round {state.get('round', 0) + 1}, {n} slides"]}


def check(state: DeckState) -> dict:
    text = WORKSPACES[state["workspace_id"]]["slides.md"]
    errors = ["found TODO"] if "TODO" in text else []
    return {"check": {"passed": not errors, "errors": errors}, "log": [f"check: {errors or 'ok'}"]}


def exhausted(state: DeckState) -> bool:
    return state.get("round", 0) >= state.get("max_rounds", 4)


def route_after_check(state: DeckState) -> Literal["critic", "writer", "fail"]:
    if state["check"]["passed"]:
        return "critic"
    return "fail" if exhausted(state) else "writer"


def critic(state: DeckState) -> Command[Literal["writer", "publish", "fail"]]:
    n = WORKSPACES[state["workspace_id"]]["slides.md"].count("---") + 1
    approved = n >= 5
    goto = "publish" if approved else ("fail" if exhausted(state) else "writer")
    return Command(goto=goto, update={"critique": {"approved": approved, "slides": n},
                                      "log": [f"critic: {n} slides -> {goto}"]})


def publish(state: DeckState) -> dict:
    key = f"decks/{state['deck_id']}/index.html"
    STORAGE[key] = "<html>" + WORKSPACES[state["workspace_id"]]["slides.md"] + "</html>"
    return {"url": f"https://cdn.example/{key}", "status": "published"}


def fail(state: DeckState) -> dict:
    return {"status": "failed"}


def cleanup(state: DeckState) -> dict:
    WORKSPACES.pop(state.get("workspace_id") or "", None)
    return {"workspace_id": None}


def build_graph(checkpointer):
    g = StateGraph(DeckState)
    for name, fn in [("interviewer", interviewer), ("outliner", outliner), ("provision", provision),
                     ("writer", writer), ("check", check), ("critic", critic),
                     ("publish", publish), ("fail", fail), ("cleanup", cleanup)]:
        g.add_node(name, fn)
    g.add_edge(START, "interviewer")
    g.add_edge("interviewer", "outliner")
    g.add_edge("outliner", "provision")
    g.add_edge("provision", "writer")
    g.add_edge("writer", "check")
    g.add_conditional_edges("check", route_after_check, ["critic", "writer", "fail"])
    g.add_edge("publish", "cleanup")
    g.add_edge("fail", "cleanup")
    g.add_edge("cleanup", END)
    return g.compile(checkpointer=checkpointer)


async def main():
    graph = build_graph(InMemorySaver())
    cfg = {"configurable": {"thread_id": "deck_1"}}
    first = {"deck_id": "deck_1", "topic": "Rust", "round": 0, "max_rounds": 4, "log": []}

    out = await graph.ainvoke(first, cfg)
    print("PAUSED:", out["__interrupt__"][0].value)
    print("next:", (await graph.aget_state(cfg)).next)

    async for ev in graph.astream(Command(resume={"audience": "Engineers"}), cfg, stream_mode="updates"):
        print("EVENT:", list(ev))
    final = (await graph.aget_state(cfg)).values
    print("\n".join(final["log"]))
    print(final["status"], final["url"], "workspace:", final["workspace_id"], "rounds:", final["round"])
    assert final["status"] == "published" and final["workspace_id"] is None and final["round"] == 3

    # crash recovery: workspace vanished mid-build, restore from source_key
    WORKSPACES.clear()
    wid = ensure_workspace({"source_key": "decks/deck_1/source.md"})
    assert "slides.md" in WORKSPACES[wid]
    print("restore ok")


asyncio.run(main())
