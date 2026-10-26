# Module 7 Deep Dive: LangGraph, Deep Agents, Self-Repair Loops & Human-in-the-Loop

> **Purpose of this guide:**
> This document is a dedicated, in-depth guide for **Module 7 (Stateful Workflows & Agent Orchestration with `LangGraph`, `LangChain`, and `Deep Agents`)**.
>
> **Strict Rule Followed:** None of the code below uses your game-studio domain. Instead, we build **"ChartForge" — an Autonomous Interactive Data-Widget & Dashboard Builder**.
> However, **ChartForge uses the exact same architectural skeleton, state machine topology, self-repair loop, dependency injection pattern, and human-in-the-loop (`interrupt` / `Command`) mechanics** that you will build in your project.

---

## Table of Contents

1. [The Mental Model: Why a State Graph Instead of a Plain `while` Loop?](#1-the-mental-model-why-a-state-graph-instead-of-a-plain-while-loop)
2. [The Complete Topology We Are Building ("ChartForge")](#2-the-complete-topology-we-are-building-chartforge)
3. [Part 1: Designing the Graph State (`TypedDict` & Reducers)](#3-part-1-designing-the-graph-state-typeddict--reducers)
4. [Part 2: Structured Output (`with_structured_output`) — The Spec Node](#4-part-2-structured-output-with_structured_output--the-spec-node)
5. [Part 3: Coding Agents, Tools & Subagents (`create_deep_agent`)](#5-part-3-coding-agents-tools--subagents-create_deep_agent)
6. [Part 4: Deterministic Verification + Bounded Self-Repair Loop](#6-part-4-deterministic-verification--bounded-self-repair-loop)
7. [Part 5: Human-in-the-Loop (`interrupt` & `Command(resume=...)`)](#7-part-5-human-in-the-loop-interrupt--commandresume)
8. [Part 6: Wiring the Complete `StateGraph` & Dependency Injection](#8-part-6-wiring-the-complete-stategraph--dependency-injection)
9. [Part 7: Durability (`AsyncPostgresSaver`) & Live SSE Streaming (`astream`)](#9-part-7-durability-asyncpostgressaver--live-sse-streaming-astream)

---

## 1. The Mental Model: Why a State Graph Instead of a Plain `while` Loop?

Beginners often ask: *"Why do I need LangGraph? Can't I just write a Python function that calls an LLM, runs a compiler in a `for` loop, and returns the result?"*

A plain Python function breaks down in production for **4 reasons**:

1. **Human Approval Takes Hours (Server Restarts):**
   After the agent builds a widget, you want to show the user a preview and wait for them to click **"Approve"** or **"Make the font bigger"**. You cannot hold an HTTP request or a Python `while` loop open in RAM for 3 hours.
   - **How LangGraph solves this:** After every single node finishes, LangGraph saves the entire state dictionary into Postgres (`AsyncPostgresSaver`). When the graph hits `interrupt()`, the Python function exits completely and frees 100% of RAM. Hours later, when the user clicks "Approve", LangGraph reloads the state from Postgres and resumes from that exact node.
2. **Mixing Deterministic Steps and LLM Steps:**
   Some steps **must** use an LLM (designing a spec, writing code, fixing a bug). Other steps **must never** use an LLM (running `tsc`, running Playwright, checking budgets, uploading files). In a graph, deterministic nodes and LLM nodes are first-class citizens wired together cleanly.
3. **Bounded Retries & Budget Guards:**
   If generated code fails to compile, you want to loop `verify → repair → verify`, **but at most `N` times** and only while `tokens_used < token_budget`. Conditional edges make routing logic explicit and testable.
4. **Live Progress Streaming (`SSE`):**
   Because the workflow is broken into named nodes (`spec`, `scaffold`, `implement`, `verify`, `repair`, `publish`), `graph.astream(..., stream_mode="updates")` automatically yields an event every time a node starts or finishes—giving your frontend a real-time progress timeline for free.

---

## 2. The Complete Topology We Are Building ("ChartForge")

Imagine a system called **ChartForge**: a user types *"Build an interactive Q3 revenue vs. churn bar chart widget with a CSV export button"*, and the studio autonomously designs, codes, verifies, repairs, asks for human sign-off, and publishes the widget.

```
                         ┌───────────────────────────┐
      User Prompt ─────► │  1. spec_node (LLM)       │
                         │  Prompt → WidgetSpec JSON │
                         └─────────────┬─────────────┘
                                       ▼
                         ┌───────────────────────────┐
                         │  2. scaffold_node (Det)   │
                         │  Boot sandbox + template  │
                         └─────────────┬─────────────┘
                                       ▼
                         ┌───────────────────────────┐
            ┌───────────►│  3. implement_node (Agent)│◄──────────┐
            │            │  Deep Agent writes code   │           │
            │            └─────────────┬─────────────┘           │
            │                          ▼                         │
            │            ┌───────────────────────────┐           │
            │            │  4. verify_node (Det)     │◄────┐     │
            │            │  Compile + headless check │     │     │
            │            └─────────────┬─────────────┘     │     │
            │                          │                   │     │
            │                 (route_after_verify)         │     │
            │              ┌───────────┼───────────┐       │     │
            │        [errors &         │       [budget/    │     │
            │       attempts < max]    │      max attempts]│     │
            │              ▼           │           ▼       │     │
            │     ┌─────────────────┐  │  ┌──────────────┐ │     │
            │     │ 5. repair_node  ├──┘  │  fail_node   │ │     │
            │     │ Patch errors    │     └──────────────┘ │     │
            │     └─────────────────┘                      │     │
            │                     [passed!]                │     │
            │                          ▼                   │     │
            │            ┌───────────────────────────┐     │     │
            │   [reject] │  6. approval_node (HITL)  │     │     │
            └────────────┤  interrupt() → waits for  ├─────┘     │
      (back to spec)     │  approve / edit / reject  │  [edit]   │
                         └─────────────┬─────────────┘           │
                                  [approve]                      │
                                       ▼                         │
                         ┌───────────────────────────┐           │
                         │  7. publish_node (Det)    │───────────┘
                         │  Upload bundle to R2/S3   │
                         └───────────────────────────┘
```

Notice how **every node in this diagram has a 1-to-1 counterpart in your own project**:
- `spec_node` ↔ `design` (GDD)
- `scaffold_node` ↔ `scaffold`
- `implement_node` ↔ `implement`
- `verify_node` ↔ `static_verify` + `runtime_verify`
- `repair_node` ↔ `repair`
- `approval_node` ↔ `await_approval`
- `publish_node` ↔ `publish`

---

## 3. Part 1: Designing the Graph State (`TypedDict` & Reducers)

### Theory: How State Flows Through LangGraph
1. **The State is a single `TypedDict`:** Every node receives `state: ChartStudioState` as its first parameter.
2. **Nodes return partial updates, NOT the whole state:** If a node only changes `status` and `spec`, it returns `{"status": "building", "spec": ...}`. LangGraph automatically merges those keys into the existing state.
3. **Overwriting vs. Appending (Reducers):**
   - By default, returning `{"attempts": 2}` **overwrites** `state["attempts"]` with `2`.
   - For lists like `messages` (chat history) or `failures`, if you want a node to **append** new items rather than overwrite the list, you use `Annotated[list, operator.add]` or `Annotated[list, add_messages]`.

```python
import operator
from typing import Annotated, Any, Literal, TypedDict
from langgraph.graph.message import add_messages


StudioStatus = Literal[
    "designing",
    "building",
    "verifying",
    "repairing",
    "awaiting_approval",
    "published",
    "failed",
    "budget_exceeded",
]


class ChartStudioState(TypedDict, total=False):
    # Identity & multi-tenancy
    org_id: str
    run_id: str
    thread_id: str

    # User input & optional edit instructions from human review
    prompt: str
    edit_instructions: str | None

    # Structured Spec (Pydantic model dumped to dict so it is JSON-serializable)
    spec: dict[str, Any]

    # Sandbox & Storage tracking
    sandbox_id: str | None
    published_url: str | None

    # Verification results
    verdict: dict[str, Any] | None

    # Control, retries & budget guardrails
    attempts: int
    max_attempts: int
    tokens_used: int
    token_budget: int

    # Append-only log of failure summaries across attempts
    failure_history: Annotated[list[str], operator.add]

    # Current lifecycle status
    status: StudioStatus

    # Conversation messages for agent nodes
    messages: Annotated[list, add_messages]
```

> **Why store `spec: dict[str, Any]` instead of a Pydantic object directly in `TypedDict`?**
> Because `AsyncPostgresSaver` serializes the state to Postgres after every node. Storing plain JSON-compatible `dict`s (`model.model_dump()`) guarantees clean serialization across database upgrades and makes inspecting checkpoints in Postgres effortless. You can re-validate it anytime with `WidgetSpec.model_validate(state["spec"])`.

---

## 4. Part 2: Structured Output (`with_structured_output`) — The Spec Node

### Theory: Never Parse Raw LLM Text with `json.loads()`
If you prompt an LLM *"Return a JSON object describing the chart"*, 5% of the time it will wrap the JSON in ` ```json ... ``` `, miss a required field, or invent an unsupported chart type.

Instead, LangChain's `.with_structured_output(PydanticModel)` forces the model (via tool-calling / constrained decoding) to return an instance of your **Pydantic model**—already validated!

```python
from typing import Literal
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model


# 1. Define the strict Pydantic schema for the Designer output
class DataSeriesSpec(BaseModel):
    label: str = Field(description="Name of the metric, e.g. 'Monthly Recurring Revenue'")
    color_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class WidgetSpec(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    chart_type: Literal["bar", "line", "stacked_area"]
    theme: Literal["dark", "light"] = "dark"
    enable_csv_export: bool = True
    series: list[DataSeriesSpec] = Field(min_length=1, max_length=4)


# 2. The Spec Node in LangGraph
async def spec_node(state: ChartStudioState) -> dict[str, Any]:
    # Initialize any supported model provider (Gemini, Groq, OpenAI, Anthropic)
    llm = init_chat_model("google_genai:gemini-2.5-flash", temperature=0.2)

    # Bind the Pydantic schema to the model
    structured_llm = llm.with_structured_output(WidgetSpec)

    prompt_text = (
        f"Design a data widget specification for this request:\n{state['prompt']}"
    )
    widget_spec: WidgetSpec = await structured_llm.ainvoke(prompt_text)

    return {
        "spec": widget_spec.model_dump(),
        "status": "building",
        "attempts": 0,
    }
```

---

## 5. Part 3: Coding Agents, Tools & Subagents (`create_deep_agent`)

### Theory: How the Coding Step Works
Once `spec_node` produces a structured `WidgetSpec` and `scaffold_node` boots a sandbox, the **Coder Agent** needs to read and write files inside that sandbox.

How do we give a LangChain / Deep Agent access to our `SandboxProvider` Protocol without hardcoding a global sandbox?
**Closure-bound `@tool` factories!** You write a small function `make_sandbox_tools(sandbox, sandbox_id)` that returns `@tool` functions bound to that specific build's `sandbox_id`.

```python
from langchain_core.tools import BaseTool, tool
from deepagents import create_deep_agent
from rift.core.ports.sandbox import SandboxProvider


def make_sandbox_tools(sandbox: SandboxProvider, sandbox_id: str) -> list[BaseTool]:
    """Creates LangChain tools bound to a specific sandbox_id."""

    @tool
    async def read_workspace_file(path: str) -> str:
        """Read a UTF-8 text file from the sandbox workspace."""
        raw = await sandbox.read_file(sandbox_id, path)
        return raw.decode("utf-8")

    @tool
    async def write_workspace_file(path: str, content: str) -> str:
        """Write UTF-8 text content to a file in the sandbox workspace."""
        await sandbox.write_file(sandbox_id, content.encode("utf-8"), path)
        return f"Wrote {len(content)} bytes to {path}"

    @tool
    async def run_typecheck() -> str:
        """Run the TypeScript compiler inside the sandbox to check for errors."""
        res = await sandbox.exec(sandbox_id, ["pnpm", "tsc", "--noEmit"])
        if res.exit_code == 0:
            return "Typecheck passed with 0 errors."
        return f"Typecheck failed (exit {res.exit_code}):\n{res.stderr}"

    return [read_workspace_file, write_workspace_file, run_typecheck]
```

### Using `create_deep_agent` Inside `implement_node`
`create_deep_agent` wraps a model + tools with a built-in **TODO planning tool** and **subagent delegation** (`subagents=[...]`) so complex coding work doesn't overflow a single context window:

```python
async def implement_node(
    state: ChartStudioState,
    *,
    sandbox: SandboxProvider,
) -> dict[str, Any]:
    sandbox_id = state["sandbox_id"]
    assert sandbox_id is not None, "Sandbox must be created before implement_node"

    tools = make_sandbox_tools(sandbox, sandbox_id)

    coder_agent = create_deep_agent(
        model="google_genai:gemini-2.5-pro",
        tools=tools,
        system_prompt=(
            "You are the Lead Widget Engineer for ChartForge. "
            "Implement the widget in `/workspace/src/widget.ts` matching the JSON spec. "
            "Always run `run_typecheck` before finishing."
        ),
    )

    # Include any human edit instructions if we are re-entering from human review
    task_description = f"Widget Spec JSON:\n{state['spec']}"
    if state.get("edit_instructions"):
        task_description += f"\n\nApply these user edits:\n{state['edit_instructions']}"

    await coder_agent.ainvoke(
        {"messages": [{"role": "user", "content": task_description}]}
    )

    return {
        "status": "verifying",
        "edit_instructions": None,  # Clear one-time edit instruction after applying
    }
```

---

## 6. Part 4: Deterministic Verification + Bounded Self-Repair Loop

### Theory: Why `verify_node` Must Be 100% Deterministic
If you ask an LLM *"Look at your code—does it have any bugs?"*, the LLM will happily say *"Everything looks great!"* even when the code crashes on line 3.

Instead:
1. **`verify_node` is pure Python** (zero LLM calls). It runs the compiler (`pnpm build`) and headless browser check inside the sandbox and writes a factual `verdict` dictionary into `ChartStudioState`.
2. **`route_after_verify` is a pure Python router function** that inspects `state["verdict"]`, `state["attempts"]`, and `state["tokens_used"]` to decide which node runs next.
3. **`repair_node` is an LLM agent** that only runs when `verify_node` found real errors. It receives the exact compiler/browser error trace, edits the broken file, and loops back into `verify_node`.

```python
from typing import Literal


# 1. Deterministic Verification Node (No LLM!)
async def verify_node(
    state: ChartStudioState,
    *,
    sandbox: SandboxProvider,
) -> dict[str, Any]:
    sandbox_id = state["sandbox_id"]
    assert sandbox_id is not None

    attempts = state.get("attempts", 0) + 1
    errors: list[str] = []

    # Step A: Static build check
    build_res = await sandbox.exec(sandbox_id, ["pnpm", "run", "build"])
    if build_res.exit_code != 0:
        errors.append(f"Build error:\n{build_res.stderr}")

    # Step B: Headless browser check (only if build succeeded)
    if not errors:
         browser_res = await sandbox.exec(
             sandbox_id, ["python3", "/workspace/verify_widget.py"]
         )
         if browser_res.exit_code != 0:
             errors.append(f"Runtime browser error:\n{browser_res.stderr}")

    passed = len(errors) == 0
    verdict = {"passed": passed, "errors": errors}

    return {
        "verdict": verdict,
        "attempts": attempts,
        "failure_history": ["; ".join(errors)] if errors else [],
    }


# 2. Conditional Edge Router (Pure function returning next node name)
def route_after_verify(
    state: ChartStudioState,
) -> Literal["await_approval", "repair", "budget_exceeded", "fail"]:
    verdict = state.get("verdict") or {}

    # Happy path: verification passed! Move to Human-in-the-Loop approval
    if verdict.get("passed") is True:
        return "await_approval"

    # Guardrail 1: Token budget check
    if state.get("tokens_used", 0) >= state.get("token_budget", 250_000):
        return "budget_exceeded"

    # Guardrail 2: Max retry attempts check
    if state.get("attempts", 0) >= state.get("max_attempts", 4):
        return "fail"

    # Otherwise, loop into the self-repair agent!
    return "repair"


# 3. Self-Repair Node (Targeted Bug-Fix Agent)
async def repair_node(
    state: ChartStudioState,
    *,
    sandbox: SandboxProvider,
) -> dict[str, Any]:
    sandbox_id = state["sandbox_id"]
    assert sandbox_id is not None

    verdict = state.get("verdict") or {}
    error_list = "\n\n".join(verdict.get("errors", []))

    tools = make_sandbox_tools(sandbox, sandbox_id)
    repair_agent = create_deep_agent(
        model="google_genai:gemini-2.5-pro",
        tools=tools,
        system_prompt=(
            "You are a Surgical Debugging Agent. Read the exact build/runtime errors "
            "below, inspect the broken file, apply the minimal fix, and run `run_typecheck`."
        ),
    )

    await repair_agent.ainvoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": f"Fix these verification failures:\n{error_list}",
                }
            ]
        }
    )

    return {"status": "verifying"}
```

---

## 7. Part 5: Human-in-the-Loop (`interrupt` & `Command(resume=...)`)

### Theory: How `interrupt()` Actually Works Under the Hood
When a node calls `decision = interrupt(payload)`:
1. **First time the node runs:** `interrupt(payload)` raises a special internal LangGraph signal (`GraphInterrupt`). LangGraph catches it, saves the current checkpoint to Postgres, surfaces `payload` to your API caller, and **stops executing the graph**.
2. **Hours later, when the user clicks a button in the UI:** Your FastAPI endpoint calls `await graph.ainvoke(Command(resume=user_decision), config=config)`.
3. **What happens on resume (CRITICAL):** LangGraph reloads the state from Postgres and **re-runs `await_approval_node` from line 1**! This time, when execution reaches `interrupt(payload)`, instead of pausing, `interrupt()` immediately returns `user_decision`!

> **The 3 Golden Rules of `interrupt()`:**
> 1. **Never wrap `interrupt()` in `try: ... except Exception:`** — catching the internal `GraphInterrupt` exception prevents the graph from pausing!
> 2. **No non-idempotent side effects above `interrupt()` in the same node:** Because the node re-runs from line 1 when resumed, any code *above* `interrupt()` runs twice (once before pausing, once on resume). Put side effects in their own node before or after the approval node.
> 3. **Keep `interrupt()` payloads and `Command(resume=...)` values pure JSON dicts.**

```python
from langgraph.types import Command, interrupt


async def await_approval_node(state: ChartStudioState) -> dict[str, Any]:
    # Pause execution and send this dictionary to the caller/UI
    human_decision: dict[str, Any] = interrupt(
        {
            "run_id": state.get("run_id"),
            "spec": state.get("spec"),
            "verdict": state.get("verdict"),
            "options": ["approve", "edit", "reject"],
        }
    )

    # Execution only reaches here AFTER Command(resume=...) is called!
    action = human_decision.get("action", "approve")

    if action == "edit":
        return {
            "status": "building",
            "edit_instructions": human_decision.get("instructions", ""),
        }
    if action == "reject":
        return {
            "status": "designing",
            "prompt": f"{state['prompt']} (Note: {human_decision.get('reason', '')})",
        }

    # Default: "approve"
    return {"status": "published"}


def route_after_approval(
    state: ChartStudioState,
) -> Literal["publish", "implement", "spec"]:
    status = state.get("status")
    if status == "building":
        return "implement"  # User requested an edit -> re-enter coder!
    if status == "designing":
        return "spec"       # User rejected the spec -> redesign!
    return "publish"        # User approved -> publish to R2!
```

---

## 8. Part 6: Wiring the Complete `StateGraph` & Dependency Injection

### Theory: How Do Nodes Receive `sandbox: SandboxProvider` and `storage: StorageProvider`?
LangGraph nodes expect the signature `async def my_node(state: ChartStudioState) -> dict`.
To inject your ports (`sandbox: SandboxProvider`, `storage: StorageProvider`) without global variables, wrap your builder in a factory function `build_chart_studio_graph(sandbox, storage, checkpointer)` using `functools.partial`:

```python
from functools import partial
from typing import Any
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from rift.core.ports.sandbox import SandboxProvider
from rift.core.ports.storage import StorageProvider


async def scaffold_node(
    state: ChartStudioState,
    *,
    sandbox: SandboxProvider,
) -> dict[str, Any]:
    sandbox_id = state.get("sandbox_id")
    if sandbox_id is None:
        sandbox_id = await sandbox.create()
    return {"sandbox_id": sandbox_id, "status": "building"}


async def publish_node(
    state: ChartStudioState,
    *,
    sandbox: SandboxProvider,
    storage: StorageProvider,
) -> dict[str, Any]:
    sandbox_id = state["sandbox_id"]
    assert sandbox_id is not None
    try:
        bundle_bytes = await sandbox.read_file(sandbox_id, "/workspace/dist/index.html")
        key = f"widgets/{state['run_id']}/index.html"
        await storage.upload_file(key, bundle_bytes, content_type="text/html")
        return {
            "status": "published",
            "published_url": storage.get_public_url(key),
            "sandbox_id": None,
        }
    finally:
        await sandbox.terminate(sandbox_id)


async def fail_node(
    state: ChartStudioState,
    *,
    sandbox: SandboxProvider,
) -> dict[str, Any]:
    if state.get("sandbox_id"):
        await sandbox.terminate(state["sandbox_id"])
    return {"status": "failed", "sandbox_id": None}


def build_chart_studio_graph(
    *,
    sandbox: SandboxProvider,
    storage: StorageProvider,
    checkpointer: BaseCheckpointSaver | None = None,
):
    builder = StateGraph(ChartStudioState)

    # 1. Register all nodes (binding `sandbox` and `storage` cleanly via partial)
    builder.add_node("spec", spec_node)
    builder.add_node("scaffold", partial(scaffold_node, sandbox=sandbox))
    builder.add_node("implement", partial(implement_node, sandbox=sandbox))
    builder.add_node("verify", partial(verify_node, sandbox=sandbox))
    builder.add_node("repair", partial(repair_node, sandbox=sandbox))
    builder.add_node("await_approval", await_approval_node)
    builder.add_node(
        "publish", partial(publish_node, sandbox=sandbox, storage=storage)
    )
    builder.add_node("fail", partial(fail_node, sandbox=sandbox))

    # 2. Wire standard edges
    builder.add_edge(START, "spec")
    builder.add_edge("spec", "scaffold")
    builder.add_edge("scaffold", "implement")
    builder.add_edge("implement", "verify")
    builder.add_edge("repair", "verify")  # Repair always loops back to verify!

    # 3. Wire conditional edges after `verify`
    builder.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "await_approval": "await_approval",
            "repair": "repair",
            "budget_exceeded": "fail",
            "fail": "fail",
        },
    )

    # 4. Wire conditional edges after human `await_approval`
    builder.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {
            "publish": "publish",
            "implement": "implement",
            "spec": "spec",
        },
    )

    builder.add_edge("publish", END)
    builder.add_edge("fail", END)

    return builder.compile(checkpointer=checkpointer)
```

---

## 9. Part 7: Durability (`AsyncPostgresSaver`) & Live SSE Streaming (`astream`)

### 1. Running in Unit Tests (`InMemorySaver`) vs. Production (`AsyncPostgresSaver`)
- **In `pytest`:** Pass `InMemorySaver()` + `FakeSandboxProvider()` + `InMemoryStorageProvider()`. Your entire multi-agent state machine runs in memory in milliseconds.
- **In Production:** Use `AsyncPostgresSaver.from_conn_string(postgres_url)` (note: `AsyncPostgresSaver` uses standard `postgresql://...` with `psycopg`, whereas SQLAlchemy uses `postgresql+asyncpg://...`).

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command


async def run_and_resume_example(
    postgres_url: str,
    sandbox: SandboxProvider,
    storage: StorageProvider,
) -> None:
    async with AsyncPostgresSaver.from_conn_string(postgres_url) as checkpointer:
        # Creates checkpoint tables on first run (idempotent)
        await checkpointer.setup()

        graph = build_chart_studio_graph(
            sandbox=sandbox,
            storage=storage,
            checkpointer=checkpointer,
        )

        # Every build uses its unique ID as the LangGraph thread_id
        config = {"configurable": {"thread_id": "run_98765"}}

        # --- PHASE A: Start the build and stream live node updates ---
        initial_input: ChartStudioState = {
            "org_id": "org_1",
            "run_id": "run_98765",
            "prompt": "Q3 MRR vs Churn bar chart in dark mode",
            "max_attempts": 3,
            "token_budget": 100_000,
        }

        async for event in graph.astream(
            initial_input, config=config, stream_mode="updates"
        ):
            # `event` is a dict like {"spec": {...}} or {"verify": {...}}
            for node_name, state_update in event.items():
                print(f"[SSE Event] Node '{node_name}' finished -> {state_update.keys()}")

        # At this point, the graph is PAUSED at `await_approval_node`!

        # --- PHASE B: User clicks "Edit" or "Approve" hours later ---
        # Example: User approves the preview
        final_state = await graph.ainvoke(
            Command(resume={"action": "approve"}),
            config=config,
        )
        print("Published URL:", final_state["published_url"])
```

---

## Summary: How to Translate "ChartForge" Into Rift (`src/rift/studio/`)

| ChartForge Concept (This Guide) | Rift Equivalent (`src/rift/studio/`) |
|---|---|
| `ChartStudioState` | `StudioState` in `src/rift/studio/state.py` |
| `WidgetSpec` (`spec_node`) | `GDD` (Game Design Document) in `design_node` |
| `scaffold_node` | Scaffolds Phaser 3 + Vite + TS starter (`topdown-shooter`) into Daytona |
| `implement_node` (`create_deep_agent`) | Writes Phaser scenes/entities against the Engine Kit |
| `verify_node` (deterministic) | Runs `pnpm tsc --noEmit`, `pnpm vite build`, and `verify_game.py` (Playwright) |
| `repair_node` + `route_after_verify` | Self-repairs TypeScript, build, or `window.__RIFT__` runtime errors up to `max_attempts` |
| `await_approval_node` (`interrupt`) | Pauses build with playable preview + screenshots; resumes on `"approve"`, `"edit"`, or `"reject"` |
| `publish_node` | Uploads verified `dist/` bundle to Cloudflare R2 and updates `BuildRepository` |
