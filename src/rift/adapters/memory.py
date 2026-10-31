"""In-process test doubles for the `SandboxProvider` and `StorageProvider` ports.

`FakeSandboxProvider` is backed by REAL temporary directories and a REAL `sh`, with the absolute
paths `/workspace`, `/tmp` and `/opt` transparently rewritten into the sandbox's private root. That
lets tests exercise the actual `tar` / `sha256sum` / `cp` shell snippets used by the lifecycle
helpers without Daytona. Commands the host can't run (`pnpm`, `playwright`, ...) are simulated via
`exec_hook`.
"""

import asyncio
import re
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from rift.core.ports.sandbox import ExecResult

ExecHook = Callable[[str, list[str]], ExecResult | None]

_VIRTUAL_ROOTS = re.compile(r"(?<![\w./-])/(workspace|tmp|opt)(?![\w-])")


class FakeSandboxProvider:
    def __init__(self, *, exec_hook: ExecHook | None = None) -> None:
        self._base = Path(tempfile.mkdtemp(prefix="rift-fake-sandbox-"))
        self._alive: set[str] = set()
        self.exec_hook = exec_hook
        self.created: list[str] = []
        self.terminated: list[str] = []
        self.labels: dict[str, dict[str, str]] = {}
        self.exec_log: list[list[str]] = []

    # ── helpers for tests ─────────────────────────────────────────────────
    def kill(self, sandbox_id: str) -> None:
        """Simulate the sandbox vanishing (expired / deleted behind our back)."""
        self._alive.discard(sandbox_id)
        shutil.rmtree(self._base / sandbox_id, ignore_errors=True)

    def root(self, sandbox_id: str) -> Path:
        return self._base / sandbox_id

    def workspace(self, sandbox_id: str) -> Path:
        return self.root(sandbox_id) / "workspace"

    @property
    def alive(self) -> set[str]:
        return set(self._alive)

    def cleanup(self) -> None:
        shutil.rmtree(self._base, ignore_errors=True)

    def _require(self, sandbox_id: str) -> Path:
        if sandbox_id not in self._alive:
            raise FileNotFoundError(f"sandbox {sandbox_id} does not exist")
        return self.root(sandbox_id)

    def _real(self, sandbox_id: str, path: str) -> Path:
        root = self._require(sandbox_id)
        real = Path(_VIRTUAL_ROOTS.sub(lambda m: f"{root}/{m.group(1)}", path))
        if not str(real).startswith(str(root)):
            raise PermissionError(f"path outside sandbox: {path}")
        return real

    # ── SandboxProvider ───────────────────────────────────────────────────
    async def create(self, *, labels: dict[str, str] | None = None) -> str:
        sid = f"fake_{uuid.uuid4().hex[:10]}"
        for sub in ("workspace", "tmp", "opt"):
            (self._base / sid / sub).mkdir(parents=True)
        self._alive.add(sid)
        self.created.append(sid)
        self.labels[sid] = labels or {}
        return sid

    async def exists(self, sandbox_id: str) -> bool:
        return sandbox_id in self._alive

    async def read_file(self, sandbox_id: str, path: str) -> bytes:
        return self._real(sandbox_id, path).read_bytes()

    async def write_file(self, sandbox_id: str, content: bytes, path: str) -> None:
        real = self._real(sandbox_id, path)
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_bytes(content)

    async def exec(
        self, sandbox_id: str, cmd: list[str], *, timeout: int = 120
    ) -> ExecResult:
        root = self._require(sandbox_id)
        self.exec_log.append(cmd)
        if self.exec_hook is not None and (hooked := self.exec_hook(sandbox_id, cmd)):
            return hooked
        rewritten = [_VIRTUAL_ROOTS.sub(lambda m: f"{root}/{m.group(1)}", a) for a in cmd]
        proc = await asyncio.create_subprocess_exec(
            *rewritten,
            cwd=root / "workspace",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            return ExecResult(stdout="", stderr="timed out", exit_code=124)
        code = proc.returncode or 0
        text_out, text_err = out.decode(errors="replace"), err.decode(errors="replace")
        return ExecResult(
            stdout=text_out, stderr=text_err or (text_out if code else ""), exit_code=code
        )

    async def terminate(self, sandbox_id: str) -> None:
        self.terminated.append(sandbox_id)
        self._alive.discard(sandbox_id)
        shutil.rmtree(self._base / sandbox_id, ignore_errors=True)


class InMemoryStorageProvider:
    def __init__(self, public_base_url: str = "https://cdn.test") -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self._base = public_base_url.rstrip("/")

    async def upload_file(
        self,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self.objects[path] = content
        self.content_types[path] = content_type
        return path

    async def get_file(self, path: str) -> bytes:
        try:
            return self.objects[path]
        except KeyError:
            raise FileNotFoundError(path) from None

    def get_public_url(self, path: str) -> str:
        return f"{self._base}/{path.lstrip('/')}"
