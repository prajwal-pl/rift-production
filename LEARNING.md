# Backend Architecture & Engineering — Step-by-Step Learning Guide

> **How to use this guide:**
> This document breaks down the backend concepts, patterns, and libraries you need to master, ordered from foundational building blocks to advanced distributed patterns.
>
> **Strict Rule of This Guide:** None of the examples below use your actual project domain. Instead, all examples use a completely unrelated fictional domain — **an Automated Recipe & Bookstore / Invoice System** — or official library documentation patterns. This forces you to understand *why* a pattern works and *how* to translate it into your own codebase rather than copy-pasting code.

---

## Table of Contents

1. [The Mental Model: How Modern Python Backends Are Layered](#module-0-the-mental-model-how-modern-python-backends-are-layered)
2. [Module 1: Python Packaging & Workspaces with `uv`](#module-1-python-packaging--workspaces-with-uv)
3. [Module 2: Data Validation & Configuration (`Pydantic v2` & `pydantic-settings`)](#module-2-data-validation--configuration-pydantic-v2--pydantic-settings)
4. [Module 3: Hexagonal Architecture (Ports & Adapters with `Protocol`)](#module-3-hexagonal-architecture-ports--adapters-with-protocol)
5. [Module 4: Async Python (`asyncio`) Fundamentals](#module-4-async-python-asyncio-fundamentals)
6. [Module 5: Async Databases (`SQLAlchemy 2.0`, `Alembic`, Repository Pattern)](#module-5-async-databases-sqlalchemy-20-alembic-repository-pattern)
7. [Module 6: Building the HTTP API & Live Streaming (`FastAPI` + `SSE`)](#module-6-building-the-http-api--live-streaming-fastapi--sse)
8. [Module 7: Stateful Workflows & Agent Orchestration (`LangGraph` & `LangChain`)](#module-7-stateful-workflows--agent-orchestration-langgraph--langchain)
9. [Module 8: Isolated Cloud Execution (`Daytona` / `E2B` Sandboxes) & Object Storage (`S3 / R2`)](#module-8-isolated-cloud-execution-daytona--e2b-sandboxes--object-storage-s3--r2)
10. [Module 9: Headless Browser Automation (`Playwright`)](#module-9-headless-browser-automation-playwright)
11. [Module 10: Idempotency, Multi-Tenancy, and Background Webhooks (`Redis` & `QStash`)](#module-10-idempotency-multi-tenancy-and-background-webhooks-redis--qstash)
12. [Suggested Study Order & Practice Roadmap](#suggested-study-order--practice-roadmap)

---

## Module 0: The Mental Model: How Modern Python Backends Are Layered

When you look at a large backend plan, it feels overwhelming because you see 15 tools at once (Postgres, Redis, S3, FastAPI, LangGraph, Daytona, Alembic, etc.).

To make it simple, realize that **every backend is just 4 concentric rings**:

```
┌─────────────────────────────────────────────────────────────┐
│ 4. Entrypoints (FastAPI routes, CLI commands, Cron workers) │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ 3. Adapters (Postgres DB, S3/R2, Daytona, OpenAI)   │   │
│   │   ┌─────────────────────────────────────────────┐   │   │
│   │   │ 2. Application / Workflows (LangGraph, Use  │   │   │
│   │   │    Cases, Orchestration)                    │   │   │
│   │   │   ┌─────────────────────────────────────┐   │   │   │
│   │   │   │ 1. Core Domain & Ports              │   │   │   │
│   │   │   │ (Pure Python classes & interfaces)  │   │   │   │
│   │   │   └─────────────────────────────────────┘   │   │   │
│   │   └─────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

1. **Core Domain & Ports (Innermost):** Pure Python. Defines *what* things are (e.g., an `Invoice`, a `Customer`) and *what interfaces* you need (e.g., "I need something that can save a PDF"). Zero external libraries besides Pydantic/standard library.
2. **Application / Workflows:** The step-by-step logic or state machine (e.g., `LangGraph`). It coordinates the work using the interfaces from Ring 1.
3. **Adapters:** Concrete code that talks to the outside world (SQLAlchemy talking to Postgres, `boto3` talking to S3/R2, `daytona` or `e2b` running a sandbox).
4. **Entrypoints (Outermost):** FastAPI HTTP endpoints or background workers that receive a request from a user, wire the adapters into the workflow, and return/stream the result.

**Why this matters:** You never have to build the whole system at once. You build from the **inside out** (Ring 1 → Ring 2 → Ring 3 → Ring 4).

---

## Module 1: Python Packaging & Workspaces with `uv`

### The Concept
When you run `uv init`, `uv` creates a flat script (`main.py`). For a real backend where multiple services (like an API server, a background worker, and tests) share core logic, you use the **`src`-layout**.

In a `src`-layout, your Python package lives inside `src/<package_name>/`. This allows you to import `<package_name>.core...` cleanly from anywhere (`tests/`, `apps/`, `services/`) without messing with `sys.path`.

### Unrelated Example: A Bookstore Package (`bookstore`)

Directory structure:
```text
my-workspace/
├─ pyproject.toml
├─ src/
│  └─ bookstore/
│     ├─ __init__.py
│     └─ pricing.py
└─ tests/
   └─ test_pricing.py
```

In `pyproject.toml`:
```toml
[project]
name = "bookstore"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "pydantic>=2.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

When you run `uv sync`, `uv` installs `src/bookstore` in **editable mode** into `.venv`. Now, any file in `tests/` or `services/` can simply do:
```python
from bookstore.pricing import calculate_discount
```

### Hands-On Exercise
1. Create a folder `src/<your_package>/` with an `__init__.py`.
2. Add `[build-system]` using `hatchling` to `pyproject.toml`.
3. Run `uv sync` and verify you can run `uv run python -c "import <your_package>"`.

---

## Module 2: Data Validation & Configuration (`Pydantic v2` & `pydantic-settings`)

### The Concept
In Python, passing raw `dict` objects around leads to typos and runtime crashes (`KeyError`). **Pydantic** enforces strict types and validation at runtime.
**`pydantic-settings`** uses the exact same mechanism to read environment variables (`.env`) into a strongly typed Python object—so your app fails immediately on startup if a required API key or DB URL is missing.

### Unrelated Example 1: Domain Models with `Pydantic`

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, EmailStr

class Ingredient(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    grams: float = Field(gt=0, description="Weight in grams, must be positive")

class Recipe(BaseModel):
    id: str
    title: str
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    ingredients: list[Ingredient]
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Validating raw dictionary data (e.g. from JSON or an LLM):
raw_data = {
    "id": "rec_101",
    "title": "Sourdough Bread",
    "difficulty": "hard",
    "ingredients": [
        {"name": "Flour", "grams": 500.0},
        {"name": "Water", "grams": 350.0},
    ],
}

recipe = Recipe.model_validate(raw_data)
print(recipe.ingredients[0].name)  # "Flour"

# Dumping back to a JSON-compatible dictionary:
as_dict = recipe.model_dump(mode="json")
```

### Unrelated Example 2: App Settings with `pydantic-settings`

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class BakerySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BAKERY_",  # Looks for BAKERY_DATABASE_URL, etc.
        extra="ignore",
    )

    env: str = "development"
    database_url: str
    stripe_api_key: SecretStr
    max_oven_temp_celsius: int = 250

# Automatically reads from environment variables or .env file:
# settings = BakerySettings()
```

### Key Takeaways to Remember
- Use `model_validate(dict)` to parse dicts into models, and `model_dump()` to convert models back into dicts.
- Never scatter `os.getenv("...")` across your codebase. Read all env vars once in a central `config.py` using `BaseSettings`.

---

## Module 3: Hexagonal Architecture (Ports & Adapters with `Protocol`)

### The Concept
Why does your architecture forbid importing cloud SDKs (like AWS `boto3`, `daytona`, `e2b`, or `stripe`) inside `core/`?
Because if your core logic directly calls `boto3.client('s3').put_object(...)`:
1. You cannot run unit tests without an internet connection or complex mocking.
2. Switching from AWS S3 to local disk (for local dev) or Cloudflare R2 requires rewriting core logic.

Instead, Python's `typing.Protocol` lets you define a **Port** (an interface). Your core code only knows about the `Protocol`. Then you write **Adapters** (one for memory/testing, one for S3/R2) that match the shape of that `Protocol`.

### Unrelated Example: A Notification Port & Adapters

**1. The Port (lives in `core/ports/`):**
```python
from typing import Protocol

class ReceiptNotifier(Protocol):
    async def send_receipt(self, customer_email: str, total_usd: float) -> bool:
        """Send a payment receipt to the customer."""
        ...
```

**2. The Adapters (live in `adapters/`):**
```python
# Adapter A: Fake adapter for unit tests & local dev (zero external dependencies)
class InMemoryNotifier:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, float]] = []

    async def send_receipt(self, customer_email: str, total_usd: float) -> bool:
        self.sent_messages.append((customer_email, total_usd))
        return True

# Adapter B: Real third-party adapter (e.g., SendGrid / SMTP)
class SendGridNotifier:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def send_receipt(self, customer_email: str, total_usd: float) -> bool:
        # Here you would call the external SendGrid HTTP API
        print(f"[SendGrid] Sending ${total_usd} receipt to {customer_email}")
        return True
```

**3. Using the Port in Core Business Logic:**
```python
async def checkout_order(
    email: str,
    amount: float,
    notifier: ReceiptNotifier,  # <-- Accepts ANY class that implements send_receipt!
) -> None:
    # Do business calculations...
    taxed_amount = round(amount * 1.08, 2)
    await notifier.send_receipt(email, taxed_amount)
```

Notice that `InMemoryNotifier` and `SendGridNotifier` don't even need to inherit from `ReceiptNotifier`! Python's `Protocol` uses **structural subtyping** (duck typing with type-checker support): if a class has the matching `async def send_receipt(...)` method signature, Pyright/Mypy accepts it automatically.

---

## Module 4: Async Python (`asyncio`) Fundamentals

### The Concept
Backend servers spend 95% of their time **waiting on I/O**: waiting for Postgres to return rows, waiting for an LLM API to respond, waiting for a cloud container to finish running a command.
- **Synchronous Python (`def`):** While waiting 5 seconds for an LLM response, the entire Python thread is frozen and cannot serve any other user.
- **Asynchronous Python (`async def` / `await`):** When Python hits `await`, it pauses that function and lets the event loop handle other requests (like streaming events or answering health checks) until the network call finishes.

### Unrelated Example: Concurrent I/O with `asyncio.gather`

```python
import asyncio

async def fetch_book_price(isbn: str) -> float:
    await asyncio.sleep(1.0)  # Simulates a 1-second network request
    return 19.99

async def main() -> None:
    # Sequential (takes ~3 seconds):
    # p1 = await fetch_book_price("111")
    # p2 = await fetch_book_price("222")
    # p3 = await fetch_book_price("333")

    # Concurrent (takes ~1 second total!):
    prices = await asyncio.gather(
        fetch_book_price("111"),
        fetch_book_price("222"),
        fetch_book_price("333"),
    )
    print(f"Total: ${sum(prices):.2f}")

asyncio.run(main())
```

### Golden Rules of Async Python
1. **Never call blocking I/O inside `async def`:** Do not use `time.sleep()`, `requests.get()`, or synchronous database drivers (`psycopg2`) inside an `async def` function—they freeze the entire event loop. Use `asyncio.sleep()`, `httpx.AsyncClient`, and `asyncpg` instead.
2. **Always `await` coroutines:** Calling `fetch_book_price("111")` without `await` does not run the function; it just returns an unawaited coroutine object.

---

## Module 5: Async Databases (`SQLAlchemy 2.0`, `Alembic`, Repository Pattern)

### The Concept
1. **SQLAlchemy 2.0 (Async ORM):** Maps Python classes (`Mapped[...]`) to Postgres tables and executes SQL queries asynchronously via `asyncpg`.
2. **Alembic (Migrations):** Tracks changes to your database schema over time (like Git commits for SQL tables). Instead of manually running `CREATE TABLE`, Alembic compares your SQLAlchemy models to the database and generates migration scripts.
3. **Repository Pattern:** Wraps raw SQLAlchemy queries (`select()`, `session.add()`) inside a clean class so the rest of your app doesn't have SQL queries scattered everywhere.

### Unrelated Example: A Library Book Database

**1. Defining the Table (`models.py`):**
```python
from datetime import datetime
from sqlalchemy import String, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

class Base(DeclarativeBase):
    pass

class BookRow(Base):
    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    library_id: Mapped[str] = mapped_column(String(64), index=True)  # Tenant ID!
    title: Mapped[str] = mapped_column(String(255))
    author: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
```

**2. Writing a Tenant-Scoped Repository (`repositories.py`):**
Notice how `library_id` (the tenant scope) is required in every query so Library A can never accidentally read or delete Library B's books:
```python
class BookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, book_id: str, library_id: str, title: str, author: str) -> BookRow:
        row = BookRow(id=book_id, library_id=library_id, title=title, author=author)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, *, library_id: str, book_id: str) -> BookRow | None:
        stmt = select(BookRow).where(
            BookRow.id == book_id,
            BookRow.library_id == library_id,  # Enforces multi-tenant isolation!
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
```

**3. How Alembic Commands Work:**
```bash
# Initialize Alembic (with async template)
uv run alembic init -t async migrations

# Generate a new migration file after editing SQLAlchemy models
uv run alembic revision --autogenerate -m "create books table"

# Apply migrations to Postgres
uv run alembic upgrade head
```

---

## Module 6: Building the HTTP API & Live Streaming (`FastAPI` + `SSE`)

### The Concept
**FastAPI** builds HTTP APIs using standard Python type hints and Pydantic models.
Two patterns you will use heavily:
1. **Dependency Injection (`Depends`):** Automatically provides a database session or checks the logged-in user on every request, and cleans up the connection when the request ends.
2. **Server-Sent Events (`SSE`):** When a backend task takes 60 seconds (like generating a report or running a workflow), a normal HTTP request would hang or time out. With **SSE**, the server keeps the HTTP response open and yields JSON events one by one (`data: {...}\n\n`) so the frontend can update a progress bar in real time.

### Unrelated Example: A Pizza Order Tracker API with SSE

```python
import asyncio
import json
from collections.abc import AsyncGenerator
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()

class OrderRequest(BaseModel):
    topping: str
    size: str = "medium"

# 1. Dependency Injection example: extracting current tenant/user
async def get_current_shop_id() -> str:
    # In real life, decode a JWT token or session cookie here
    return "shop_nyc_01"

# 2. Normal POST endpoint
@app.post("/orders")
async def create_order(
    payload: OrderRequest,
    shop_id: str = Depends(get_current_shop_id),
) -> dict:
    return {"order_id": "ord_999", "shop_id": shop_id, "status": "queued"}

# 3. Server-Sent Events (SSE) endpoint for real-time progress
async def pizza_status_stream(order_id: str) -> AsyncGenerator[str, None]:
    steps = ["kneading_dough", "adding_sauce", "baking_in_oven", "out_for_delivery"]
    for step in steps:
        await asyncio.sleep(1.5)  # Simulates work happening
        event_payload = json.dumps({"order_id": order_id, "step": step})
        # SSE protocol format requires "data: <payload>\n\n"
        yield f"data: {event_payload}\n\n"

@app.get("/orders/{order_id}/events")
async def stream_order_events(order_id: str) -> StreamingResponse:
    return StreamingResponse(
        pizza_status_stream(order_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
```

---

## Module 7: Stateful Workflows & Agent Orchestration (`LangGraph` & `LangChain`)

> **Dedicated Deep-Dive Guide:** For a complete, end-to-end guide using an unrelated domain ("ChartForge") that mirrors your exact studio topology (`spec → scaffold → implement → verify ⇄ repair → interrupt/approve → publish`, `create_deep_agent`, `functools.partial` port injection, and `AsyncPostgresSaver`), see **[LANGGRAPH_AGENTS_GUIDE.md](LANGGRAPH_AGENTS_GUIDE.md)**.

Since you mentioned you will read the official LangGraph and LangChain docs, this module summarizes the **exact architectural patterns** from the docs so you know *what* to look for when reading them.

### Pattern 1: `StateGraph`, Nodes, and Conditional Edges
A LangGraph workflow is a state machine:
- **State (`TypedDict`):** A single dictionary schema passed through the graph.
- **Nodes:** Plain Python functions (or async functions) that take the current `State` and return a dictionary of **updates** to that state.
- **Conditional Edges:** A router function that inspects the state (e.g., "Did the invoice pass validation, or did it have math errors?") and returns the name of the next node to visit.

#### Unrelated Example: An Automated Invoice Auditor Graph
```python
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END

# 1. Define the State
class InvoiceState(TypedDict, total=False):
    raw_text: str
    extracted_total: float
    math_is_valid: bool
    attempts: int
    status: Literal["pending", "approved", "failed"]

# 2. Define Nodes (each returns ONLY the keys it wants to update)
async def extract_invoice_node(state: InvoiceState) -> dict:
    # Imagine an LLM with .with_structured_output() extracts the total here
    attempts = state.get("attempts", 0) + 1
    return {"extracted_total": 150.0, "attempts": attempts}

async def verify_math_node(state: InvoiceState) -> dict:
    # Deterministic verification node (no LLM!)
    is_valid = state.get("extracted_total", 0) > 0
    return {"math_is_valid": is_valid}

# 3. Define Routing Function
def route_after_verify(state: InvoiceState) -> Literal["approve", "extract", "fail"]:
    if state.get("math_is_valid"):
        return "approve"
    if state.get("attempts", 0) >= 3:
        return "fail"
    return "extract"  # Loop back and try again!

async def approve_node(state: InvoiceState) -> dict:
    return {"status": "approved"}

async def fail_node(state: InvoiceState) -> dict:
    return {"status": "failed"}

# 4. Wire the Graph
builder = StateGraph(InvoiceState)
builder.add_node("extract", extract_invoice_node)
builder.add_node("verify", verify_math_node)
builder.add_node("approve", approve_node)
builder.add_node("fail", fail_node)

builder.add_edge(START, "extract")
builder.add_edge("extract", "verify")
builder.add_conditional_edges(
    "verify",
    route_after_verify,
    {"approve": "approve", "extract": "extract", "fail": "fail"},
)
builder.add_edge("approve", END)
builder.add_edge("fail", END)

graph = builder.compile()
```

### Pattern 2: Structured Output (`with_structured_output`)
Never ask an LLM to "reply in JSON" and parse it with `json.loads()`—it will eventually include markdown backticks or hallucinate field names. Instead, bind a Pydantic model to the chat model:
```python
from pydantic import BaseModel

class ExtractedInvoice(BaseModel):
    vendor_name: str
    line_items_sum: float
    tax: float

# structured_llm = chat_model.with_structured_output(ExtractedInvoice)
# invoice_obj: ExtractedInvoice = await structured_llm.ainvoke("Parse this receipt: ...")
```

### Pattern 3: Checkpointing & Human-in-the-Loop (`interrupt` & `Command`)
When you compile a graph with a **Checkpointer** (like `InMemorySaver` for tests or `AsyncPostgresSaver` for production), LangGraph saves the state after every single node under a `thread_id`.

This unlocks `interrupt()`: a node can pause execution and wait hours or days for a human to click "Approve" or "Edit" in the UI!

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

async def manager_review_node(state: InvoiceState) -> dict:
    # Pauses the graph! Surfaces this dictionary to the caller.
    decision = interrupt({
        "question": "Approve this invoice payment?",
        "amount": state.get("extracted_total"),
    })
    # When resumed via Command(resume={"action": "approve"}), `decision` receives that dict!
    if decision.get("action") == "approve":
        return {"status": "approved"}
    return {"status": "failed"}
```

**4 Non-Negotiable Rules of `interrupt()` (from LangGraph Docs):**
1. **Never wrap `interrupt()` in a bare `try / except Exception:`** — under the hood, `interrupt()` pauses the graph by raising a special internal exception. Catching it breaks the pause mechanism.
2. **Idempotency before `interrupt()`:** When you resume a graph with `Command(resume=...)`, LangGraph **re-runs the node function from line 1** up to the `interrupt()` call (where it immediately returns the resume value). Therefore, do not put non-idempotent side effects (like charging a credit card or sending an email) *above* `interrupt()` inside the same node. Put them in their own node *before* or *after* the interrupt node.
3. **Always pass a `thread_id` in `config`:**
   ```python
   config = {"configurable": {"thread_id": "invoice_thread_42"}}
   await graph.ainvoke({"raw_text": "..."}, config=config)
   # Later, resume the paused thread:
   await graph.ainvoke(Command(resume={"action": "approve"}), config=config)
   ```
4. **Checkpointer vs. Store:**
   - **Checkpointer (`AsyncPostgresSaver`):** Short-term memory for a *single run/thread* (keyed by `thread_id`).
   - **Store (`AsyncPostgresStore`):** Long-term memory shared *across threads* (e.g., remembering a customer's preferred currency across all their future invoices).

---

## Module 8: Isolated Cloud Execution (`Daytona` / `E2B` Sandboxes) & Object Storage (`S3 / R2`)

> **Dedicated Deep-Dive Guide:** For a complete, game-studio-specific walkthrough of how **Daytona + Playwright + Cloudflare R2** link together end-to-end in Rift, see **[SANDBOX_STORAGE_GUIDE.md](SANDBOX_STORAGE_GUIDE.md)**.

### Concept A: Why Cloud Sandboxes (`Daytona` & `E2B`)?
If an automated system generates Python or JavaScript code and needs to compile or test it, **you must never run `subprocess.run()` on your own FastAPI server**. Untrusted code could delete files, read your `.env` database passwords, or use 100% CPU.

A **Cloud Sandbox** (like **Daytona** or **E2B**) boots an isolated Linux container/microVM in sub-second time (`~90ms` from snapshot) with no access to your server's secrets, runs the command, and destroys itself.

#### Why Daytona (Primary) vs. E2B (Fallback)?
- **Daytona (Primary):** Gives **$200 in free compute credits** (no credit card required for Tier 1 email-verified, 10 vCPU / 10 GiB RAM / 30 GiB storage pool), pure pay-as-you-go per-second pricing afterwards (no $150/month base fee), per-sandbox CPU/RAM sizing (`Resources`), custom snapshots/Docker images, and an official `langchain-daytona` backend for LangChain's `deepagents`.
- **E2B (Fallback):** Firecracker microVMs with a **$100 one-time credit** on the Hobby tier (up to 20 concurrent sandboxes, 1-hour max session duration; Pro jumps to $150/mo base). Because both live behind your `SandboxProvider` Protocol, you can switch between them via `SANDBOX_PROVIDER=daytona|e2b`.

#### Unrelated Example 1: Running an Untrusted Data-Science Script in Daytona (`AsyncDaytona`)
```python
from daytona import AsyncDaytona, CreateSandboxFromImageParams, Image, Resources

async def run_csv_analysis_in_daytona(csv_bytes: bytes, script_code: str) -> str:
    # Reads DAYTONA_API_KEY from environment automatically
    async with AsyncDaytona() as daytona:
        params = CreateSandboxFromImageParams(
            image=Image.debian_slim("3.12").pip_install(["pandas"]),
            resources=Resources(cpu=1, memory=1, disk=3),  # 1 vCPU, 1 GiB RAM, 3 GiB disk
            auto_stop_interval=5,  # Auto-stop after 5 minutes of inactivity
        )
        sb = await daytona.create(params, timeout=120)
        try:
            # 1. Upload files into the sandbox filesystem
            await sb.fs.upload_file(csv_bytes, "/tmp/data.csv")
            await sb.fs.upload_file(script_code.encode("utf-8"), "/tmp/analyze.py")

            # 2. Execute command inside the sandbox
            response = await sb.process.exec("python /tmp/analyze.py", timeout=30)
            return response.result
        finally:
            # 3. ALWAYS delete the sandbox in a finally block so you don't leak billing!
            await daytona.delete(sb)
```

#### Unrelated Example 2: The Same Pattern in E2B (`AsyncSandbox`)
```python
from e2b import AsyncSandbox

async def run_csv_analysis_in_e2b(csv_bytes: bytes, script_code: str) -> str:
    # Reads E2B_API_KEY from environment automatically
    sb = await AsyncSandbox.create(timeout=120)
    try:
        await sb.files.write("/tmp/data.csv", csv_bytes)
        await sb.files.write("/tmp/analyze.py", script_code)

        result = await sb.commands.run("python3 /tmp/analyze.py", timeout=30)
        return result.stdout
    finally:
        await sb.kill()
```

### Concept B: Content-Addressed Object Storage (`S3 / Cloudflare R2`)
Databases (Postgres) are for structured rows (`users`, `orders`), **not** for storing 5 MB ZIP files, PDFs, or images. You store files in **Object Storage** (AWS S3, Cloudflare R2, or local MinIO) and save only the file's path/key in Postgres.

**What does "Content-Addressed" mean?**
Instead of naming a file `report_latest.pdf` (which gets overwritten and breaks caching), you hash the file's bytes with `SHA-256` and name it `reports/<sha256_hash>.pdf`.
- If you upload the exact same file twice, it produces the exact same hash → **free deduplication and idempotency**!

#### Unrelated Example: Content-Addressed PDF Upload (`boto3`)
```python
import hashlib
import boto3

def upload_pdf_content_addressed(bucket: str, pdf_bytes: bytes) -> str:
    # 1. Compute SHA-256 hash of the file contents
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    storage_key = f"invoices/{digest}.pdf"

    # 2. Upload to S3 / Cloudflare R2 / MinIO
    s3 = boto3.client(
        "s3",
        endpoint_url="https://<account_id>.r2.cloudflarestorage.com",
        aws_access_key_id="...",
        aws_secret_access_key="...",
    )
    s3.put_object(
        Bucket=bucket,
        Key=storage_key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    return storage_key
```

---

## Module 9: Headless Browser Automation (`Playwright`)

### The Concept
Sometimes `npm run build` succeeds, TypeScript has zero errors, and yet when a real browser opens the web page, it crashes immediately with `TypeError: Cannot read properties of undefined`.
**Playwright** launches a real Chromium browser in **headless mode** (no visible window), opens a URL, listens for console errors, clicks buttons or presses keys, and takes screenshots to prove the page actually works at runtime.

### Unrelated Example: Verifying an Interactive Calculator Web Page

```python
from playwright.async_api import async_playwright

async def verify_calculator_app(url: str) -> dict:
    console_errors: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Capture any uncaught JS exceptions or console.error calls
        page.on("pageerror", lambda exc: console_errors.append(str(exc)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        # 2. Load the page
        await page.goto(url, wait_until="networkidle")

        # 3. Interact with the page (press buttons: 2 + 3 =)
        await page.click("#btn-2")
        await page.click("#btn-plus")
        await page.click("#btn-3")
        await page.click("#btn-equals")

        # 4. Read state from the DOM or window object
        result_text = await page.inner_text("#display")

        # 5. Take a screenshot as proof
        screenshot_bytes = await page.screenshot(full_page=True)

        await browser.close()

    return {
        "booted": len(console_errors) == 0,
        "errors": console_errors,
        "calculation_correct": result_text.strip() == "5",
        "screenshot_size": len(screenshot_bytes),
    }
```

---

## Module 10: Idempotency, Multi-Tenancy, and Background Webhooks (`Redis` & `QStash`)

### Concept A: Idempotency (Why Retries Can Be Dangerous)
In distributed systems, networks fail and jobs retry automatically.
If a background worker retries a step 3 times, you must ensure it doesn't charge the user's quota 3 times!
**Solution — An Idempotency / Dedupe Key:**
Every usage or billing event includes a unique `dedupe_key` (for example: `f"{invoice_id}:ocr_step:attempt_{attempt_num}"`) with a `UNIQUE` constraint in Postgres. If a retry tries to insert the same `dedupe_key` again, Postgres ignores the duplicate (`ON CONFLICT DO NOTHING`).

### Concept B: Multi-Tenancy (Data Isolation)
In a B2B or multi-organization SaaS:
- Every User belongs to an **Organization (`org_id`)** via a `Membership` table with a `role` (`owner`, `admin`, `member`, `viewer`).
- **Golden Rule:** Never write a database query like `SELECT * FROM invoices WHERE id = :id`. Always scope it by the authenticated user's organization:
  `SELECT * FROM invoices WHERE id = :id AND org_id = :current_org_id`.

### Concept C: Serverless Cron & Delayed Jobs (`QStash`)
Traditionally, running a cleanup task every night at midnight required running an extra server 24/7 (like Celery Beat).
Modern serverless queues like **Upstash QStash** flip this around: QStash is an external HTTP scheduler that simply sends a signed `POST` request to your FastAPI webhook endpoint (`/webhooks/cleanup`) on a cron schedule!

```python
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

@app.post("/webhooks/nightly-cleanup")
async def handle_nightly_cleanup(
    upstash_signature: str = Header(alias="Upstash-Signature"),
) -> dict:
    # 1. Verify signature so random people on the internet can't trigger your cron job
    # verify_qstash_signature(upstash_signature, body)

    # 2. Run idempotent cleanup (e.g., delete expired temporary files > 7 days old)
    deleted_count = 42
    return {"status": "ok", "deleted": deleted_count}
```

---

## Suggested Study Order & Practice Roadmap

Don't try to learn all 10 modules in one day. Learn them **just-in-time** right before the phase that needs them:

| Step | What to Learn & Practice First | Concepts Used |
|---|---|---|
| **Step 1 (Day 1–2)** | **Modules 1, 2, & 3:** Set up `uv` `src`-layout, write pure `Pydantic` models, `pydantic-settings`, and a `Protocol` interface with an in-memory fake adapter. Write a `pytest` test for it. | `uv`, `Pydantic`, `Protocol`, `pytest` |
| **Step 2 (Day 3–4)** | **Modules 4 & 5:** Spin up local Postgres in Docker Compose. Define 2 simple tables in `SQLAlchemy 2.0` async, generate an `Alembic` migration, and write a Repository class with `pytest-asyncio` tests. | `asyncio`, `SQLAlchemy`, `Alembic` |
| **Step 3 (Day 5–6)** | **Module 8 & 9:** Write a standalone 40-line Python script that boots a `Daytona` (or `E2B` / local Docker) sandbox, runs a build command inside it, opens the output in headless `Playwright`, and uploads a file to local MinIO / S3. | `Daytona`, `Playwright`, `boto3` |
| **Step 4 (Day 7–10)** | **Module 7:** Dive into the official **LangGraph** & **LangChain** docs. Build a tiny 3-node graph (`extract → verify → repair`) with `InMemorySaver`, then swap in `AsyncPostgresSaver` and test `interrupt()` / `Command(resume=...)`. | `LangGraph`, `LangChain`, Checkpointers, HITL |
| **Step 5 (Day 11+)** | **Modules 6 & 10:** Wrap your working graph in `FastAPI` endpoints, stream node transitions over `SSE`, and add tenant scoping + idempotent usage tracking. | `FastAPI`, `SSE`, Multi-tenancy |
