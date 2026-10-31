# LangGraph Multi-Agent Pipelines — Learn the Pattern, Then Write Rift Yourself

> **How this relates to the other doc:** [`LANGGRAPH_AGENTS_GUIDE.md`](LANGGRAPH_AGENTS_GUIDE.md) is the *reference* (every detail of Rift). **This file is the *course*.** It teaches the same architecture on a **different, tiny project** so you learn the *shape* once, then write Rift's version yourself.
>
> Everything in Steps 1–6 **runs** — try it: `uv run python examples/slideforge_pipeline.py` and `uv run python examples/agent_interrupt_demo.py` (no API keys needed; I ran both).

---

## 0. The whole thing on one page

Rift's pipeline looks huge, but it is **7 small patterns** stacked. Learn them one by one:

| # | Pattern | One-line idea | Tool you use |
|---|---|---|---|
| 1 | **State + nodes** | A node is a function: `state in → partial dict out` | `StateGraph(TypedDict)` |
| 2 | **Edges + loop** | Static edge = fixed order; conditional edge = a pure function picks next node; loop = edge going backwards + a counter | `add_edge`, `add_conditional_edges` |
| 3 | **Command** | A node returns *update + next node* together | `Command(update=…, goto=…)` |
| 4 | **Pause for a human** | A node asks a question and the graph *stops*, saved in the DB; answer resumes it | `interrupt()`, `Command(resume=…)`, checkpointer |
| 5 | **Agent inside a node** | The LLM part is just a function call inside a node; structured output = typed hand-off | `create_agent(response_format=…)` |
| 6 | **Environment by pointer** | Big/real stuff (sandbox, files) lives outside state; state holds an *id* and you can always rebuild it | `ensure_x()` idempotent helper |
| 7 | **Publish + cleanup** | Last steps are boring deterministic code; cleanup is its own node shared by success and failure | plain nodes |

**The mental model in one sentence:**
> *Nodes do work and write facts into state. Edges decide who goes next by reading state. The checkpointer saves state after every node so the graph can stop and restart anywhere.*

---

## The practice project: **SlideForge**

Same shape as Rift, different domain — so you can't just copy-paste, you must *recognise the pattern*:

| SlideForge | Rift equivalent |
|---|---|
| `interviewer` (asks the user questions) | `planner` (HITL) |
| `outliner` (topic → outline) | `designer` (brief → GDD) |
| fake **workspace** dict (files) | Daytona sandbox |
| `writer` (writes `slides.md`) | `coder` |
| `check` (deterministic: "no TODO left") | `verify` (tsc / build / Playwright) |
| `critic` (needs ≥ 5 slides) | `reviewer` |
| `publish` (HTML → fake storage) | `publish` (index.html → R2) |
| `cleanup` (delete workspace) | `cleanup` (snapshot + delete sandbox) |

```text
START → interviewer ⇢(pause for human)⇢ outliner → provision → writer → check ─┬─ pass → critic ─┬─ ok ──→ publish ┐
                                                                   ▲           │                 │                 ├→ cleanup → END
                                                                   └─ fail ────┘  ◄── needs more ┘      fail ───────┘
```

---

## Step 1 — State and nodes

**Idea.** State is one `TypedDict`. A node reads it and returns *only what changed*. LangGraph merges the result in.
By default a returned key **overwrites**. For "append, don't overwrite" tag the key with a **reducer**.

```python
import operator
from typing import Annotated, Any, TypedDict

class DeckState(TypedDict, total=False):
    deck_id: str
    topic: str
    audience: str
    outline: list[str]
    workspace_id: str | None        # pointer to the environment (Step 6)
    source_key: str | None          # pointer to a durable copy (Step 6)
    check: dict[str, Any] | None    # deterministic facts
    critique: dict[str, Any] | None # reviewer verdict
    round: int
    max_rounds: int
    log: Annotated[list[str], operator.add]   # reducer: returned lists get APPENDED
    status: str
    url: str | None

def outliner(state: DeckState) -> dict:              # returns a PARTIAL update
    return {"outline": [f"{state['topic']} – part {i}" for i in range(1, 6)],
            "log": ["outliner: 5-point outline"]}    # appended, not overwritten
```

**Rules to remember**
- Return only changed keys. Never return `{**state, …}`.
- Store plain JSON (dicts/lists/str/int), not objects, so it survives the database (Step 4).
- Reducer keys (`log`, `messages`, `tokens_used`) take **deltas**: return `{"log": ["new line"]}`, not the whole list.

**▶ Your turn (Rift).** Write `StudioState` with: `prompt`, `messages` (use `add_messages`), `brief`, `gdd`, `sandbox_id`, `source_key`, `verify_report`, `review`, `round`, `max_rounds`, `status`. Ask yourself for each key: *overwrite or append?*

---

## Step 2 — Edges, conditional edges, and a bounded loop

**Idea.**
- `add_edge(a, b)`: after `a`, always `b`.
- `add_conditional_edges(a, router, [possible targets])`: after `a`, call `router(state)` — it returns the **name** of the next node. The router is a *pure function* (no I/O, no LLM) → trivially unit-testable.
- A **loop** is just an edge pointing backwards **plus a counter** so it ends.

```python
from typing import Literal
from langgraph.graph import END, START, StateGraph

def exhausted(state: DeckState) -> bool:
    return state.get("round", 0) >= state.get("max_rounds", 4)       # the loop's brake

def route_after_check(state: DeckState) -> Literal["critic", "writer", "fail"]:
    if state["check"]["passed"]:
        return "critic"
    return "fail" if exhausted(state) else "writer"                   # ← backwards edge = the loop

g = StateGraph(DeckState)
g.add_node("writer", writer); g.add_node("check", check)
g.add_node("critic", critic); g.add_node("fail", fail)
g.add_edge("writer", "check")
g.add_conditional_edges("check", route_after_check, ["critic", "writer", "fail"])
```

The **worker increments the counter** (`writer` returns `"round": state.get("round", 0) + 1`), the **router reads it**. Whoever does the work counts it.

**Deterministic check before the LLM critic:** `check` is plain Python (is there a `TODO`? does it compile?). If it fails we loop back **without paying for an LLM review**. Facts first, judgement second.

**▶ Your turn (Rift).** Write `route_after_verify(state) -> Literal["reviewer","coder","fail"]` and a `exhausted(state)` that also checks `tokens_used >= token_budget`. Write 4 `pytest` cases (passed; failed+rounds left; failed+out of rounds; failed+over budget). No LLM needed.

---

## Step 3 — `Command`: update and route in one atomic step

**Idea.** Sometimes the node that did the work is the one who knows where to go next (the critic just made a decision). Return `Command(update=…, goto=…)` instead of a dict.

```python
from langgraph.types import Command

def critic(state: DeckState) -> Command[Literal["writer", "publish", "fail"]]:
    n = slide_count(state)
    approved = n >= 5
    goto = "publish" if approved else ("fail" if exhausted(state) else "writer")
    return Command(
        goto=goto,
        update={"critique": {"approved": approved, "slides": n},
                "log": [f"critic: {n} slides -> {goto}"]},
    )
```
The `Command[Literal[…]]` return annotation tells LangGraph the possible destinations (used for drawing the graph). A node returning `Command` needs **no** outgoing edges in the builder.

**Which to use?** Router (Step 2) when the decision is a pure function of state that already exists. `Command` when the decision comes from the node's own fresh output.

**▶ Your turn (Rift).** Write `decide_after_review(verdict, state) -> Literal["coder","publish","fail"]` as a **pure function** (so it's testable), then call it from `reviewer` inside `Command(goto=…)`. Rule: only `blocker`/`major` issues cause another round; if rounds are exhausted, ship unless a blocker remains.

---

## Step 4 — Pause for a human (`interrupt`) + checkpointer

**Idea.** `interrupt(payload)` stops the graph. The state is saved to the checkpointer (memory in tests, Postgres in prod) and your Python call **returns**. Later `Command(resume=value)` continues, and `interrupt(...)` *returns that value*.

```python
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

def interviewer(state: DeckState) -> dict:
    answers = interrupt({"questions": [{"id": "audience", "question": "Who is the audience?",
                                        "options": ["Execs", "Engineers", "Students"]}]})
    return {"audience": answers["audience"]}               # runs only AFTER resume

graph = build_graph(checkpointer=InMemorySaver())          # interrupt REQUIRES a checkpointer
cfg = {"configurable": {"thread_id": "deck_1"}}            # thread_id = which saved run

out = await graph.ainvoke(first_input, cfg)                # ← returns when paused
out["__interrupt__"][0].value                              # the payload to show in the UI
(await graph.aget_state(cfg)).next                         # ('interviewer',) = waiting here

await graph.ainvoke(Command(resume={"audience": "Engineers"}), cfg)   # continue, same thread_id
```

Real output from the runnable example:
```text
PAUSED: {'questions': [{'id': 'audience', 'question': 'Who is the audience?', ...}]}
next: ('interviewer',)
```

**The 4 rules (each one causes a classic bug):**
1. **Never** wrap `interrupt()` in `try/except Exception` — it works by raising an exception.
2. On resume the node **re-runs from its first line**. Anything *above* `interrupt()` runs twice → no side effects (DB writes, uploads, creating sandboxes) before it.
3. Payload and resume value must be small JSON.
4. Same `thread_id` on resume, or you start a brand-new run.

**▶ Your turn (Rift).** Make a tiny graph `START → planner → END` where `planner` calls `interrupt` once, then returns `{"brief": …}`. Run it with `InMemorySaver`, print the payload, resume it. Then deliberately put `print("side effect")` above the interrupt and watch it print twice.

---

## Step 5 — An LLM agent *inside* a node

**Idea.** An agent is not special to the graph. A node is: `build agent → invoke it → map its output into state`. Use **structured output** so the hand-off is a validated Pydantic object, never parsed text.

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

class Outline(BaseModel):                 # ← the typed hand-off (the CONTRACT between agents)
    title: str
    points: list[str]

def build_outliner_agent():               # a FACTORY, not a module-level singleton
    return create_agent(
        model=make_model("outline"),
        system_prompt=OUTLINER_PROMPT,
        response_format=ToolStrategy(Outline),
        name="outliner",                  # NO checkpointer= → inherits the graph's (needed for Step 4)
    )

async def outliner(state: DeckState) -> dict:
    agent = build_outliner_agent()
    result = await agent.ainvoke({"messages": [HumanMessage(f"Topic: {state['topic']}\nAudience: {state['audience']}")]})
    outline: Outline = result["structured_response"]        # already validated
    return {"outline": outline.model_dump(),                # JSON into state
            "log": [f"outliner: {outline.title}"]}
```

**Why curated input instead of passing the whole conversation?** Each agent gets a *fresh, small* context built from the state fields it needs (the "view"). The durable context travels in typed state + the files — not in a giant shared message list. Cheaper, and agents don't get confused by each other's tool chatter.

**▶ Your turn (Rift).** Write `GameBrief` and `GameDesignDoc` Pydantic models, then `build_design_agent()` and `designer` node. Input to the agent = prompt + `state["brief"]` as JSON text. Output = `state["gdd"]`.

---

## Step 5b — Let an agent *ask the human* (`ask_user` tool)

**Idea.** Combine Step 4 + 5: give the agent a **tool whose body is `interrupt()`**. The LLM decides when to ask; the graph pauses; the answer becomes the tool's return value.

```python
from langchain_core.tools import tool
from langgraph.types import interrupt

@tool
def ask_user(question: str) -> str:
    """Ask the human a clarifying question."""
    answer = interrupt({"question": question})        # PAUSE here
    return f"User said: {answer}"                     # the LLM sees this as the tool result
```

I tested exactly this with a fake model (`examples/agent_interrupt_demo.py`) and the output proves how resume works:
```text
paused: {'question': 'Audience?'}   llm calls: 1   side: 1
brief:  {'title': 'Rust', ...}      llm calls: 2   side: 2
```
- **`llm calls` 1 → 2:** only **one new** LLM call after resume. The call that decided to ask was *not* repeated — the inner agent restored from its checkpoint.
- **`side` 1 → 2:** the *node* body ran again from the top (rule 2 above). Keep nodes with `interrupt` inside free of side effects.

Prompt tip for the planner: ask only what changes the outcome, batch questions in **one** call, give options, cap rounds (`ToolCallLimitMiddleware(tool_name="ask_user", run_limit=3)`), and write down decisions you made yourself as `assumptions`.

**▶ Your turn (Rift).** Write `ask_user(questions: list[Question])`, return answers as readable text. Then `build_plan_agent()` with `tools=[ask_user]`, `response_format=ToolStrategy(GameBrief)`.

---

## Step 6 — Environment by pointer (the sandbox pattern)

**Idea.** The real workspace (Daytona sandbox / files / browser) is **big, slow, and can die**. So:
- State holds only `workspace_id` (pointer), `source_key` (durable copy in object storage), and later a manifest.
- Nodes never assume the workspace exists; they call an **idempotent** `ensure_workspace(state)` first.
- After each work round, **snapshot** the source to durable storage.

```python
WORKSPACES: dict[str, dict[str, str]] = {}    # fake sandbox:   id -> {path: content}
STORAGE: dict[str, str] = {}                  # fake R2:        key -> content

def ensure_workspace(state: DeckState) -> str:
    wid = state.get("workspace_id")
    if wid and wid in WORKSPACES:             # still alive → reuse
        return wid
    wid = f"ws_{len(WORKSPACES) + 1}"         # dead or first time → create…
    WORKSPACES[wid] = {}
    if key := state.get("source_key"):        # …and restore if we have a snapshot
        WORKSPACES[wid]["slides.md"] = STORAGE[key]
    return wid

def writer(state: DeckState) -> dict:
    wid = ensure_workspace(state)                          # 1. self-heal
    WORKSPACES[wid]["slides.md"] = write_slides(state)     # 2. do the work IN the environment
    key = f"decks/{state['deck_id']}/source.md"
    STORAGE[key] = WORKSPACES[wid]["slides.md"]            # 3. snapshot to durable storage
    return {"workspace_id": wid, "source_key": key,        # 4. return POINTERS only
            "round": state.get("round", 0) + 1, "check": None, "critique": None}
```

Crash test from the example: `WORKSPACES.clear()` → `ensure_workspace({"source_key": …})` → file is back. In Rift the same function handles: sandbox idle-deleted, worker crashed, and **refinement builds** ("make the player faster" → start a new build from the parent's `source_key`).

**Rules**
- The environment is a *cache*; **storage + state is the truth**.
- Never put file contents in state (every node saves a checkpoint → you'd copy them dozens of times).
- Creating the environment is *not* allowed above an `interrupt()` in the same node (rule 2). That's why Rift's `provision` is a separate node **after** the planner.

**▶ Your turn (Rift).** Implement `ensure_sandbox(sandbox, storage, state)` with your `SandboxProvider` port: `exists()` → reuse; else `create()` + (`restore_source` if `source_key` else `seed_starter`). Test it with an in-memory fake provider: create, write a file, snapshot, kill, ensure, assert the file is back.

---

## Step 7 — Publish and cleanup

```python
def publish(state: DeckState) -> dict:
    key = f"decks/{state['deck_id']}/index.html"            # deterministic key → safe to retry
    STORAGE[key] = render_html(state)
    return {"url": public_url(key), "status": "published"}

def cleanup(state: DeckState) -> dict:                      # shared exit for publish AND fail
    destroy_workspace(state.get("workspace_id"))
    return {"workspace_id": None}

g.add_edge("publish", "cleanup")
g.add_edge("fail", "cleanup")
g.add_edge("cleanup", END)
```
Why `cleanup` is separate: upload and delete can fail/retry independently, and the failure path gets the same teardown for free. Deterministic keys make `publish` idempotent.

The full wiring, running end to end (real output of `examples/slideforge_pipeline.py`):
```text
interviewer: audience=Engineers
outliner: 5-point outline
writer: round 1, 2 slides
check: ['found TODO']            ← deterministic failure → straight back to writer (no LLM critic cost)
writer: round 2, 4 slides
check: ok
critic: 4 slides -> writer       ← critic wants ≥5 → Command(goto="writer")
writer: round 3, 6 slides
check: ok
critic: 6 slides -> publish
published https://cdn.example/decks/deck_1/index.html  workspace: None  rounds: 3
```

---

## Step 8 — Make it durable: swap `InMemorySaver` for Postgres

The graph code does **not change**. Only the object you pass to `compile()`:

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string("postgresql://user:pw@host/db") as saver:
    await saver.setup()                                   # creates tables once
    graph = build_graph(checkpointer=saver)
    await graph.ainvoke(first_input, {"configurable": {"thread_id": build_id}})
```
- Postgres URL for LangGraph is `postgresql://…` (psycopg). Your SQLAlchemy URL is `postgresql+asyncpg://…` → strip `+asyncpg`.
- Needs `uv add langgraph-checkpoint-postgres "psycopg[binary,pool]"` (not installed yet).
- Resume after a crash/restart: `graph.astream(None, config)` (`None` = "continue from last checkpoint").
- `thread_id = build_id`: one build = one saved run.

---

## Step 9 — The iframe (30 seconds)

Publish **one self-contained `index.html`** to R2 (single-file Vite build), serve it from its own domain, embed:
```html
<iframe src="https://play.example.com/builds/ID/index.html"
        sandbox="allow-scripts" allow="autoplay; fullscreen"></iframe>
```
No `allow-same-origin` ⇒ the game can't touch your cookies/API — and also can't use `localStorage` itself. Details: [guide §15](LANGGRAPH_AGENTS_GUIDE.md#15-publishing-r2-and-the-iframe).

---

## Pattern → Rift file map (where each step lands)

| Step | You write | File |
|---|---|---|
| 1 | `StudioState` | `src/rift/core/studio/state.py` |
| 2 | `exhausted`, `route_after_verify` | `…/studio/routing.py` |
| 3 | `decide_after_review` + `reviewer` node | `routing.py`, `nodes.py` |
| 4 | `interrupt` | inside `ask_user` (Step 5b) |
| 5 | `GameBrief`, `GameDesignDoc`, `ReviewVerdict` | `src/rift/core/domain/gdd.py` |
| 5 | `build_plan_agent`, `build_design_agent`, … | `src/rift/core/agents/*.py` |
| 5b | `ask_user` | `src/rift/core/toolbox/interaction_tools.py` |
| 6 | `ensure_sandbox`, `snapshot_source`, `teardown` | `…/studio/sandbox_lifecycle.py` |
| 2–7 | nodes as methods, graph wiring | `…/studio/nodes.py`, `graph.py` |
| 8 | checkpointer helper | `src/rift/memory/checkpointer.py` |

---

## Suggested build order (each step ends with something that *runs*)

1. **Fake everything.** Copy `examples/slideforge_pipeline.py`, rename to Rift terms (`interviewer→planner`, `writer→coder`…). Keep the fake workspace. Get the full flow green with **no LLMs**.
2. **Pure functions + tests:** routers, `decide_after_review`, `exhausted`.
3. **Replace one fake node at a time with a real agent**, in this order: `designer` (no tools) → `planner` (+`ask_user`) → `reviewer` (read-only tools) → `coder` (deep agent + sandbox).
4. **Replace the fake workspace/storage** with Daytona/R2 adapters behind your existing `SandboxProvider`/`StorageProvider` ports.
5. **Swap `InMemorySaver` → Postgres.** Kill the process mid-run, resume with `astream(None, cfg)`.
6. **Wrap in FastAPI + SSE.** Only now think about HTTP.

If a step breaks, you only changed one thing — that's the point of the order.

---

## Debug cheat sheet

| You see | Check |
|---|---|
| `interrupt` never pauses | Is a checkpointer passed to `compile()`? Is `thread_id` in config? |
| Resume starts over / does nothing | Different `thread_id`; or you passed a dict as input instead of `Command(resume=…)` |
| Something happens twice after resume | Side effect above `interrupt()` in the same node |
| `log`/`messages` has duplicates or loses items | Wrong reducer, or returning `{**state}` |
| Infinite loop | Router never reaches `fail`/exit; counter not incremented by the worker |
| `KeyError` in a node | Key missing because that node ran before the one that sets it — use `state.get()` or fix edge order |
| "Where is my graph now?" | `await graph.aget_state(cfg)` → `.values` (state), `.next` (waiting node), `.tasks[*].interrupts` |
| See every step | `graph.astream(input, cfg, stream_mode="updates")` |
| What happened earlier? | `graph.aget_state_history(cfg)` |

---

## Self-test (can you answer without looking?)

1. A node returns `{"log": ["x"]}` and `log` has `operator.add`. What's in state afterwards if it was `["a"]` before?
2. What decides which node runs after `check`? What type of thing is it, and why does that matter for testing?
3. Why does the `writer` increment `round` instead of the router?
4. Why must `provision` be a separate node from `planner`?
5. After `Command(resume=…)`, which code re-runs: the node, the agent's earlier LLM calls, or both?
6. If the sandbox is deleted while paused, which two state fields let you rebuild it?
7. Why store `workspace_id` in state but not the files?
8. Why is `cleanup` a node shared by `publish` and `fail`?

<details><summary>Answers</summary>

1. `["a", "x"]`.
2. The router function (conditional edge); it's pure so you can unit-test every branch with plain dicts, no LLM.
3. The worker knows when it did a round; the router stays a read-only function of state.
4. Because the node re-runs from the top on resume — creating a sandbox before the question would create it twice (and bill while the human thinks).
5. The node body re-runs; the inner agent's finished LLM calls do not (it restores from its checkpoint).
6. `workspace_id` (to detect it's gone) and `source_key` (to restore from). With no `source_key` yet, `ensure_*` just seeds a fresh starter.
7. Every node saves state to the DB; files would be copied into every checkpoint, and the environment can die anyway.
8. Upload and teardown retry independently; failures get identical teardown.
</details>
