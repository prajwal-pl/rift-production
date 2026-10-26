# Module 8 & 9 Deep Dive: Daytona Sandboxes, Playwright Verification & Cloudflare R2

> **Purpose of this guide:**
> This document is a dedicated, project-relevant guide for **Module 8 (Daytona Cloud Sandboxes & Cloudflare R2 Object Storage)** and **Module 9 (Playwright Headless Browser Verification)**.
>
> Instead of abstract or unrelated examples, this guide explains **the exact theory** in plain English and shows **how Daytona, Playwright, and Cloudflare R2 connect together as a single pipeline** to build, test, screenshot, and publish a playable 2D browser game.

---

## Table of Contents

1. [The Big Picture: How Daytona, Playwright & R2 Connect](#1-the-big-picture-how-daytona-playwright--r2-connect)
2. [Part 1: Daytona Cloud Sandboxes (`AsyncDaytona`)](#2-part-1-daytona-cloud-sandboxes-asyncdaytona)
   - [Theory: What is a Daytona Sandbox?](#theory-what-is-a-daytona-sandbox)
   - [Daytona Python SDK Reference](#daytona-python-sdk-reference)
   - [Implementing the `DaytonaSandboxProvider` Adapter](#implementing-the-daytonasandboxprovider-adapter)
3. [Part 2: Headless Browser Verification (`Playwright`)](#3-part-2-headless-browser-verification-playwright)
   - [Theory: Why Static Checks (`tsc` / `vite build`) Are Not Enough](#theory-why-static-checks-tsc--vite-build-are-not-enough)
   - [The `window.__RIFT__` Test Bridge](#the-window__rift__-test-bridge)
   - [How Playwright Runs Inside the Daytona Sandbox](#how-playwright-runs-inside-the-daytona-sandbox)
4. [Part 3: Cloudflare R2 Object Storage (`boto3`)](#4-part-3-cloudflare-r2-object-storage-boto3)
   - [Theory: Content-Addressed Storage & `ContentType`](#theory-content-addressed-storage--contenttype)
   - [Cloudflare R2 + `boto3` Reference](#cloudflare-r2--boto3-reference)
   - [Implementing the `R2StorageProvider` Adapter](#implementing-the-r2storageprovider-adapter)
5. [Part 4: Putting It All Together — Linking Daytona → Playwright → R2](#5-part-4-putting-it-all-together--linking-daytona--playwright--r2)

---

## 1. The Big Picture: How Daytona, Playwright & R2 Connect

When your AI agent writes TypeScript/Phaser game code, **three things must happen** before a user can play that game in their browser:

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. DAYTONA SANDBOX (Execution Sandbox — Ephemeral Linux Container)         │
│                                                                            │
│   Agent writes code ──► `pnpm tsc --noEmit` ──► `pnpm vite build`          │
│                              (Static Check)         (Outputs dist/)        │
│                                                           │                │
│                                                           ▼                │
│   ┌────────────────────────────────────────────────────────────────────┐   │
│   │ 2. PLAYWRIGHT (Headless Chromium running INSIDE Daytona Sandbox)   │   │
│   │                                                                    │   │
│   │   • Serves `dist/` on localhost:4173                               │   │
│   │   • Opens http://localhost:4173 in headless Chromium               │   │
│   │   • Listens for `console.error` & uncaught JS crashes              │   │
│   │   • Waits for `window.__RIFT__.ready == true`                      │   │
│   │   • Simulates key press (`ArrowRight`) & checks state change       │   │
│   │   • Saves `screenshot_t0.png` and `screenshot_t1.png`              │   │
│   └────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬─────────────────────────────────────┘
                                       │
         Download `dist/` files & `.png` screenshots via `sb.fs.download_file()`
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 3. CLOUDFLARE R2 (Permanent Object Storage + CDN)                          │
│                                                                            │
│   • Computes SHA-256 hash of files                                         │
│   • Uploads `games/<build_id>/index.html`, `assets/...`, `screenshot.png`  │
│   • Returns public CDN URL → Loaded by Next.js `<iframe sandbox>`!         │
└────────────────────────────────────────────────────────────────────────────┘
```

### Why are Daytona and R2 separate?
- **Daytona costs money per second (~$0.011 per 4-min build):** You only want Daytona running while compiling code and running Playwright. As soon as `dist/` is built and verified, you **destroy the Daytona sandbox** (`await daytona.delete(sb)`).
- **Cloudflare R2 is free to serve forever ($0 egress):** Once the static `dist/` files (`index.html`, `.js`, `.png`) are copied from Daytona to R2, a million people can play the game in their browser `<iframe>` and it costs **$0** in compute.

---

## 2. Part 1: Daytona Cloud Sandboxes (`AsyncDaytona`)

### Theory: What is a Daytona Sandbox?
A Daytona Sandbox is an isolated Linux environment managed via an API:
1. **Stateful across commands, ephemeral per build:** When you call `await daytona.create()`, Daytona gives you a `sandbox.id` (e.g., `"sbx_9f8a..."`). While that sandbox is alive, you can write 20 files and run 10 shell commands (`pnpm install`, `pnpm tsc`, `pnpm build`), and the filesystem persists between commands.
2. **Snapshots vs. Custom Images:**
   - If you boot a bare Ubuntu image and run `apt-get install nodejs` + `npx playwright install chromium` on every build, every build wastes 90 seconds installing tools.
   - Instead, Daytona lets you define a **Declarative Image** (`Image.debian_slim().run_commands(...)`) or a **Pre-built Snapshot** (`CreateSandboxFromSnapshotParams(snapshot="rift-sandbox")`) that already has Node.js, `pnpm`, Playwright, and Chromium pre-installed. Booting from a snapshot takes **~90ms**.
3. **Reconnect by ID (`daytona.get(sandbox_id)`):**
   - Look at your [`SandboxProvider`](src/rift/core/ports/sandbox.py) Protocol: `create()` returns a `sandbox_id: str`, and subsequent calls (`write_file(sandbox_id, ...)`, `exec(sandbox_id, ...)`) pass that `sandbox_id`.
   - Daytona's SDK supports `await daytona.get(sandbox_id)` to grab the `AsyncSandbox` handle for any active `sandbox_id` (or you can cache the active `AsyncSandbox` object in a dictionary in your adapter for zero extra network lookups).

---

### Daytona Python SDK Reference

Install the SDK:
```bash
uv add daytona
```

| Operation | Daytona Async SDK Method (`daytona` package) | Notes |
|---|---|---|
| **Client Init** | `daytona = AsyncDaytona(DaytonaConfig(api_key=...))` | Or `AsyncDaytona()` to read `DAYTONA_API_KEY` from `.env` |
| **Create (from Snapshot)** | `sb = await daytona.create(CreateSandboxFromSnapshotParams(snapshot="rift-sandbox", auto_stop_interval=15))` | Fastest boot (`~90ms`); `auto_stop_interval` is in minutes |
| **Create (from Image)** | `sb = await daytona.create(CreateSandboxFromImageParams(image=..., resources=Resources(cpu=2, memory=4, disk=8)))` | Custom CPU (vCPUs), Memory (GiB), Disk (GiB) |
| **Get Existing Sandbox** | `sb = await daytona.get(sandbox_id)` | Re-fetches an active `AsyncSandbox` by ID |
| **Write File (Bytes)** | `await sb.fs.upload_file(content_bytes, remote_path)` | Accepts `bytes` directly as first argument |
| **Read File (Bytes)** | `data: bytes = await sb.fs.download_file(remote_path)` | Returns raw `bytes` |
| **Run Command** | `resp = await sb.process.exec("pnpm run build", cwd="/workspace", timeout=60)` | Returns `ExecuteResponse` (`resp.exit_code`, `resp.result`) |
| **Destroy Sandbox** | `await daytona.delete(sb)` | Permanently deletes sandbox and stops billing |

---

### Implementing the `DaytonaSandboxProvider` Adapter

Here is how Daytona plugs directly into your [`SandboxProvider`](src/rift/core/ports/sandbox.py) port in `src/rift/adapters/daytona.py`:

```python
import shlex
from daytona import (
    AsyncDaytona,
    AsyncSandbox,
    CreateSandboxFromSnapshotParams,
    DaytonaConfig,
)
from rift.core.ports.sandbox import ExecResult, SandboxProvider


class DaytonaSandboxProvider(SandboxProvider):
    def __init__(
        self,
        api_key: str,
        snapshot: str = "rift-sandbox",
        auto_stop_minutes: int = 15,
    ) -> None:
        self._client = AsyncDaytona(DaytonaConfig(api_key=api_key))
        self._snapshot = snapshot
        self._auto_stop_minutes = auto_stop_minutes
        # Cache active sandbox objects by ID to avoid extra HTTP round-trips
        self._sandboxes: dict[str, AsyncSandbox] = {}

    async def _get_sandbox(self, sandbox_id: str) -> AsyncSandbox:
        if sandbox_id not in self._sandboxes:
            self._sandboxes[sandbox_id] = await self._client.get(sandbox_id)
        return self._sandboxes[sandbox_id]

    async def create(self) -> str:
        params = CreateSandboxFromSnapshotParams(
            snapshot=self._snapshot,
            auto_stop_interval=self._auto_stop_minutes,
        )
        sandbox = await self._client.create(params, timeout=120)
        self._sandboxes[sandbox.id] = sandbox
        return sandbox.id

    async def write_file(self, sandbox_id: str, content: bytes, path: str) -> None:
        sandbox = await self._get_sandbox(sandbox_id)
        await sandbox.fs.upload_file(content, path)

    async def read_file(self, sandbox_id: str, path: str) -> bytes:
        sandbox = await self._get_sandbox(sandbox_id)
        return await sandbox.fs.download_file(path)

    async def exec(self, sandbox_id: str, cmd: list[str]) -> ExecResult:
        sandbox = await self._get_sandbox(sandbox_id)
        # Safely join ["pnpm", "tsc", "--noEmit"] -> "pnpm tsc --noEmit"
        command_str = shlex.join(cmd)
        response = await sandbox.process.exec(command_str, timeout=120)

        output = response.result or ""
        exit_code = int(response.exit_code) if response.exit_code is not None else 0
        return ExecResult(
            stdout=output if exit_code == 0 else "",
            stderr=output if exit_code != 0 else "",
            exit_code=exit_code,
        )

    async def terminate(self, sandbox_id: str) -> None:
        sandbox = await self._get_sandbox(sandbox_id)
        try:
            await self._client.delete(sandbox)
        finally:
            self._sandboxes.pop(sandbox_id, None)
```

---

## 3. Part 2: Headless Browser Verification (`Playwright`)

### Theory: Why Static Checks (`tsc` / `vite build`) Are Not Enough
In Phaser 3 / HTML5 Canvas games, a project can compile with **zero TypeScript errors** (`tsc --noEmit` exits `0`) and bundle cleanly (`vite build` exits `0`), yet still be completely broken when a player opens it:
1. **Missing asset crash:** `this.load.image('player', 'missing.png')` only fails at runtime when Phaser boots in a browser.
2. **Null physics body crash:** Calling `this.player.body.setVelocityX(200)` when physics wasn't enabled on `this.player` throws `TypeError: Cannot read properties of null` on frame 1.
3. **Frozen controls:** The game renders a title screen, but pressing `ArrowRight` or `Space` does nothing because input listeners weren't wired.

### The `window.__RIFT__` Test Bridge
How can an automated script tell if a `<canvas>` game is actually working? A `<canvas>` is just pixels—there are no DOM `<button>` or `<div id="score">` elements to inspect!

To solve this, Rift's **Engine Kit** exposes a tiny JavaScript object on `window.__RIFT__` inside the game:
```ts
// Inside packages/engine-kit/runtime/debug.ts
window.__RIFT__ = {
  ready: true, // Set to true once the Phaser scene finishes create()
  state: () => ({
    scene: game.scene.getScenes(true)[0]?.scene.key ?? "boot",
    score: currentScore,
    playerX: player.x,
    playerY: player.y,
    gameOver: isGameOver,
  }),
  errors: [], // Captures any internal runtime errors
};
```
Now Playwright doesn't have to guess from pixels—it can simply run `await page.evaluate("window.__RIFT__.state()")` before and after pressing a key to prove that pressing `ArrowRight` actually moved `playerX`!

---

### How Playwright Runs Inside the Daytona Sandbox

Inside the Daytona sandbox, after `pnpm vite build` produces `/workspace/dist/`, we run a self-contained verification script (`verify_game.py`) that:
1. Starts a local static HTTP server serving `/workspace/dist/` on `http://127.0.0.1:4173`.
2. Launches Headless Chromium via Playwright (`--no-sandbox` is required inside Linux containers).
3. Attaches listeners to `page.on("pageerror")` and `page.on("console")` to catch every JS exception.
4. Waits for `window.__RIFT__?.ready === true`.
5. Takes an initial screenshot (`/workspace/screenshot_t0.png`), presses movement keys (`ArrowRight`, `Space`), waits 500ms, takes a second screenshot (`/workspace/screenshot_t1.png`), and compares `state_t0` vs `state_t1`.
6. Prints a structured JSON `Verdict` to `stdout`.

```python
# This script runs INSIDE the Daytona sandbox (or local verify harness)
import asyncio
import functools
import http.server
import json
import socketserver
import threading
from playwright.async_api import async_playwright


def start_static_server(directory: str, port: int = 4173) -> socketserver.TCPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


async def verify_built_game(dist_dir: str = "/workspace/dist") -> dict:
    server = start_static_server(dist_dir, port=4173)
    console_errors: list[str] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            page = await browser.new_page(viewport={"width": 800, "height": 600})

            # 1. Record uncaught exceptions and console.error()
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error"
                else None,
            )

            # 2. Load the built game bundle
            await page.goto("http://127.0.0.1:4173/index.html", wait_until="networkidle")

            # 3. Check that a <canvas> element exists and wait for window.__RIFT__.ready
            canvas_count = await page.locator("canvas").count()
            await page.wait_for_function("() => window.__RIFT__?.ready === true", timeout=5000)

            # 4. Read initial state & capture t0 screenshot
            state_t0 = await page.evaluate("() => window.__RIFT__.state()")
            await page.screenshot(path="/workspace/screenshot_t0.png")

            # 5. Simulate player input (hold ArrowRight for 300ms)
            await page.keyboard.down("ArrowRight")
            await page.wait_for_timeout(300)
            await page.keyboard.up("ArrowRight")

            # 6. Read state after input & capture t1 screenshot
            state_t1 = await page.evaluate("() => window.__RIFT__.state()")
            await page.screenshot(path="/workspace/screenshot_t1.png")

            await browser.close()

        interactive = state_t0 != state_t1
        return {
            "boots": len(console_errors) == 0 and canvas_count > 0,
            "canvas_present": canvas_count > 0,
            "interactive": interactive,
            "errors": console_errors,
            "state_t0": state_t0,
            "state_t1": state_t1,
        }
    finally:
        server.shutdown()


if __name__ == "__main__":
    verdict = asyncio.run(verify_built_game())
    print(json.dumps(verdict))
```

---

## 4. Part 3: Cloudflare R2 Object Storage (`boto3`)

### Theory: Content-Addressed Storage & `ContentType`
Once Playwright verifies the game inside Daytona, your backend downloads the built files (`dist/index.html`, `dist/assets/index.js`, `screenshot_t0.png`) from Daytona into Python memory (`bytes`) and uploads them to **Cloudflare R2**.

Three critical concepts to understand for R2:

1. **R2 uses the AWS S3 API (`boto3`):**
   Cloudflare R2 is S3-compatible. You use standard `boto3.client("s3", ...)` pointed at `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` with `region_name="auto"`.
2. **Wrapping `boto3` with `asyncio.to_thread`:**
   `boto3` is a synchronous library. Calling `s3.put_object(...)` directly inside an `async def` function would block FastAPI's event loop during the upload. Wrapping it in `await asyncio.to_thread(self._s3.put_object, ...)` runs the network upload on a background thread without freezing the event loop!
3. **Why `ContentType` matters for playable games:**
   If you upload `index.html` without specifying `ContentType="text/html"` (or `mimetypes.guess_type(path)`), R2 defaults to `application/octet-stream`. When your Next.js frontend points an `<iframe>` at that URL, the browser will pop up a "Save File" dialog instead of playing the game!

---

### Cloudflare R2 + `boto3` Reference

Install `boto3`:
```bash
uv add boto3
```

| Parameter | Value for Cloudflare R2 |
|---|---|
| `service_name` | `"s3"` |
| `endpoint_url` | `f"https://{r2_account_id}.r2.cloudflarestorage.com"` |
| `aws_access_key_id` | R2 API Token Access Key ID |
| `aws_secret_access_key` | R2 API Token Secret Access Key |
| `region_name` | `"auto"` (Required by Cloudflare R2 for SigV4 signing) |

---

### Implementing the `R2StorageProvider` Adapter

Here is how Cloudflare R2 implements your [`StorageProvider`](src/rift/core/ports/storage.py) Protocol in `src/rift/adapters/r2.py`, including automatic content-addressing (`SHA-256`) and MIME type detection:

```python
import asyncio
import hashlib
import mimetypes
import boto3
from rift.core.ports.storage import StorageProvider


class R2StorageProvider(StorageProvider):
    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        public_base_url: str,
    ) -> None:
        self._bucket = bucket_name
        self._public_base_url = public_base_url.rstrip("/")
        self._s3 = boto3.client(
            service_name="s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    async def upload_file(
        self,
        path: str,
        content: bytes,
        content_type: str | None = None,
    ) -> str:
        # Automatically detect MIME type from file extension if not provided
        if content_type is None:
            guessed_type, _ = mimetypes.guess_type(path)
            content_type = guessed_type or "application/octet-stream"

        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=path,
            Body=content,
            ContentType=content_type,
        )
        return path

    async def upload_content_addressed(
        self,
        prefix: str,
        extension: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Hashes `content` with SHA-256 so identical artifacts are deduplicated."""
        digest = hashlib.sha256(content).hexdigest()
        ext = extension.lstrip(".")
        key = f"{prefix.strip('/')}/{digest}.{ext}"
        await self.upload_file(path=key, content=content, content_type=content_type)
        return key

    async def get_file(self, path: str) -> bytes:
        def _download() -> bytes:
            response = self._s3.get_object(Bucket=self._bucket, Key=path)
            return response["Body"].read()

        return await asyncio.to_thread(_download)

    def get_public_url(self, path: str) -> str:
        return f"{self._public_base_url}/{path.lstrip('/')}"
```

---

## 5. Part 4: Putting It All Together — Linking Daytona → Playwright → R2

Here is a complete, realistic workflow function showing how your **LangGraph Studio** (or a standalone test script) uses `SandboxProvider` (Daytona) and `StorageProvider` (Cloudflare R2) together:

1. Boots a Daytona sandbox.
2. Writes a playable HTML5 Canvas + `window.__RIFT__` game into the sandbox.
3. Runs `verify_game.py` (Playwright) inside the Daytona sandbox to verify it boots, responds to `ArrowRight`, and generates `screenshot_t1.png`.
4. Reads the built `index.html` and `screenshot_t1.png` bytes out of Daytona (`sandbox.read_file`).
5. Uploads both to Cloudflare R2 (`storage.upload_file`) and returns the live playable URL.
6. Tears down the Daytona sandbox in `finally`.

```python
import json
from rift.core.ports.sandbox import SandboxProvider
from rift.core.ports.storage import StorageProvider


SAMPLE_GAME_HTML = b"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Neon Dodger</title></head>
<body style="margin:0;background:#090d16;overflow:hidden;">
  <canvas id="game" width="800" height="600"></canvas>
  <script>
    const canvas = document.getElementById("game");
    const ctx = canvas.getContext("2d");
    let playerX = 100;
    let score = 0;

    window.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { playerX += 25; score += 10; }
    });

    function loop() {
      ctx.fillStyle = "#090d16";
      ctx.fillRect(0, 0, 800, 600);
      ctx.fillStyle = "#00ffcc";
      ctx.fillRect(playerX, 280, 40, 40);
      requestAnimationFrame(loop);
    }
    loop();

    window.__RIFT__ = {
      ready: true,
      state: () => ({ scene: "main", playerX, score }),
      errors: []
    };
  </script>
</body>
</html>
"""


async def build_verify_and_publish_game(
    build_id: str,
    sandbox: SandboxProvider,
    storage: StorageProvider,
    verify_script_bytes: bytes,
) -> dict:
    # 1. Create isolated Daytona sandbox
    sandbox_id = await sandbox.create()

    try:
        # 2. Write the game output & verification script into Daytona
        await sandbox.write_file(
            sandbox_id, SAMPLE_GAME_HTML, "/workspace/dist/index.html"
        )
        await sandbox.write_file(
            sandbox_id, verify_script_bytes, "/workspace/verify_game.py"
        )

        # 3. Run Playwright verification inside Daytona
        exec_res = await sandbox.exec(
            sandbox_id, ["python3", "/workspace/verify_game.py"]
        )
        if exec_res.exit_code != 0:
            raise RuntimeError(f"Verification script crashed: {exec_res.stderr}")

        verdict = json.loads(exec_res.stdout)
        if not verdict["boots"] or not verdict["interactive"]:
            return {"status": "failed", "verdict": verdict}

        # 4. Extract built files & Playwright screenshot from Daytona into memory
        html_bytes = await sandbox.read_file(sandbox_id, "/workspace/dist/index.html")
        screenshot_bytes = await sandbox.read_file(
            sandbox_id, "/workspace/screenshot_t1.png"
        )

        # 5. Upload from memory to Cloudflare R2
        game_key = f"builds/{build_id}/index.html"
        screenshot_key = f"builds/{build_id}/screenshot_t1.png"

        await storage.upload_file(game_key, html_bytes, content_type="text/html")
        await storage.upload_file(
            screenshot_key, screenshot_bytes, content_type="image/png"
        )

        return {
            "status": "published",
            "verdict": verdict,
            "play_url": storage.get_public_url(game_key),
            "screenshot_url": storage.get_public_url(screenshot_key),
        }

    finally:
        # 6. Always destroy the Daytona sandbox so compute billing stops immediately
        await sandbox.terminate(sandbox_id)
```

---

## Summary Checklist: What to Implement in Rift for Modules 8 & 9

1. Update [`src/rift/core/ports/storage.py`](src/rift/core/ports/storage.py) so `upload_file` accepts `content: bytes` and `content_type: str`, and add `get_public_url(path: str) -> str`.
2. Add `src/rift/adapters/memory.py` (`FakeSandboxProvider` and `InMemoryStorageProvider`) so you can run the `build_verify_and_publish_game` pipeline in `pytest` offline in 5ms.
3. Add `src/rift/adapters/daytona.py` (`DaytonaSandboxProvider`) and `src/rift/adapters/r2.py` (`R2StorageProvider`).
4. Add `daytona`, `boto3`, and `playwright` to `pyproject.toml` when you are ready to run live integration tests.
