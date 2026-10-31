"""Deterministic lifecycle helpers for Daytona sandboxes (`ensure_sandbox`, `snapshot_source`, `teardown`).

The sandbox is treated as an ephemeral cache of `/workspace`. The durable source of truth is
`source_key` in R2 (`builds/<build_id>/source.tgz`) plus the SHA-256 `files` manifest in
`StudioState`.
"""

import logging
from pathlib import Path
from typing import Any

from rift.core.ports.sandbox import SandboxProvider
from rift.core.ports.storage import StorageProvider
from rift.verify.harness_script import HARNESS_SCRIPT

log = logging.getLogger(__name__)

WORKSPACE = "/workspace"
_EXCLUDES = "--exclude=node_modules --exclude=dist --exclude=.git"
_LOCAL_STARTER_DIR = Path(__file__).resolve().parents[2] / "starters" / "phaser_base"


async def _upload_local_starter(sandbox: SandboxProvider, sandbox_id: str) -> None:
    """Upload the bundled `phaser_base` starter files when `/opt/starter` is not in the image."""
    for file_path in sorted(_LOCAL_STARTER_DIR.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(_LOCAL_STARTER_DIR).as_posix()
        if rel.startswith(("node_modules/", "dist/", ".git/")):
            continue
        await sandbox.write_file(
            sandbox_id,
            file_path.read_bytes(),
            f"{WORKSPACE}/{rel}",
        )


async def seed_starter(sandbox: SandboxProvider, sandbox_id: str) -> None:
    """Seed `/workspace` with the Phaser + Vite + TypeScript starter and `verify_game.py`."""
    copy_cmd = (
        f"mkdir -p {WORKSPACE} && "
        f"if [ -d /opt/starter/phaser_base ]; then cp -a /opt/starter/phaser_base/. {WORKSPACE}/; "
        f"elif [ -d /opt/starter/topdown-shooter ]; then cp -a /opt/starter/topdown-shooter/. {WORKSPACE}/; "
        f"else exit 2; fi"
    )
    res = await sandbox.exec(sandbox_id, ["sh", "-c", copy_cmd])
    if res.exit_code == 2:
        await _upload_local_starter(sandbox, sandbox_id)
    elif res.exit_code != 0:
        raise RuntimeError(f"seed_starter failed: {res.stderr}")

    await sandbox.write_file(
        sandbox_id,
        HARNESS_SCRIPT.encode("utf-8"),
        f"{WORKSPACE}/verify_game.py",
    )


async def snapshot_source(
    sandbox: SandboxProvider,
    storage: StorageProvider,
    sandbox_id: str,
    build_id: str,
) -> tuple[str, dict[str, str]]:
    """Tar `/workspace` (excluding `node_modules`, `dist`, `.git`), upload to R2, and return `(key, manifest)`."""
    script = (
        f"cd {WORKSPACE} && tar czf /tmp/src.tgz {_EXCLUDES} . && "
        "find . -type f -not -path './node_modules/*' -not -path './dist/*' -not -path './.git/*' "
        "-exec sha256sum {} +"
    )
    res = await sandbox.exec(sandbox_id, ["sh", "-c", script])
    if res.exit_code != 0:
        raise RuntimeError(f"snapshot_source failed: {res.stderr}")

    manifest: dict[str, str] = {}
    for line in res.stdout.splitlines():
        if line.strip():
            parts = line.split(None, 1)
            if len(parts) == 2:
                digest, rel_path = parts
                manifest[rel_path.removeprefix("./")] = digest

    data = await sandbox.read_file(sandbox_id, "/tmp/src.tgz")
    key = f"builds/{build_id}/source.tgz"
    await storage.upload_file(key, data, content_type="application/gzip")
    return key, manifest


async def restore_source(
    sandbox: SandboxProvider,
    storage: StorageProvider,
    sandbox_id: str,
    key: str,
) -> None:
    """Restore `/workspace` from an R2 `source.tgz` tarball."""
    tarball = await storage.get_file(key)
    await sandbox.write_file(sandbox_id, tarball, "/tmp/src.tgz")
    script = (
        f"mkdir -p {WORKSPACE} && tar xzf /tmp/src.tgz -C {WORKSPACE} && "
        f"cd {WORKSPACE} && "
        f"if [ ! -d node_modules ] && command -v pnpm >/dev/null 2>&1; then "
        f"pnpm install --frozen-lockfile || true; fi"
    )
    res = await sandbox.exec(sandbox_id, ["sh", "-c", script], timeout=300)
    if res.exit_code != 0:
        raise RuntimeError(f"restore_source failed: {res.stderr}")


async def ensure_sandbox(
    sandbox: SandboxProvider,
    storage: StorageProvider,
    state: dict[str, Any],
) -> tuple[str, bool]:
    """Idempotent: returns `(sandbox_id, was_recreated)`.

    If `state["sandbox_id"]` is alive, reuses it. Otherwise creates a new sandbox and either
    restores `state["source_key"]` from R2 or seeds the starter template.
    """
    sid = state.get("sandbox_id")
    if sid and await sandbox.exists(sid):
        return sid, False

    labels: dict[str, str] = {}
    if state.get("build_id"):
        labels["build_id"] = str(state["build_id"])
    if state.get("org_id"):
        labels["org_id"] = str(state["org_id"])

    sid = await sandbox.create(labels=labels)
    if source_key := state.get("source_key"):
        await restore_source(sandbox, storage, sid, source_key)
    else:
        await seed_starter(sandbox, sid)
    return sid, True


async def teardown(
    sandbox: SandboxProvider,
    storage: StorageProvider,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Take a final best-effort source snapshot, then terminate the sandbox. Returns a state update."""
    sid = state.get("sandbox_id")
    if not sid:
        return {}

    update: dict[str, Any] = {}
    try:
        if await sandbox.exists(sid) and state.get("build_id"):
            try:
                key, manifest = await snapshot_source(
                    sandbox, storage, sid, str(state["build_id"])
                )
                update = {"source_key": key, "files": manifest}
            except Exception:
                log.exception("final snapshot failed; keeping previous source_key")
    finally:
        await sandbox.terminate(sid)
    return {**update, "sandbox_id": None}
