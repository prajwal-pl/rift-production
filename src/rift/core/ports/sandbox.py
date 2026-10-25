from typing import Protocol

from pydantic import BaseModel


class ExecResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class SandboxProvider(Protocol):
    async def create(self) -> str: ...
    async def read_file(self, sandbox_id: str, path: str) -> bytes: ...
    async def write_file(self, sandbox_id: str, content: bytes, path: str) -> None: ...
    async def exec(self, sandbox_id: str, cmd: list[str]) -> ExecResult: ...
    async def terminate(self, sandbox_id: str) -> None: ...
