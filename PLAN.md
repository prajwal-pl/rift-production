# Rift — Comprehensive Development Plan

> **What is Rift?**
> An AI game studio. A user types a prompt — *"a neon cyberpunk top-down
> shooter where I dodge malware and collect data packets, with a synthwave
> soundtrack"* — and a **multi-agent studio** designs it, scaffolds a real
> project, writes the code, generates the visuals and HUD, runs it in an
> isolated sandbox, **plays it with a bot, finds its own bugs, fixes them**,
> and publishes a playable game you can embed anywhere.
>
> The interesting part is **not** "prompt → game" (that space is crowded:
> Rosebud, Astrocade, Websim, Replit, v0). The interesting part — and the
> portfolio thesis — is the engineering *behind* it:
>
> **A durable, multi-tenant, human-in-the-loop agent studio with real
> verification, isolated execution sandboxes, and an eval scoreboard that
> proves generated games actually run, are winnable, and match their spec.**
>
> Everything in this document serves that thesis.

---

## Table of Contents

1. [North Star](#north-star)
2. [Scope Guardrails (Read First)](#scope-guardrails-read-first)
3. [Design Principles](#design-principles)
4. [Glossary](#glossary)
5. [Architecture Overview](#architecture-overview)
6. [Target Repository Structure](#target-repository-structure)
7. [Tech Stack](#tech-stack)
8. [The Two Kinds of Sandbox](#the-two-kinds-of-sandbox)
9. [Domain Model](#domain-model)
10. [Data Model](#data-model)
11. [The Agent Studio (LangGraph)](#the-agent-studio-langgraph)
12. [The Game Dev Toolbox](#the-game-dev-toolbox)
13. [The Engine Kit](#the-engine-kit)
14. [The Sandbox Layer (Daytona & E2B)](#the-sandbox-layer-daytona--e2b)
15. [Verification & Evaluation](#verification--evaluation)
16. [Multi-Tenancy, Quotas & Metering](#multi-tenancy-quotas--metering)
17. [API Design](#api-design)
18. [Frontend Architecture](#frontend-architecture)
19. [Security Model](#security-model)
20. [Cost Model & Budget Controls](#cost-model--budget-controls)
21. [Deployment Topology (Free Tier)](#deployment-topology-free-tier)
22. [Engineering Standards](#engineering-standards)
23. [Phased Roadmap](#phased-roadmap)
24. [Evaluation Scoreboard](#evaluation-scoreboard)
25. [Risks & Mitigations](#risks--mitigations)
26. [Milestone Map (v0.1 → v1.0)](#milestone-map)
27. [Shortcut Build Order](#shortcut-build-order)
28. [Appendix](#appendix)

---

## North Star

The end goal is a studio that receives a prompt and autonomously produces a
**playable, verified, spec-compliant 2D web game**:

```
User:  "neon cyberpunk top-down shooter, dodge malware, collect data packets,
        synthwave soundtrack"

Rift:  DESIGN       → GDD: top-down twin-stick, 3 waves, dash ability, score loop
       SCAFFOLD     → Phaser 3 + Vite + TS project from `topdown-shooter` starter
       IMPLEMENT    → player controller, enemy spawner, collision, scoring, HUD
       VERIFY       → tsc ✓ · vite build ✓ · boot in headless Chrome ✓
                    → console errors: 1 (undefined `this.score`)
       REPAIR       → fix → re-verify ✓
       CRITIQUE     → vision: "HUD overlaps play area" → fix layout → ✓
       APPROVE      → (human) "looks good"           [interrupt / resume]
       PUBLISH      → static dist → R2 → playable iframe URL
       SCOREBOARD   → runs ✓ · winnable ✓ · spec-match 8/9 ✓ · 41s build
```

Everything below exists to make that loop **reliable, safe, measurable, and cheap
enough to run for free.**

---

## Scope Guardrails (Read First)

These are deliberate constraints. They are what make the difference between a
finished, impressive project and an abandoned one. **Do not relax them early.**

1. **2D only.** Phaser 3 / Canvas. No Three.js, no Godot, no 3D, no shaders.
2. **Browser games only.** Output runs in an `<iframe>`. No native targets.
3. **One genre family first** (2D arcade: top-down shooter, platformer, or
   puzzle). Add genres only after the loop is reliable end-to-end.
4. **Engine-kit + data first, free-form coding second.** The agent composes and
   configures a *tested* runtime more than it invents one.
5. **Build in the sandbox, play in the browser.** Never expose the dev server.
6. **Verification is not optional.** A build that can't be verified is a demo,
   not a product.
7. **No parallax, no custom agent runtime.** We use LangChain + LangGraph +
   Deep Agents as the harness. The product is the *studio*, not the runtime.

### Anti-goals (explicitly out of scope)

- A general-purpose app generator (websites, SaaS, mobile).
- 3D, VR, multiplayer/networking, or game "marketplaces" with payments.
- Fine-tuning our own code model (we may *route* models, not train them).
- Beating Rosebud on raw game quality. We win on **engineering**, not art.

---

## Design Principles

These are non-negotiable and referenced throughout the phases.

1. **The artifact is data, the engine is code.**
   The agent authors **content + configuration + narrowly-scoped systems**
   against a known-good runtime. The runtime is versioned, tested, and shared.
   This is the single biggest lever on reliability.

2. **Verification over vibes.**
   Nothing is "done" until `tsc`, `vite build`, and a headless browser run
   agree. Vision and "fun" critics are *advisory*; the compiler and the
   runtime are *authoritative*.

3. **Isolation is the product boundary.**
   All generated code executes in an isolated cloud sandbox (Daytona / E2B), never on the
   host. The game executes in a sandboxed iframe with no network. Two
   sandboxes, two threat models.

4. **Durability over cleverness.**
   Builds take minutes and pause for human approval. State lives in Postgres
   via the LangGraph checkpointer, not in a process. Any node must survive a
   restart and resume.

5. **Budgeted agency.**
   Every build has a token budget, a sandbox-second budget, and a wall-clock
   budget. The supervisor stops or degrades gracefully when a budget is hit.
   Unbounded agent loops are a bug, not a feature.

6. **Replaceable boundaries.**
   Sandbox vendor, LLM provider, object store, and auth are all behind
   interfaces. No vendor SDK leaks into the domain or graph layer.

7. **A real scoreboard.**
   Success is measured — % of builds that run, % that are winnable,
   spec-compliance rate, median time-to-playable, cost per build. Logged
   automatically, shown in CI. Not vibes.

8. **Scope ladder, not monolith.**
   Every phase ends in something runnable and demoable. You can stop after any
   phase and still have a portfolio artifact.

9. **Own your data.**
   Memory, checkpoints, and generated games live in our own Postgres and R2.
   No lock-in to a vendor's proprietary memory store.

---

## Glossary

| Term | Meaning |
|---|---|
| **Execution sandbox** | Server-side isolated container/microVM where agent-generated code builds/tests (Daytona / E2B). |
| **Runtime sandbox** | Browser `<iframe>` where the finished game runs for the user. |
| **GDD** | Game Design Document — the structured spec the Designer agent emits. |
| **Engine Kit** | Our fixed, tested Phaser + Vite + TS runtime that agents target. |
| **Starter** | A named Engine Kit + genre-specific modules (`topdown-shooter`). |
| **Toolbox** | The set of tools the agents can call inside the sandbox. |
| **Skill** | Progressive-disclosure domain knowledge (e.g. `platformer-fundamentals`). |
| **Build** | One end-to-end generation attempt producing an artifact + verify report. |
| **Verify Report** | Structured result of static + runtime checks for a build. |
| **Trace** | The LangSmith run tree for a build (steps, tool calls, tokens, cost). |
| **Playtrace** | A user-facing timeline of how a build was made (screenshots + steps). |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           Interfaces                                  │
│   Web Studio (Next.js)        Public Play Page (iframe)      CLI      │
└───────────────┬───────────────────────────┬──────────────────────────┘
                │  REST + SSE/WebSocket      │  static artifact (R2/CDN)
┌───────────────▼───────────────────────────▼──────────────────────────┐
│                           API layer (FastAPI)                         │
│  auth · orgs · projects · builds · approvals · quotas · play · webhooks│
└───────────────┬──────────────────────────────────────────────────────┘
                │  enqueue / stream
┌───────────────▼──────────────────────────────────────────────────────┐
│                     RIFT CORE (Python, async)                          │
│                                                                        │
│  domain/    → Org, User, Project, Build, Artifact, Verdict, Quota      │
│  studio/    → LangGraph supervisor graph + nodes                       │
│  agents/    → designer, architect, coder (deep agent), repair, critics │
│  toolbox/   → tool registry (deterministic + generative)               │
│  skills/    → progressive-disclosure game-domain skills                │
│  engine/    → Engine Kit + starters (Phaser/Vite/TS)                   │
│  sandbox/   → SandboxProvider interface (daytona/e2b/local)            │
│  verify/    → static checks + Playwright runtime harness + graders     │
│  memory/    → checkpointer (Postgres) + store (Postgres, pgvector)     │
│  evals/     → golden prompts, graders, scoreboard                      │
│  llm/       → provider-agnostic model layer + routing + fallbacks      │
└───────────────┬──────────────────────────────────────────────────────┘
                │
   ┌────────────┼────────────┬──────────────┬─────────────────┐
   ▼            ▼            ▼              ▼                 ▼
 Postgres    Upstash      Daytona/E2B   Cloudflare R2     LangSmith
 (Neon)      (Redis+QStash)(sandboxes)  (artifacts)       (traces/evals)
```

**Non-negotiable rule:** `domain/` and `studio/` have **zero** vendor SDK
imports. Sandbox, storage, LLM, and messaging are reached only through
interfaces defined in `rift.core.ports`.

---

## Target Repository Structure

A monorepo. Python backend + agents, TypeScript frontend + engine kit.

```
rift/
├─ apps/
│  ├─ web/                      # Next.js 16 · React 19 · Tailwind 4 · shadcn
│  │  ├─ app/                   #   routes: studio, project, play, settings
│  │  ├─ components/            #   BuildTimeline, PreviewFrame, Playtrace
│  │  ├─ lib/                   #   api client, sse, zod schemas, auth
│  │  └─ package.json
│  ├─ api/                      # FastAPI: HTTP surface + SSE
│  │  └─ rift_api/
│  └─ worker/                   # LangGraph runtime + schedulers
│     └─ rift_worker/
├─ packages/
│  ├─ engine-kit/               # Phaser + Vite + TS runtime (the fixed engine)
│  │  ├─ runtime/               #   main tsc, scene mgr, input, HUD, audio, save
│  │  ├─ modules/               #   opt-in systems (player, enemies, scoring…)
│  │  ├─ starters/              #   topdown-shooter, platformer, puzzle
│  │  └─ package.json
│  ├─ sandbox/                  # SandboxProvider interface + adapters
│  ├─ verify/                   # Playwright harness + TS config + bots
│  └─ skills/                   # game-domain skills (SKILL.md + references)
├─ src/rift/                    # Python source (uv-managed, src-layout)
│  ├─ core/
│  │  ├─ domain/                #   entities + value objects
│  │  ├─ ports/                 #   Protocols: SandboxProvider, BlobStore, …
│  │  ├─ config.py  errors.py  logging.py
│  ├─ studio/                   #   LangGraph supervisor + nodes + state
│  ├─ agents/                   #   individual agent definitions
│  ├─ toolbox/                  #   tool implementations + registry
│  ├─ verify/                   #   python-side verifiers + graders
│  ├─ memory/                   #   checkpointer + store wiring
│  ├─ evals/                    #   golden set + scoreboard runner
│  ├─ adapters/                 #   daytona.py, e2b.py, r2.py, upstash.py, llm.py
│  └─ api/                      #   FastAPI app factory (shared by apps/api)
├─ tests/                       # pytest (unit + integration + e2e)
├─ evals/                       # golden prompts + expected assertions (data)
├─ infra/
│  ├─ docker/                   #   Dockerfiles for api + worker
│  ├─ compose/                  #   local Postgres/Redis/MinIO
│  └─ deploy/                   #   northflank + vercel config
├─ docs/                        #   ADRs, runbooks, DEPLOYMENT.md
├─ pyproject.toml
├─ package.json                 # workspace root (turborepo or npm workspaces)
└─ PLAN.md
```

---

## Tech Stack

Everything below is chosen for **(a) free-tier viability, (b) LangGraph-native
fit, (c) your existing conventions** (Python `uv` + src-layout; Next.js 16 +
Tailwind 4 + shadcn). Versions are the current track as of **Oct 2026**; pin
exact versions in lockfiles at implementation time.

### Core agent layer

| Piece | Choice | Notes |
|---|---|---|
| Orchestration | **LangGraph** (`langgraph` 1.2+) | Durable state graph, `interrupt`, streaming, checkpointing |
| Framework | **LangChain** (`langchain` 1.3+, `langchain-core` 1.5+) | `create_agent`, middleware, tools, model abstraction |
| Agent harness | **Deep Agents** (`deepagents` 0.7+) | Built-in **planning tool, subagents, virtual filesystem, skills** — purpose-built for coding agents |
| Short-term memory | **`langgraph-checkpoint-postgres`** (`AsyncPostgresSaver`) | Thread-scoped state; survives restarts |
| Long-term memory | **`langgraph.store.postgres`** (`AsyncPostgresStore`) | Cross-thread; per-org style memory, reusable assets; pgvector semantic search |
| Structured output | **Pydantic v2** + `with_structured_output` | GDD, verify reports, tool I/O |
| Tracing + evals | **LangSmith** (Developer free) | Traces, datasets, graders |
| Optional managed deploy | **LangSmith Deployment** (LangGraph Platform) | Developer tier self-host: **100k nodes/mo free** |

> **Ecosystem note (important, current):** `langgraph-supervisor` and
> `langgraph-swarm` are **deprecated / unmaintained**. The recommended path is
> the **subagents pattern** (supervisor calls subagents as tools) built on
> `create_agent` + middleware, or **Deep Agents** for built-in orchestration.
> Do not start from `create_supervisor`.

### Sandbox layer

| Piece | Choice | Notes |
|---|---|---|
| Primary sandbox | **Daytona Sandboxes** (`daytona`, `langchain-daytona`) | Sub-second (`~90ms`) snapshot cold-starts; per-sandbox CPU/RAM (`Resources`); **$200 free compute credits** (no card for Tier 1: 10 vCPU / 10 GiB RAM / 30 GiB storage); native `deepagents` backend |
| Interface | `SandboxProvider` (Protocol) | Vendor-neutral |
| Alternates | **E2B** (`e2b` Firecracker microVMs, $100 one-time credit, up to 8 GiB RAM via template, 20 concurrent), **Northflank Sandboxes** (Kata/gVisor), **self-host** (gVisor on Oracle Always Free) | Swap via config |
| Hardening (optional) | `agentsh-secure-sandbox` | seccomp/Landlock/network-proxy/DLP for LangChain agents |

### App / data layer

| Piece | Choice | Free tier |
|---|---|---|
| API | **FastAPI + Uvicorn** (SSE + WebSocket) | — |
| Python | **3.13/3.14**, packaged with **uv** | — |
| ORM / migrations | **SQLAlchemy 2.0 (async)** + **Alembic** (`asyncpg`) | — |
| Validation / settings | **Pydantic v2** + **pydantic-settings** | — |
| Database | **Neon Postgres + pgvector** | 100 projects, 100 CU-hrs/proj/mo, 1 GB storage/proj, scale-to-zero 5 min; **pgvector on all plans**; **Managed Better Auth (60k MAU)**; 5 GB object storage |
| Cache / locks | **Upstash Redis** | 250 MB, 500K cmds/mo |
| Scheduling / queues | **Upstash QStash** | 1,000 msgs/day, 7-day delays |
| Object storage | **Cloudflare R2** (S3-compatible) | 10 GB, 1M writes / 10M reads, no egress |
| Auth | **Neon Managed Better Auth** (default) or **Clerk** | 60k MAU included with Neon |
| Observability | **LangSmith** + **OpenTelemetry** | 5k traces/mo free |

### Frontend / game layer

| Piece | Choice | Notes |
|---|---|---|
| Framework | **Next.js 16** (App Router), **React 19** | Matches black-box/codex |
| Styling | **Tailwind 4**, **shadcn**, **class-variance-authority**, **clsx**, **tailwind-merge** | |
| State / data | **zustand 5**, **@tanstack/react-query 5** | |
| Validation | **zod 4** | Schema parity with Pydantic |
| 2D engine | **Phaser 3** (primary), **Kaplay** (alt) | Vast API surface = best LLM coverage |
| Build toolchain | **Vite + TypeScript + pnpm** | For generated projects |
| Runtime verify | **Playwright** (Python + Node) | Headless Chromium |

---

## The Two Kinds of Sandbox

Most people conflate these. Keeping them separate is half the architecture.

| | **Execution sandbox** | **Runtime sandbox** |
|---|---|---|
| Runs | Agent-generated code: install, typecheck, build, tests | The finished game the **user** plays |
| Where | Daytona / E2B cloud sandbox (server-side) | Browser `<iframe>` |
| Isolation | gVisor/VM microVM, own kernel or syscall interception | `sandbox` attr + strict CSP, no network, no same-origin |
| Lifetime | Ephemeral (per build), ≤ few minutes | Static artifact, served forever, zero compute |
| Cost | The **only** real cost center | ~$0 (runs on the user's machine) |
| Threat | Malicious/buggy generated code, npm supply chain | Malicious game trying to exfiltrate / phone home |

**The core move:** build and verify in the **execution sandbox**; export a
**static bundle**; play it in the **runtime sandbox**. This makes play free and
safe while keeping all codegen isolated. It is also exactly what
Lovable / Bolt / v0 do (build in a sandbox, publish a static preview).

---

## Domain Model

Pure Python dataclasses / Pydantic models in `src/rift/core/domain/`.

```
Org           — id, name, slug, plan, created_at
User          — id, email, name, auth_subject
Membership    — org_id, user_id, role (owner|admin|member|viewer)

Project       — id, org_id, name, slug, engine, current_build_id, visibility
Build         — id, project_id, prompt, status, engine, starter,
                gdd (jsonb), plan (jsonb), artifact_key, verify_report,
                scores (jsonb), cost (jsonb), created_by, thread_id,
                parent_build_id (for refinements), created_at, finished_at
Artifact      — build_id, kind (static_bundle|screenshot|playtrace|source),
                storage_key, content_type, bytes, hash
SandboxSession— id, build_id, provider, provider_ref, status, started_at,
                ended_at, seconds, vcpu, memory_mib
UsageEvent    — id, org_id, build_id, kind (tokens|sandbox_seconds|egress),
                amount, unit, meta, created_at
AuditEvent    — id, org_id, actor, action, target, meta, created_at

Verdict       — structured result passed between agents:
                { static: {typecheck, lint, build}, runtime: {boots, errors[],
                  canvas, interactive, winnable, softlock}, critique: {vision,
                  spec_compliance, score} }
Quota         — org_id, period, tokens_limit, tokens_used,
                sandbox_seconds_limit, sandbox_seconds_used,
                max_concurrent_sandboxes
```

**Invariants**
- A `Build` belongs to exactly one `Project` and one `Org`.
- `thread_id` is the LangGraph thread; equals the build id (≤255 chars for
  `PostgresSaver`).
- Every `UsageEvent` is idempotent on `(build_id, kind, dedupe_key)`.
- `Artifact.hash` is content-addressed; publishing is idempotent.

---

## Data Model

Postgres (Neon). Alembic migrations. All tenant tables carry `org_id` and are
row-scoped by the API layer (see Security).

```sql
-- Identity & tenancy
orgs            (id pk, name, slug unique, plan, created_at)
users           (id pk, email unique, name, auth_subject unique, created_at)
memberships     (org_id fk, user_id fk, role, primary key(org_id,user_id))

-- Product
projects        (id pk, org_id fk, name, slug, engine, visibility,
                 current_build_id, created_at, unique(org_id,slug))
builds          (id pk, project_id fk, org_id fk, prompt, status, engine,
                 starter, gdd jsonb, plan jsonb, verify_report jsonb,
                 scores jsonb, cost jsonb, thread_id, parent_build_id,
                 created_by fk, created_at, finished_at)
artifacts       (id pk, build_id fk, kind, storage_key, content_type,
                 bytes, hash, created_at)
sandbox_sessions(id pk, build_id fk, provider, provider_ref, status,
                 started_at, ended_at, seconds, vcpu, memory_mib)

-- Governance
usage_events    (id pk, org_id fk, build_id fk, kind, amount, unit,
                 dedupe_key, meta jsonb, created_at, unique(build_id,kind,dedupe_key))
quotas          (org_id pk, period, tokens_limit, tokens_used,
                 sandbox_seconds_limit, sandbox_seconds_used,
                 max_concurrent_sandboxes)
audit_events    (id pk, org_id fk, actor, action, target, meta jsonb, created_at)

-- Long-term memory / retrieval (pgvector)
memories        (id pk, org_id fk, namespace text[], key, value jsonb,
                 embedding vector(1536), created_at)
asset_index     (id pk, org_id fk, kind, prompt, storage_key,
                 embedding vector(1536), created_at)
```

**LangGraph tables** are created by `AsyncPostgresSaver.setup()` /
`AsyncPostgresStore.setup()` (checkpoints, checkpoint_writes, checkpoint_blobs,
store). Point the checkpointer at the **pooled** Neon connection string
(`-pooler` host) to avoid `max_connections` exhaustion.

**Indexes:** `builds(project_id, created_at desc)`,
`usage_events(org_id, created_at)`, HNSW on `memories.embedding` and
`asset_index.embedding`.

---

## The Agent Studio (LangGraph)

This is the heart of the project. One **supervisor graph** orchestrates a set
of **specialist subagents** plus **deterministic nodes** (verify, publish).

### Topology

```
                    ┌─────────────────────────┐
        prompt ───► │        SUPERVISOR        │◄──── budget guard
                    │  (Director / planner)    │
                    └────────────┬─────────────┘
        ┌──────────────┬─────────┼──────────┬───────────────┐
        ▼              ▼         ▼          ▼               ▼
   ┌─────────┐   ┌──────────┐ ┌────────┐ ┌────────┐  ┌───────────┐
   │ DESIGNER│   │ ARCHITECT│ │ CODER  │ │ VISUAL │  │ HUD/UX    │
   │ prompt  │   │ starter  │ │ (deep  │ │ sprite │  │ menus,    │
   │ → GDD   │   │ + plan   │ │ agent) │ │ + look │  │ HUD, a11y │
   └─────────┘   └──────────┘ └────────┘ └────────┘  └───────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    ▼                              ▼
            ┌───────────────┐              ┌───────────────┐
            │  VERIFY (det) │◄── loop ─────│ REPAIR (agent)│
            │ tsc/build/run │              │ fix failures  │
            └───────┬───────┘              └───────────────┘
                    ▼
            ┌───────────────┐    ┌───────────────┐   ┌────────────┐
            │ CRITIQUE (det │    │ APPROVE (HITL │   │ PUBLISH    │
            │ + vision LLM) │──► │  interrupt)   │──►│ (det) → R2 │
            └───────────────┘    └───────────────┘   └────────────┘
```

**Deterministic nodes** (`verify`, `publish`, budget checks, routing) are plain
Python. **Agentic nodes** are LLM-driven. Keeping verification deterministic is
what makes the scoreboard trustworthy.

### State (`StudioState`)

```python
from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages

class StudioState(TypedDict, total=False):
    # identity
    org_id: str; user_id: str; project_id: str; build_id: str
    thread_id: str
    # inputs
    prompt: str
    engine: str                      # "phaser"
    starter: str | None
    # design
    gdd: dict                        # validated GDD (Pydantic-dumped)
    plan: list[dict]                 # task list w/ module ownership
    # execution
    sandbox_ref: str | None          # provider sandbox id
    files: dict[str, str]            # virtual fs manifest (path -> hash)
    artifacts: list[dict]
    # verification
    verify_report: dict | None
    critique: dict | None
    # control
    attempts: int
    max_attempts: int
    budget: dict                     # tokens, sandbox_seconds, wall_clock
    failures: list[dict]
    status: Literal["designing","building","verifying","repairing",
                    "awaiting_approval","published","failed","budget_exceeded"]
    messages: Annotated[list, add_messages]
```

### Nodes

| Node | Kind | Responsibility | Tools |
|---|---|---|---|
| `design` | agent | prompt → **GDD** (structured, scoped, testable) | — |
| `architect` | agent | pick starter, produce **task plan** with module ownership | sandbox boot, list starters |
| `scaffold` | det | materialize Engine Kit + starter into sandbox | file write |
| `implement` | agent (subagents) | write/modify modules per plan task | toolbox file + code tools |
| `assets` | agent | sprites, tileset, palette, SFX/music | generative asset tools |
| `hud` | agent | HUD/menu/tutorial/accessibility | HUD tools |
| `integrate` | det | resolve exports/imports, wire modules | tsc, build |
| `static_verify` | det | `tsc --noEmit`, `eslint`, `vite build` | verify harness |
| `runtime_verify` | det | boot headless, console, input, screenshot | Playwright |
| `critique` | det + LLM | vision critique + spec compliance | screenshot, gdd |
| `repair` | agent | turn failures into a patch; bounded retries | coder + verify |
| `route` | det | decide next based on verdict + budgets | — |
| `await_approval` | HITL | `interrupt()` surfacing preview + diff | — |
| `publish` | det | export `dist/` → R2 (content-addressed) | blob store |
| `record` | det | persist scores, usage events, playtrace | — |

### Deep Agents usage

The **`implement`** (and **`repair`**) step is where coding happens. We use
**Deep Agents** because it ships exactly what a coding subagent needs:

- **Planning tool** — a persistent TODO list the coder maintains across turns.
- **Subagents** — the supervisor spawns isolated workers per module, so context
  doesn't bloat (the "dumb zone" problem).
- **Virtual filesystem** — file read/write/edit/ls/search **without** a real FS
  dependency (backed by the sandbox).
- **Skills** — progressive-disclosure domain knowledge loaded on demand.

**Context modes for subagents** (Deep Agents / LangChain current API):

| Mode | Behavior | Use for |
|---|---|---|
| `"isolated"` (default) | Fresh context; only the task description | Most modules (context isolation) |
| `"fork"` | Inherits supervisor conversation (prompt-cache friendly) | Modules needing prior design context |

**Subgraph persistence modes** (per LangGraph docs):

| Mode | `checkpointer=` | Use for |
|---|---|---|
| per-invocation (default) | `None` | Stateless, parallel-safe subagents |
| per-thread | `True` | A subagent needing its own multi-turn memory (**add `ToolCallLimitMiddleware`** to avoid parallel-checkpoint conflicts) |
| stateless | `False` | Pure, side-effect-free helpers |

### Orchestration patterns we exploit

(From Deep Agents' dynamic-subagent patterns — used deliberately per step.)

- **Fanout and synthesize** — `implement` fans out one coding subagent per
  module in parallel, then `integrate` synthesizes.
- **Adversarial verification** — `critique` is an *independent* judge of work
  the coders produced; false positives (a game that "looks done") are costly.
- **Generate and filter** — for visual variants, generate N, score, keep best.
- **Loop until done** — the `verify → repair` cycle, bounded by `max_attempts`
  and budget.

### Human-in-the-loop

`await_approval` uses LangGraph's `interrupt()` / `Command(resume=...)`.

The resume payload can be:
- `{"action":"approve"}` — publish as-is.
- `{"action":"edit","instructions":"make the player faster"}` — loop back to
  `implement`/`repair` with new instructions.
- `{"action":"reject","reason":"wrong genre"}` — back to `design`.

**Interrupt rules (non-negotiable, from LangGraph semantics):**
1. Never wrap `interrupt()` in `try/except` (it raises a control-flow signal).
2. Never reorder `interrupt()` calls within a node (resume matches positionally).
3. Keep resume payloads small and JSON-serializable.
4. **Side effects before an `interrupt()` must be idempotent** — resume
   re-executes the node from the top.

### Durability

- `AsyncPostgresSaver` on Neon (pooled connection).
- A **checkpoint retention job** (cron via QStash/Northflank) prunes old
  checkpoints — they grow unboundedly otherwise.
- `thread_id` = `build_id`, kept ≤255 chars.
- Builds resume correctly after a worker restart or deploy mid-run.

---

## The Game Dev Toolbox

Tools live in `src/rift/toolbox/`, registered into the agents. Split into
**deterministic** (reliable, testable, no LLM) and **generative** (asset models).

| Domain | Deterministic tools | Generative tools |
|---|---|---|
| **Scaffold** | `list_starters()`, `create_from_starter(engine, starter)` | — |
| **Files** | `read_file`, `write_file`, `edit_file`, `list_files`, `search_code` | — |
| **Build** | `install_deps`, `typecheck`, `lint`, `build`, `run_preview` | — |
| **Verify** | `run_headless`, `get_console`, `screenshot`, `simulate_input`, `wait_for_ready`, `diff_screenshots` | `interpret_trace` |
| **Design** | `validate_gdd`, `estimate_scope` | `propose_mechanics`, `design_level_spec` |
| **HUD/UX** | `add_hud(layout)`, `add_menu()`, `add_tutorial()`, `add_settings()` | `design_ui_theme` |
| **Controls** | `bind_input(scheme)`, `add_rebinding()`, `map_gamepad()`, `add_touch_controls()` | — |
| **Visuals** | `set_palette()`, `add_camera()`, `set_resolution()`, `add_particles()` | `generate_sprite(prompt)`, `generate_tileset()`, `generate_animation()` |
| **Physics** | `add_arcade_body()`, `add_collision()`, `add_gravity()`, `add_platformer_body()` | — |
| **Audio** | `bind_sfx(event)`, `add_music_track()`, `set_audio_bus()` | `generate_sfx()`, `generate_soundtrack()` |
| **Content** | `add_scene()`, `add_level(data)`, `spawn_entity()`, `set_difficulty()` | — |
| **Data** | `add_save_load()`, `add_scoreboard()` | — |
| **Package** | `bundle()`, `export_dist()`, `publish_artifact()` | — |

**Design rule:** prefer a deterministic tool over raw free-form code whenever
the pattern is known. Tools are versioned and unit-tested; free-form edits are
allowed only for genuinely novel mechanics, and always go through `verify`.

**Skills** (`packages/skills/`) — progressive disclosure, loaded on demand:
`platformer-fundamentals`, `topdown-shooter`, `puzzle-logic`, `juice-and-feel`,
`hud-ux-guidelines`, `phaser-patterns`, `accessibility`, `balancing`. Each is a
`SKILL.md` + reference snippets + bound tools.

---

## The Engine Kit

`packages/engine-kit/` is **our fixed, tested runtime**. Agents mostly author
*content + config + narrow systems*; the runtime provides the rest. This is the
single biggest reliability lever.

```
engine-kit/
├─ runtime/
│  ├─ main.ts            # boot, canvas, scaling, game loop
│  ├─ scenes.ts          # scene manager (menu/game/pause/gameover)
│  ├─ input.ts           # input abstraction (kb/mouse/touch/gamepad)
│  ├─ hud.ts             # HUD framework (declarative layout)
│  ├─ audio.ts           # audio bus (music/sfx/mute)
│  ├─ save.ts            # localStorage save/load + settings
│  ├─ assets.ts          # loader + atlas support
│  ├─ debug.ts           # `window.__RIFT__` test hooks (see Verify)
│  └─ rng.ts             # seeded RNG (determinism)
├─ modules/              # opt-in systems, each independently testable
│  ├─ player/  enemies/  weapons/  scoring/  difficulty/
│  ├─ particles/  camera/  spawner/  pickups/
├─ starters/
│  ├─ topdown-shooter/   # scene + entities + data + tests baseline
│  ├─ platformer/
│  └─ puzzle/
└─ package.json          # pinned phaser, vite, typescript, vitest
```

**Test hooks (critical for verification):** the runtime exposes a stable,
documented interface on `window.__RIFT__`:

```ts
window.__RIFT__ = {
  ready: boolean,                 // set true once first frame renders
  state(): { score, lives, scene, win, lose, entities },
  input: { press(k), release(k), click(x,y) },
  errors: string[],               // collected console/runtime errors
}
```

Agents **may not** remove these hooks; the starter includes tests asserting they
exist. This is how `runtime_verify` inspects a game deterministically instead of
guessing from a screenshot.

---

## The Sandbox Layer (Daytona & E2B)

`SandboxProvider` is a `Protocol` in `src/rift/core/ports/`. Adapters live in
`src/rift/adapters/`.

```python
class SandboxProvider(Protocol):
    async def create(self) -> str: ...
    async def read_file(self, sandbox_id: str, path: str) -> bytes: ...
    async def write_file(self, sandbox_id: str, content: bytes, path: str) -> None: ...
    async def exec(self, sandbox_id: str, cmd: list[str]) -> ExecResult: ...
    async def terminate(self, sandbox_id: str) -> None: ...
```

### Daytona adapter details (Primary — verified Oct 2026)

- **SDK:** `AsyncDaytona` from `daytona` (plus `langchain-daytona`'s `DaytonaSandbox` for direct `deepagents` integration).
- **Creation & Snapshots:** `await daytona.create(CreateSandboxFromSnapshotParams(snapshot="rift-sandbox", auto_stop_interval=15))` or `CreateSandboxFromImageParams(image=..., resources=Resources(cpu=2, memory=4, disk=8))`.
- **Pre-baked Snapshot (`rift-sandbox`):** Pre-build a Daytona snapshot (or custom Docker image) baking in Node, **pnpm**, the Engine Kit, and Playwright + Chromium so sandbox creation boots in **~90ms** without rebuilding dependencies on every run.
- **Filesystem & Execution:**
  - Write file: `await sandbox.fs.upload_file(content_bytes, path)`
  - Read file: `await sandbox.fs.download_file(path)` → `bytes`
  - Execute command: `await sandbox.process.exec(cmd_str, timeout=...)`
- **Lifecycle:** Always call `await daytona.delete(sandbox)` in a `finally` block; configure `auto_stop_interval` and `auto_delete_interval` so stuck sandboxes never leak credits.
- **Secrets:** Never inject app secrets into a build sandbox.

### E2B adapter details (Secondary Fallback — `src/rift/adapters/e2b.py`)

- **SDK:** `AsyncSandbox` from `e2b`.
- **Creation:** `sb = await AsyncSandbox.create(template="rift-sandbox", timeout=600)`
- **Filesystem & Execution:**
  - Write file: `await sb.files.write(path, content)`
  - Read file: `await sb.files.read(path, format="bytes")`
  - Execute command: `await sb.commands.run(cmd_str, timeout=...)`
  - Cleanup: `await sb.kill()`

### Why Daytona is primary over E2B (and other adapters)

| Provider | Free Tier & Spec | Billing & Trade-offs |
|---|---|---|
| **Daytona (Primary)** | **$200 free credit**; Tier 1 (email verified, no card) = 10 vCPU / 10 GiB RAM / 30 GiB storage; 5 GiB free storage | Pure pay-as-you-go per second (~$0.0504/vCPU-hr, ~$0.0162/GiB-hr) with **no monthly base fee**; per-sandbox CPU/RAM (`Resources`); official `langchain-daytona` package for Deep Agents |
| **E2B (Fallback)** | **$100 one-time credit** on Hobby ($0/mo); up to 8 GiB RAM (fixed at template build); 20 concurrent; **1 hr max session** | Upgrading beyond Hobby jumps to **$150/month Pro base fee**; RAM is fixed per template rather than per sandbox |
| **Northflank Sandboxes** | Kata microVMs / gVisor | Lets us keep everything in one vendor |
| **Self-host (gVisor on Oracle Always Free)** | 2 OCPU / 12 GB, $0 forever | Long-term zero-cost escape hatch |

---

## Verification & Evaluation

Verification is the differentiator. Two layers, both deterministic first.

### Layer 1 — Static (fast, free, authoritative)

Run inside the sandbox against the generated project:

| Check | Command | Failure meaning |
|---|---|---|
| Typecheck | `tsc --noEmit` | Type errors — the most common codegen bug |
| Lint | `eslint --max-warnings=0` | Style / obvious bugs |
| Build | `vite build` | Project doesn't compile / bundle |
| Unit tests | `vitest run` | Logic broken (starter ships baseline tests) |

TypeScript is intentional: it turns "is this correct?" into a **compiler
signal** the Repair agent can iterate on autonomously.

### Layer 2 — Runtime (Playwright, headless Chromium)

```
1. serve dist/ (static) on a local port
2. launch Chromium (--no-sandbox inside microVM)
3. collect console + pageerror into a buffer
4. goto page; wait for window.__RIFT__.ready
5. assert: no uncaught errors; canvas present; state() reachable
6. simulate input (window.__RIFT__.input.press('ArrowRight'))
7. assert state changed (score/position/scene)
8. screenshot at t0, t1 → artifact
9. (optional) scripted bot: attempt to reach win/lose; detect softlock
```

Result is a structured `Verdict` (see Domain Model) stored on the build.

### Layer 3 — Critique (advisory, LLM)

- **Vision critic** — reads screenshots; judges readability, contrast, UI
  overlap, visual coherence. Emits findings, not pass/fail.
- **Spec compliance** — checks the build against the GDD (`has_hud == true`,
  `controls includes WASD`, `genre == "top-down shooter"`), scored.
- **Fun proxy** — difficulty metrics, bot session length, LLM-judge rubric.
  **Documented as a proxy**, never as ground truth.

### The scoreboard (machine-checkable, CI-gated)

| Metric | Definition | Target |
|---|---|---|
| **Runs** | boot with zero uncaught errors | ≥95% |
| **Builds** | `tsc` + `vite build` succeed | ≥90% |
| **Interactive** | input changes state | ≥85% |
| **Winnable** | scripted bot reaches win/lose | ≥70% |
| **Spec match** | GDD assertions passed / total | ≥80% |
| **Time-to-playable** | median wall-clock prompt→publish | < 5 min |
| **Cost/build** | tokens + sandbox-seconds in USD | < $0.50 |

**Golden set:** ~20 fixed prompts in `evals/golden/`, each with expected
assertions. Re-run on every change to the studio; regressions fail CI. This is
the discipline that separates senior AI engineering from prompt-tinkering.

---

## Multi-Tenancy, Quotas & Metering

### Roles

| Role | Can |
|---|---|
| `owner` | Everything, including billing and org deletion |
| `admin` | Manage members, projects, quotas |
| `member` | Create/build projects, publish |
| `viewer` | View + play only |

### Quota model (per org, per period)

- `tokens_limit` / `sandbox_seconds_limit`
- `max_concurrent_sandboxes`
- Soft limit → warn + degrade (smaller model, shorter runs). Hard limit →
  reject new builds with a clear error.

### Metering

Every agent step writes a `UsageEvent`; a rollup job updates `quotas`. Usage is
keyed on `(build_id, kind, dedupe_key)` so retries never double-count. Expose
`GET /orgs/{id}/usage` for the dashboard.

### Sandbox management

- **Warm pool / Snapshots** — use pre-built Daytona snapshots (`rift-sandbox`) for ~90ms cold starts.
- **Per-project labels** (Daytona `labels={"project_id": ...}`) — prevent duplicate concurrent
  builds on the same project.
- **TTL + auto-stop** — every sandbox sets `auto_stop_interval` and max lifetime.
- **Orphan reaper** — periodic job terminates sandboxes with no live build
  (`daytona.list()` + labels).
- **Placement** — a build gets **exactly one** sandbox; never reuse a sandbox
  across tenants.

---

## API Design

FastAPI (`src/rift/api/`). REST for state, **SSE** for live build progress.

```
Auth & tenancy
  GET    /me
  GET    /orgs                          POST /orgs
  GET    /orgs/{org}/members            POST /orgs/{org}/members
  GET    /orgs/{org}/usage

Projects & builds
  GET    /orgs/{org}/projects           POST /orgs/{org}/projects
  GET    /projects/{id}                 PATCH/DELETE /projects/{id}
  POST   /projects/{id}/builds          # { prompt, engine?, starter? } -> build
  GET    /builds/{id}
  GET    /builds/{id}/events            # SSE: node transitions, logs, screenshots
  POST   /builds/{id}/approve           # { action, instructions?, reason? }
  POST   /builds/{id}/cancel
  GET    /builds/{id}/artifacts
  GET    /builds/{id}/playtrace

Play (public, toggled per project)
  GET    /play/{project_slug}           # HTML shell + iframe
  GET    /a/{artifact_hash}/index.html  # static bundle (served from R2/CDN)

Ops
  POST   /webhooks/qstash               # scheduler callbacks
  GET    /healthz  /readyz  /metrics
```

**SSE event shapes:** `node_started`, `node_finished`, `log`, `screenshot`,
`awaiting_approval`, `published`, `failed`, `budget_warning`.

---

## Frontend Architecture

Next.js 16 App Router. Matches your black-box/codex conventions.

```
apps/web/
├─ app/
│  ├─ (marketing)/page.tsx           # landing + live demo
│  ├─ studio/new/page.tsx            # prompt → build
│  ├─ studio/[buildId]/page.tsx      # live build view
│  ├─ projects/[id]/page.tsx         # project + builds + versions
│  ├─ play/[slug]/page.tsx           # public play page
│  ├─ orgs/[slug]/settings/page.tsx  # members, roles, quotas, usage
│  └─ api/                           # rsc/proxy routes if needed
├─ components/
│  ├─ BuildTimeline.tsx              # SSE-driven step timeline
│  ├─ PreviewFrame.tsx               # sandboxed iframe + CSP
│  ├─ Playtrace.tsx                  # screenshots + step scrubbing
│  ├─ VerdictPanel.tsx               # verify + critique findings
│  ├─ RefineBar.tsx                  # "make it harder" chat
│  └─ QuotaMeter.tsx
├─ lib/
│  ├─ api.ts  sse.ts  auth.ts
│  └─ schemas.ts                     # zod (parity with Pydantic)
```

- **PreviewFrame** always renders the game in `<iframe sandbox="allow-scripts
  allow-pointer-lock">` with a strict CSP and **no network**.
- **Two entry points for approval** — inline in the timeline and in a dedicated
  review pane (image + diff + "approve / edit / reject").
- **Playtrace** is the portfolio money-shot: scrub through *how* the game was
  built (design → scaffolds → screenshots → fixes → publish).

---

## Security Model

Two threat surfaces: **generated code** (server) and **generated games**
(browser). Plus classic multi-tenant data isolation.

### Generated code (execution sandbox)
- Isolated container / microVM execution (Daytona / E2B). No host mounts. No host env/secrets.
- **Egress denied by default**; allowlist npm registry only during install.
- `pnpm install --ignore-scripts` — never run postinstall scripts.
- Pinned lockfiles; pinned Node; pinned Engine Kit → determinism + supply-chain
  safety.
- CPU/memory/wall-clock caps per sandbox. OOM/timeouts are caught, not retried
  blindly.
- Secrets never enter a build sandbox.

### Generated games (runtime sandbox)
- `<iframe sandbox>` + **strict CSP**, `no-same-origin`, no network (block
  `fetch`/`XHR`/`WebSocket`) → a malicious game can't exfiltrate or phone home.
- Artifacts are content-addressed and immutable; served from R2/CDN.

### Prompt injection
- Treat **all** model outputs, user text, and any fetched/parsed content as
  untrusted. The GDD is validated against a schema; agents act on **structured
  fields**, never on free text that could carry instructions.
- **Tool allowlist per agent** — e.g. the vision critic cannot write code; the
  Designer cannot touch the filesystem.
- No agent may escalate its own permissions or reach outside its sandbox.

### Multi-tenancy
- Every query is scoped by `org_id` from the authenticated session; no
  cross-org reads are reachable by construction.
- One sandbox per build; never shared across tenants.
- RBAC enforced in the API layer (not just the UI).
- `audit_events` for all privileged actions.

### Auth
- **Neon Managed Better Auth** (included on the free plan, 60k MAU) or Clerk.
- OAuth (Google/GitHub), magic links, sessions; org scoping on every request.

---

## Cost Model & Budget Controls

**The sandbox and the LLM are the only real costs.** Everything else is free
tier. Budgets make this safe.

### Daytona / E2B sandbox cost (per build, ~2 vCPU / 4 GiB, ~4 min)

| Resource | Rate (Oct 2026) | Build usage | Cost |
|---|---|---|---|
| CPU | ~$0.000014 / vCPU / s ($0.0504/hr) | 2 vCPU × 240 s | ~$0.0067 |
| Memory | ~$0.0000045 / GiB / s ($0.0162/GiB-hr) | 4 GiB × 240 s | ~$0.0043 |
| **Per build** | | | **~$0.011** |
| **Free credit** | **$200 (Daytona) + $100 (E2B)** | | **~18,000+ builds** |

### Controls

- Per-build caps: `max_attempts`, token budget, sandbox-second budget, wall clock.
- **Warm sandbox pool** + **named images** cut cold-start and rebuild cost.
- **Single-file vs full project** is a per-build choice: full project for the
  showcase, single-file for cheap/fast iterations.
- Model **routing**: free tier (Gemini/Groq) for design/critique; a stronger
  model for the coding step; cache prompts (fork subagents exploit prompt cache).
- **Demo mode:** a seeded "golden build" replayable from stored artifacts with
  **zero** live sandbox/LLM cost — so the public demo never depends on credits.

### Free LLM tiers (dev/demo)

| Provider | Model | Limit | Caveat |
|---|---|---|---|
| Google AI Studio | Gemini (Flash) | ~1,000–1,500 req/day | May train on data |
| Groq | gpt-oss-120b / Llama | 30 RPM, ~1k req/day, 8k TPM | Fast |
| Cerebras | gpt-oss-120b | ~1M tokens/day | 8k ctx cap |
| OpenRouter | ~25 `:free` models | 50–1,000 req/day | One key, many models |

Use free tiers for **synthetic demo** content; use a paid key (or self-host) for
real user data.

---

## Deployment Topology (Free Tier)

```
Vercel Hobby / CF Pages   → apps/web (Next.js)
Northflank free service   → apps/api  (FastAPI, "always-on, no sleeping")   ┐
Northflank free service   → apps/worker (LangGraph runtime + schedulers)    ┘ (2 services)
Northflank free database  → (optional) Redis/PG fallback
Neon free                 → Postgres + pgvector (checkpoints, store, domain)
Upstash free              → Redis (locks) + QStash (cron + durable delays)
Cloudflare R2 free        → static game bundles, screenshots, playtraces
Daytona ($200 credit)/E2B → execution sandbox (build + Playwright verify)
Gemini/Groq free          → LLM
LangSmith Developer       → traces + evals
────────────────────────────────────────────────────────────────────────────
≈ $0/month, always-on, no cold starts
```

### Why Northflank (and alternatives)

| Option | Free offer | Catch |
|---|---|---|
| **Northflank (recommended)** | **2 services + 2 cron + 1 DB, always-on (no sleeping)** | Requires a **payment method** on signup; free tier "not for production"; limited compute |
| Render | 750 hrs/mo web services | **Sleeps after 15 min**; free Postgres **expires in 30 days** |
| Fly.io | none for new accounts | ~$2–7/mo |
| Railway | $1/mo credit | Effectively unusable for a worker |
| Cloudflare Workers | generous free | Different execution model; not ideal for a long-running LangGraph worker |
| **Oracle Cloud Always Free** | 2 OCPU / 12 GB VM, **$0 forever** | More setup; you own the OS + sandbox isolation |
| Hugging Face Spaces | free Docker | Sleeps; ephemeral FS; not a backend |

**Decision:** Northflank free for `api` + `worker` (two services, always-on).
Fallback if the card requirement blocks you: **Oracle Always Free VM** running
Docker Compose (API + worker + Redis), which also becomes the **self-hosted
sandbox** once Daytona/E2B credits matter. Keep `SandboxProvider` swappable for this.

### Scheduler / durable waits

Replace Celery beat entirely:
- **QStash** for cron (retention jobs, orphan reaping, quota rollups) and for
  any multi-minute deferred work — callbacks hit the API.
- LangGraph checkpointer + QStash means **no always-on process is strictly
  required** for durability, though Northflank's always-on service keeps it
  responsive.

### Local development

`infra/compose/` runs Postgres (+pgvector), Redis, and MinIO (R2 substitute) so
you develop without touching cloud services. A `local` `SandboxProvider` runs
builds in a local container for fast iteration (clearly marked dev-only).

---

## Engineering Standards

- **Ruff** + **Pyright** (strict) for Python; **ESLint** + **Prettier** +
  **tsc** for TS; both enforced in CI.
- **Pytest** (`pytest-asyncio`) for backend/agents; **Vitest** for engine kit;
  **Playwright** for e2e.
- **Conventional commits**, small PRs, one phase per milestone branch.
- **Typed everything** — Pydantic models and TS types; zod schemas mirror
  Pydantic (single source of truth where possible).
- **Idempotency** — publishing, usage events, and webhooks are all retry-safe.
- **Structured logging** (JSON) with `build_id`/`org_id` correlation.
- **Config via `pydantic-settings`**; no secrets in code; `.env.example` kept
  current.
- **ADRs** in `docs/adr/` for every irreversible decision (sandbox vendor, auth
  provider, engine choice).
- **No vendor SDK in `core/`** — adapters only. Enforced by an import-linter
  rule in CI.

---

## Phased Roadmap

Each phase ends in a runnable artifact and a demo. "DoD" = Definition of Done.

### Phase 0 — Foundation & Scaffold

**Goal:** a working monorepo skeleton, CI, and local infra.

- [ ] Initialize uv Python project `src/rift/`, Python 3.13/3.14, pyproject +
      dependency groups (`dev`, `agents`, `sandbox`, `web`).
- [ ] Initialize npm workspace root; `apps/web` (Next.js 16 + Tailwind 4 +
      shadcn), `packages/engine-kit` skeleton.
- [ ] `core/` split: `domain/`, `ports/`, `config.py`, `errors.py`, `logging.py`.
- [ ] `infra/compose/` — Postgres+pgvector, Redis, MinIO.
- [ ] CI: ruff, pyright, pytest, eslint, tsc, vitest.
- [ ] ADR-0001: sandbox vendor = Daytona (with E2B fallback + rationale).
- [ ] Import-linter rule: `core/` may not import adapters/vendor SDKs.

**DoD:** `uv run pytest` + `npm run build` pass in CI on an empty-but-real
skeleton; `docker compose up` yields Postgres/Redis/MinIO.

---

### Phase 1 — Domain Model & Data Layer

**Goal:** the database is real, migrations run, repository layer works.

- [ ] Pydantic domain models (Org, User, Membership, Project, Build, Artifact,
      SandboxSession, UsageEvent, AuditEvent, Quota, Verdict).
- [ ] SQLAlchemy 2.0 async models + Alembic initial migration (schema in
      [Data Model](#data-model)); enable `pgvector`.
- [ ] Repositories for each aggregate (async, org-scoped).
- [ ] Settings via `pydantic-settings`; `.env.example`.
- [ ] Seed script for local dev (org + user + project).

**DoD:** migrations apply cleanly to Neon and local; repository CRUD covered by
tests; `org_id` scoping enforced and tested.

---

### Phase 2 — Sandbox Layer + Engine Kit

**Goal:** we can create a sandbox, scaffold a game, build it, and screenshot it.

- [ ] `SandboxProvider` Protocol + `DaytonaSandboxProvider` adapter (plus optional `E2BSandboxProvider` fallback)
      (create/exec/write_file/read_file/terminate).
- [ ] Create a **pre-baked Daytona snapshot / image** (`rift-sandbox`) baking Node + pnpm +
      Engine Kit + Playwright/Chromium.
- [ ] `local` dev provider (Docker) behind the same interface.
- [ ] **Engine Kit runtime** (`runtime/` modules) + `topdown-shooter` starter
      with `window.__RIFT__` hooks and baseline `vitest` tests.
- [ ] `create_from_starter` + `install_deps` + `build` tools working end-to-end
      inside a sandbox.
- [ ] Sandbox lifecycle: timeout, idle timeout, `finally` terminate, tags.

**DoD:** from a clean state, a script creates a sandbox, scaffolds
`topdown-shooter`, installs, builds, serves `dist/`, screenshots it, and tears
the sandbox down — all in one integration test.

---

### Phase 3 — Single-Agent MVP (prompt → playable)

**Goal:** the thinnest possible end-to-end loop. One genre. One agent.

- [ ] `StudioState` + a minimal LangGraph `StateGraph`:
      `design → scaffold → implement → static_verify → publish`.
- [ ] `design` node: prompt → validated **GDD** (Pydantic).
- [ ] `implement` node: a single **Deep Agents** coder that authors content +
      config against the starter (uses the planning tool + virtual FS).
- [ ] `publish` node: export `dist/` → **R2** (content-addressed) → return URL.
- [ ] CLI: `rift build "<prompt>"` prints a playable URL.
- [ ] `AsyncPostgresSaver` checkpointer wired (durability from day one).

**DoD:** `rift build "a top-down shooter where I dodge red squares"` produces a
game that boots and is playable in a browser, with a real R2 URL, and the build
survives a worker restart mid-run.

---

### Phase 4 — Verification Harness

**Goal:** trustworthy, deterministic verification. **This is the flagship phase.**

- [ ] Static verifier: `tsc --noEmit`, `eslint`, `vite build`, `vitest` →
      structured results.
- [ ] Playwright harness (`packages/verify/`): serve `dist/`, boot Chromium,
      collect console/pageerrors, wait for `window.__RIFT__.ready`, assert state,
      simulate input, screenshot t0/t1.
- [ ] `runtime_verify` node → `Verdict`.
- [ ] Persist `verify_report` on the build; store screenshots as artifacts.
- [ ] Deterministic seeds surfaced in the GDD and used by tests.

**DoD:** every build has a `Verdict` with static + runtime results; a
deliberately-broken game **fails** verification with an actionable report.

---

### Phase 5 — Repair Loop & Guardrails

**Goal:** the studio fixes its own failures, safely.

- [ ] `repair` node: consumes `Verdict.failures` → patch → re-`verify`.
- [ ] Bounded loop: `max_attempts` + budgets; explicit `budget_exceeded` state.
- [ ] Failure taxonomy (type error, build error, console error, no-input-effect,
      softlock) with tailored prompts per class.
- [ ] Tool allowlist per agent; no agent can widen its own permissions.
- [ ] Usage metering written on every step (`UsageEvent`).

**DoD:** a prompt known to produce a bug is automatically detected, repaired,
and published green, within budget, with the repair visible in the trace.

---

### Phase 6 — Multi-Agent Studio

**Goal:** specialist subagents + a supervisor; parallel module work.

- [ ] Restructure into a supervisor graph with subagents:
      Designer, Architect, **Coder** (deep agent), **Visual**, **HUD/UX**,
      Integrator, Repair, Critics.
- [ ] Subagents-as-tools; `isolated` vs `fork` context modes chosen per module.
- [ ] **Fanout-and-synthesize** for `implement` (one coder per module).
- [ ] `adversarial verification`: independent `critique` node.
- [ ] `integrate` node: resolve imports/exports; run `tsc` to catch mismatches.
- [ ] Per-agent model routing (free model for design/critique; stronger for
      coding).

**DoD:** a build shows ≥3 subagents in parallel in the trace; quality and
spec-match improve over Phase 3 on the golden set.

---

### Phase 7 — Toolbox & Skills

**Goal:** the "tools installed in the agent" become a real, versioned library.

- [ ] Implement the full [Toolbox](#the-game-dev-toolbox) (deterministic first).
- [ ] Tool registry with JSON schemas + per-agent binding.
- [ ] **Skills** package: `platformer-fundamentals`, `topdown-shooter`,
      `puzzle-logic`, `juice-and-feel`, `hud-ux-guidelines`, `phaser-patterns`,
      `accessibility` — progressive disclosure.
- [ ] Skill loading wired into Deep Agents; only load skills the GDD implies.
- [ ] Unit tests for every deterministic tool (against the Engine Kit).

**DoD:** adding a new module (e.g. `weapons`) is done by the agent via tools +
a skill, not by free-form invention, and passes verification.

---

### Phase 8 — HITL & Refinement

**Goal:** humans steer; the graph pauses and resumes reliably.

- [ ] `await_approval` node via `interrupt()`; resume with `Command(resume=...)`.
- [ ] Approval actions: approve / edit(+instructions) / reject(+reason).
- [ ] Refinement: `parent_build_id` lineage; user follow-ups ("make it harder",
      "add a boss") re-enter `implement`→`verify` without regressing.
- [ ] Idempotency guards around all pre-interrupt side effects.
- [ ] SSE events `awaiting_approval` + `resumed`.

**DoD:** a build pauses for approval, resumes hours later after a restart, and
applies an edit instruction correctly.

---

### Phase 9 — Durability & Scheduling

**Goal:** production-grade reliability and background jobs.

- [ ] `AsyncPostgresStore` for long-term memory (style prefs, reusable assets)
      with pgvector semantic search.
- [ ] **Checkpoint retention job** (QStash cron) — prune old checkpoints.
- [ ] **Orphan sandbox reaper** (QStash cron) — terminate idle sandboxes.
- [ ] **Quota rollup job** (QStash cron) — aggregate `usage_events` → `quotas`.
- [ ] Multi-minute deferred steps via QStash callbacks.
- [ ] Crash/deploy resilience tests (kill worker mid-build → resumes).

**DoD:** a build survives a mid-run deploy; scheduled jobs run on QStash; store
retrieval improves style consistency across a project.

---

### Phase 10 — API & Streaming

**Goal:** the full HTTP surface + live progress.

- [ ] All [API Design](#api-design) endpoints; org-scoped, RBAC-enforced.
- [ ] SSE stream of build progress (`node_started/finished`, `log`,
      `screenshot`, `awaiting_approval`, `published`, `failed`).
- [ ] Artifact serving (signed or public URLs from R2/CDN).
- [ ] `/play/{slug}` HTML shell + iframe; per-project visibility toggle.
- [ ] Webhook receiver for QStash; idempotent handlers.
- [ ] OpenAPI published; contract tests.

**DoD:** a client can create a project, start a build, watch it live over SSE,
approve it, and play the result — entirely via the API.

---

### Phase 11 — Frontend Studio

**Goal:** the product surface that makes the demo land.

- [ ] Prompt → build flow; live **BuildTimeline** (SSE).
- [ ] **PreviewFrame** (sandboxed iframe + CSP) with hot reload on new builds.
- [ ] **VerdictPanel** (static/runtime/critique findings, screenshots).
- [ ] **RefineBar** (chat-style refinements → new build).
- [ ] **Playtrace** viewer (the portfolio money-shot).
- [ ] Project pages, build history, public play page, gallery.
- [ ] Auth (Better Auth/Clerk) + org context.

**DoD:** a non-technical person can go from prompt to publishing a game in the
UI, and a visitor can play it from a public URL.

---

### Phase 12 — Multi-Tenancy & Governance

**Goal:** orgs, roles, quotas — the "real SaaS" layer.

- [ ] Orgs + memberships + RBAC (owner/admin/member/viewer).
- [ ] Quota enforcement (tokens, sandbox-seconds, concurrency) with soft/hard
      limits and graceful degradation.
- [ ] Usage dashboard (`QuotaMeter`), audit log.
- [ ] Per-org isolation tests (attempt cross-org access → denied).
- [ ] Invite flow.

**DoD:** two orgs operate in complete isolation; hitting a quota degrades or
blocks cleanly with a clear message.

---

### Phase 13 — Sandbox Management at Scale

**Goal:** sandbox lifecycle predictable and cheap.

- [ ] **Warm pool / pre-built snapshots** of sandboxes.
- [ ] Labeled sandboxes per project (prevent duplicate concurrent builds).
- [ ] TTL + auto-stop timeouts tuned; per-build resource profiles.
- [ ] Provider failover: Daytona → E2B → self-host (config-driven).
- [ ] Self-host adapter (gVisor on a free VM) implemented behind the interface.
- [ ] Sandbox cost dashboard.

**DoD:** cold-start latency drops measurably; killing Daytona access fails over to E2B
without code changes.

---

### Phase 14 — Assets & Richer Games

**Goal:** games that look and sound good, still reliably.

- [ ] Generative asset pipeline: sprites, tilesets, palettes, SFX, music —
      cached and content-addressed in R2 + `asset_index` (pgvector).
- [ ] **Style-coherence** pass (one palette/art-direction enforced across
      assets).
- [ ] Tilemaps (Tiled JSON), sprite atlases, camera, particles, juice.
- [ ] Add `platformer` and `puzzle` starters; expand golden set across genres.
- [ ] IP-safety notes (generated-asset provenance) documented.

**DoD:** multi-genre generation; visual coherence score improves; asset reuse
across a project's builds is measurable.

---

### Phase 15 — Evals, CI Gate & Polish

**Goal:** prove quality, then make it presentable.

- [ ] `evals/golden/` (~20 prompts) with assertions; **CI gate** on the
      [Evaluation Scoreboard](#evaluation-scoreboard).
- [ ] LangSmith datasets + graders wired; regression report per PR.
- [ ] **Demo mode**: stored golden build replayable with zero live cost.
- [ ] README led by the studio diagram, a self-repair trace, and the scoreboard.
- [ ] `DEPLOYMENT.md` (Northflank + Vercel + Neon + Upstash + R2 + Daytona/E2B).
- [ ] Load sanity check; error budgets; runbooks in `docs/`.

**DoD:** CI fails on a scoreboard regression; a visitor lands on a working demo
URL that never sleeps and costs nothing to view.

---

## Evaluation Scoreboard

Recomputed per PR from the golden set; the headline number in the README.

| Metric | v0.1 target | v1.0 target |
|---|---|---|
| Runs (no uncaught errors) | 70% | 95% |
| Builds (tsc + vite) | 60% | 90% |
| Interactive (input works) | 50% | 85% |
| Winnable (bot) | 30% | 70% |
| Spec match (GDD) | 50% | 80% |
| Median time-to-playable | < 10 min | < 5 min |
| Median cost per build | < $0.50 | < $0.25 |

---

## Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | Integration breakage across modules | High | High | Engine Kit + `integrate` node + `tsc` as a hard gate |
| 2 | Agent loop burns budget/time | High | High | Hard budgets, `max_attempts`, early stopping, fail-fast |
| 3 | "Fun"/quality can't be auto-judged | Certain | Med | Proxy metrics + vision/spec critics; state this honestly |
| 4 | Sandbox cost outruns free credits | Med | Med | Runtime=iframe (free), warm pool, budgets, self-host fallback |
| 5 | npm supply-chain / malicious codegen | Med | High | `--ignore-scripts`, egress denied, microVM, allowlist |
| 6 | Prompt injection via content | Med | High | Structured fields only, per-agent tool allowlist, no self-escalation |
| 7 | Malicious generated game | Low | Med | iframe sandbox + strict CSP + no network |
| 8 | Cross-tenant leakage | Low | High | `org_id` scoping by construction; isolation tests |
| 9 | Northflank signup (card) blocks deploy | Med | Low | Oracle Always Free VM fallback; local-first dev |
| 10 | Asset style drift / IP concerns | Med | Med | Coherence pass; provenance notes; curated packs |
| 11 | Determinism/reproducibility | Med | Med | Seeded RNG, pinned toolchain, pinned Engine Kit |
| 12 | Non-determinism in `npm install` | Med | Med | Lockfiles, pinned registry, cached warm images |

---

## Milestone Map

| Milestone | Content | The flex |
|---|---|---|
| **v0.1** (Phases 0–3) | Prompt → one genre, playable, published to R2 | "Build me a game" works end-to-end |
| **v0.2** (Phases 4–5) | Verification + self-repair | **It finds and fixes its own bugs** |
| **v0.3** (Phases 6–7) | Multi-agent studio + toolbox/skills | A real multi-agent system, visibly |
| **v0.4** (Phases 8–10) | HITL + durable scheduling + full API | It pauses, resumes, and streams live |
| **v0.5** (Phases 11–13) | Frontend studio + orgs + sandbox mgmt | A usable, multi-tenant product |
| **v1.0** (Phases 14–15) | Multi-genre, assets, evals/CI, demo | **A multi-tenant AI game studio with a scoreboard** |

Every milestone ends in something playable. You can stop at any of them.

---

## Shortcut Build Order

If time-constrained, this order maximizes showcase value per hour:

**0 → 1 → 2 → 3 → 4 → 5 → 6 → 10 → 11 → 15**

i.e. reach a verified, self-repairing, multi-agent build with an API and a UI,
then add the eval scoreboard for the portfolio narrative. Phases 7–9 and 12–14
deepen it but are not required for a compelling demo.

---

## Appendix

### Environment variables (`.env.example`)

```bash
# Core
RIFT_ENV=development
DATABASE_URL=postgresql://...@...-pooler.neon.tech/rift
REDIS_URL=redis://...upstash.io:6379
# Storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=rift-storage
R2_PUBLIC_BASE_URL=https://...
# Sandbox
SANDBOX_PROVIDER=daytona          # daytona|e2b|local
DAYTONA_API_KEY=...
DAYTONA_SNAPSHOT=rift-sandbox
E2B_API_KEY=...                   # optional fallback
E2B_TEMPLATE=rift-sandbox         # optional fallback
# Scheduling
QSTASH_TOKEN=...
QSTASH_CURRENT_SIGNING_KEY=...
# Observability
LANGSMITH_API_KEY=...
LANGSMITH_TRACING=true
# LLM
GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
# Auth
AUTH_PROVIDER=neon-better-auth    # or clerk
CLERK_SECRET_KEY=...              # optional
# Budgets (per build)
RIFT_MAX_ATTEMPTS=4
RIFT_TOKEN_BUDGET=250000
RIFT_SANDBOX_SECONDS_BUDGET=900
RIFT_WALL_CLOCK_BUDGET_S=900
```

### Key packages

```toml
# Python (pyproject.toml)
langgraph = ">=1.2"
langchain = ">=1.3"
langchain-core = ">=1.5"
deepagents = ">=0.7"
langgraph-checkpoint-postgres = "*"
langgraph-store-postgres = "*"     # or via langgraph-checkpoint-postgres extras
daytona = "*"
langchain-daytona = "*"
e2b = "*"                          # optional fallback
fastapi = ">=0.115"
uvicorn = { extras = ["standard"] }
pydantic = ">=2"
pydantic-settings = "*"
sqlalchemy = { extras = ["asyncio"] }
asyncpg = "*"
alembic = "*"
playwright = "*"
boto3 = "*"                        # R2 (S3 API)
upstash-redis = "*"
httpx = "*"
langsmith = "*"
pytest = "*"; pytest-asyncio = "*"
```

```jsonc
// package.json (workspace root)
{
  "workspaces": ["apps/*", "packages/*"],
  "devDependencies": { "turbo": "*", "typescript": "5.x", "prettier": "*" }
}
```

### Verified free-tier facts (Oct 2026)

- **Daytona (Primary)**: **$200 free credit** (no credit card required for Tier 1 email-verified = 10 vCPU / 10 GiB RAM / 30 GiB storage; 5 GiB free storage). Compute ~$0.0504/vCPU-hr, ~$0.0162/GiB-hr (~$0.011 per 4-min build), pure pay-as-you-go with no monthly base fee. Supports `AsyncDaytona`, custom snapshots/Docker images, `Resources(cpu, memory, disk)`, `auto_stop_interval`, and `langchain-daytona` for Deep Agents.
- **E2B (Fallback)**: RAM fixed at **template build** (up to 8 GiB Hobby); **$100 one-time credit**; 20 concurrent; 1 hr max continuous session on Hobby (Pro jumps to $150/mo base fee).
- **Northflank**: free = 2 services + 2 cron + 1 DB, **always-on (no sleeping)**;
  requires a payment method; licenses say not for production. PAYG
  $0.01667/vCPU-hr, $0.00833/GB-hr.
- **Neon**: 100 projects, 100 CU-hrs/proj/mo, 1 GB storage/proj (20 GB total),
  scale-to-zero 5 min, pgvector on all plans, Managed Better Auth 60k MAU, 5 GB
  object storage.
- **Upstash**: Redis 250 MB / 500K cmds/mo; QStash 1,000 msgs/day, 7-day delays.
- **Cloudflare R2**: 10 GB, 1M writes / 10M reads, no egress fees.
- **LangSmith**: Developer free, 1 seat, 5k base traces/mo.
- **LangSmith Deployment / LangGraph Platform**: Developer tier self-hosted,
  **up to 100k nodes executed/mo free**.
- **GitHub Codespaces**: 120 core-hrs/mo (15 GB) — dev box only, not a
  multi-tenant sandbox.

### References to keep in reach

- LangGraph: durable execution, `interrupt`/`Command(resume=…)`, checkpointers
  vs stores, subgraphs & persistence modes.
- LangChain: `create_agent` + middleware, subagents pattern (replaces
  `create_supervisor`).
- Deep Agents: planning tool, subagents, virtual filesystem, skills, context
  modes (`isolated` / `fork`), dynamic-subagent orchestration patterns.
- Daytona & E2B: `AsyncDaytona` (`daytona`, `langchain-daytona`), `AsyncSandbox` (`e2b`).
- Playwright: headless Chromium, console/pageerror capture, input simulation.
- Neon: pgvector, pooled connections, scale-to-zero.
- Cloudflare R2: S3-compatible API.
- Upstash: Redis + QStash (schedules, delays, callbacks).

---

> **The one-line pitch for the portfolio:**
> *"Everyone else built a prompt-to-game toy. I built the durable, multi-tenant
> agent studio behind one — with real sandbox isolation, a verification loop
> that lets the system fix its own bugs, and an eval scoreboard that proves the
> games actually run."*
