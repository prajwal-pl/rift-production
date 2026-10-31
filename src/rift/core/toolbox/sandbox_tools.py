# src/rift/core/toolbox/sandbox_tools.py
import shlex

from langchain_core.tools import BaseTool, tool

from rift.core.ports.sandbox import SandboxProvider

WORKSPACE = "/workspace"


def make_readonly_tools(sandbox: SandboxProvider, sandbox_id: str) -> list[BaseTool]:
    """Tools bound (by closure) to ONE sandbox. No write/exec-anything tools on purpose."""

    @tool
    async def list_files(subdir: str = "src") -> str:
        """List files under /workspace/<subdir> (excludes node_modules and dist)."""
        res = await sandbox.exec(
            sandbox_id,
            [
                "sh",
                "-c",
                f"cd {WORKSPACE} && find {shlex.quote(subdir)} -type f -not -path '*/node_modules/*' | sort | head -200",
            ],
        )
        return res.stdout if res.exit_code == 0 else f"error: {res.stderr}"

    @tool
    async def read_file(path: str) -> str:
        """Read a UTF-8 file under /workspace (path relative to /workspace, e.g. 'src/main.ts')."""
        if ".." in path or path.startswith("/"):
            return "error: path must be relative and inside /workspace"
        raw = await sandbox.read_file(sandbox_id, f"{WORKSPACE}/{path}")
        return raw.decode("utf-8", errors="replace")[:30_000]  # cap context cost

    @tool
    async def grep_code(pattern: str) -> str:
        """Search /workspace/src for a fixed string. Returns file:line:match (max 100 lines)."""
        res = await sandbox.exec(
            sandbox_id,
            [
                "sh",
                "-c",
                f"cd {WORKSPACE} && grep -rnF --include='*.ts' -- {shlex.quote(pattern)} src | head -100",
            ],
        )
        return res.stdout or "no matches"

    return [list_files, read_file, grep_code]
