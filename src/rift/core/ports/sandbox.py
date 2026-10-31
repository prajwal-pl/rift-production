from typing import Protocol

from pydantic import BaseModel


class ExecResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class SandboxProvider(Protocol):
    """Vendor-neutral execution sandbox. Implementations: Daytona (prod), in-memory fake (tests)."""

    async def create(self, *, labels: dict[str, str] | None = None) -> str:
        """Create a sandbox and return its id. `labels` are attached for later reaping."""
        ...

    async def exists(self, sandbox_id: str) -> bool:
        """True if the sandbox is usable (a stopped sandbox is restarted). False if gone."""
        ...

    async def read_file(self, sandbox_id: str, path: str) -> bytes: ...

    async def write_file(self, sandbox_id: str, content: bytes, path: str) -> None: ...

    async def exec(
        self, sandbox_id: str, cmd: list[str], *, timeout: int = 120
    ) -> ExecResult:
        """Run argv (no shell). Wrap compound commands as ["sh", "-c", "..."]."""
        ...

    async def terminate(self, sandbox_id: str) -> None:
        """Delete the sandbox. MUST be idempotent (already gone == success)."""
        ...
