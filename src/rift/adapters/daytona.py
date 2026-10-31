"""Daytona implementation of the `SandboxProvider` port (async SDK)."""

import asyncio
import logging
import shlex
from collections.abc import Awaitable, Callable
from typing import TypeVar

from daytona import (
    AsyncDaytona,
    AsyncSandbox,
    CreateSandboxFromSnapshotParams,
    DaytonaConfig,
    DaytonaError,
    DaytonaFileNotFoundError,
    DaytonaNotFoundError,
    DaytonaRateLimitError,
    DaytonaTimeoutError,
    SandboxState,
)

from rift.config import RiftSettings
from rift.core.ports.sandbox import ExecResult

log = logging.getLogger(__name__)
T = TypeVar("T")

_TIMEOUT_EXIT_CODE = 124  # same convention as coreutils `timeout`


class DaytonaSandboxProvider:
    """Async adapter. Sandboxes are addressed by id so any worker can re-attach to them."""

    def __init__(
        self,
        *,
        api_key: str,
        api_url: str | None = None,
        snapshot: str | None = None,
        auto_stop_minutes: int = 15,
        auto_delete_minutes: int = 60,
    ) -> None:
        self._config = DaytonaConfig(api_key=api_key, api_url=api_url)
        self._snapshot = snapshot
        self._auto_stop = auto_stop_minutes
        self._auto_delete = auto_delete_minutes
        self._client: AsyncDaytona | None = None
        self._cache: dict[str, AsyncSandbox] = {}

    @classmethod
    def from_settings(cls, settings: RiftSettings) -> "DaytonaSandboxProvider":
        if settings.daytona_api_key is None:
            raise RuntimeError("DAYTONA_API_KEY is not configured")
        return cls(
            api_key=settings.daytona_api_key.get_secret_value(),
            api_url=settings.daytona_api_url,
            snapshot=settings.daytona_snapshot,
        )

    # ── plumbing ──────────────────────────────────────────────────────────
    def _daytona(self) -> AsyncDaytona:
        if self._client is None:  # lazily, so it is created inside the running event loop
            self._client = AsyncDaytona(self._config)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._cache.clear()

    @staticmethod
    async def _retry(op: Callable[[], Awaitable[T]], *, attempts: int = 3) -> T:
        """Retry on rate limits / transient timeouts with exponential backoff."""
        delay = 1.0
        for attempt in range(1, attempts + 1):
            try:
                return await op()
            except (DaytonaRateLimitError, DaytonaTimeoutError):
                if attempt == attempts:
                    raise
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    async def _sandbox(self, sandbox_id: str) -> AsyncSandbox:
        sb = self._cache.get(sandbox_id)
        if sb is None:
            sb = await self._daytona().get(sandbox_id)
            self._cache[sandbox_id] = sb
        return sb

    # ── SandboxProvider ───────────────────────────────────────────────────
    async def create(self, *, labels: dict[str, str] | None = None) -> str:
        params = CreateSandboxFromSnapshotParams(
            snapshot=self._snapshot,
            labels=labels or {},
            auto_stop_interval=self._auto_stop,
            auto_delete_interval=self._auto_delete,
        )
        sb = await self._retry(lambda: self._daytona().create(params, timeout=120))
        self._cache[sb.id] = sb
        log.info("created sandbox %s", sb.id)
        return sb.id

    async def exists(self, sandbox_id: str) -> bool:
        try:
            sb = await self._daytona().get(sandbox_id)
        except DaytonaNotFoundError:
            self._cache.pop(sandbox_id, None)
            return False
        state = sb.state
        if state in (SandboxState.STOPPED, SandboxState.ARCHIVED):
            await sb.start(timeout=120)  # filesystem persists across stop
            state = SandboxState.STARTED
        elif state in (
            SandboxState.STARTING,
            SandboxState.CREATING,
            SandboxState.RESTORING,
            SandboxState.RESUMING,
        ):
            await sb.wait_for_sandbox_start(timeout=120)
            state = SandboxState.STARTED
        if state == SandboxState.STARTED:
            self._cache[sandbox_id] = sb
            return True
        self._cache.pop(sandbox_id, None)
        return False

    async def read_file(self, sandbox_id: str, path: str) -> bytes:
        sb = await self._sandbox(sandbox_id)
        try:
            data = await sb.fs.download_file(path)
        except DaytonaFileNotFoundError as e:
            raise FileNotFoundError(path) from e
        if data is None:
            raise FileNotFoundError(path)
        return data

    async def write_file(self, sandbox_id: str, content: bytes, path: str) -> None:
        sb = await self._sandbox(sandbox_id)
        try:
            await sb.fs.upload_file(content, path)
        except DaytonaError:
            parent = path.rsplit("/", 1)[0] or "/"
            await sb.process.exec(f"mkdir -p {shlex.quote(parent)}")
            await sb.fs.upload_file(content, path)  # second failure propagates

    async def exec(
        self, sandbox_id: str, cmd: list[str], *, timeout: int = 120
    ) -> ExecResult:
        sb = await self._sandbox(sandbox_id)
        try:
            resp = await sb.process.exec(shlex.join(cmd), timeout=timeout)
        except DaytonaTimeoutError:
            msg = f"command timed out after {timeout}s: {shlex.join(cmd)[:200]}"
            return ExecResult(stdout="", stderr=msg, exit_code=_TIMEOUT_EXIT_CODE)
        output = resp.result or ""
        code = int(resp.exit_code) if resp.exit_code is not None else 0
        # Daytona merges stdout+stderr; expose it as stderr too when the command failed.
        return ExecResult(
            stdout=output, stderr=output if code != 0 else "", exit_code=code
        )

    async def terminate(self, sandbox_id: str) -> None:
        try:
            sb = await self._sandbox(sandbox_id)
            await self._daytona().delete(sb)
        except DaytonaNotFoundError:
            pass  # already gone == success
        finally:
            self._cache.pop(sandbox_id, None)
