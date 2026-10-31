"""Tests for `sandbox_lifecycle.py` using `FakeSandboxProvider` and `InMemoryStorageProvider`."""

import pytest

from rift.adapters.memory import FakeSandboxProvider, InMemoryStorageProvider
from rift.core.studio.sandbox_lifecycle import (
    WORKSPACE,
    ensure_sandbox,
    snapshot_source,
    teardown,
)


@pytest.mark.asyncio
async def test_lifecycle_seed_snapshot_restore_and_teardown() -> None:
    sandbox = FakeSandboxProvider()
    storage = InMemoryStorageProvider()
    try:
        state = {"build_id": "bld_lifecycle", "org_id": "org_1"}

        # 1. First ensure_sandbox creates a sandbox and seeds the starter + verify_game.py
        sid1, recreated1 = await ensure_sandbox(sandbox, storage, state)
        assert recreated1 is True
        assert await sandbox.exists(sid1)
        main_ts = (await sandbox.read_file(sid1, f"{WORKSPACE}/src/main.ts")).decode()
        assert "installBridge" in main_ts
        verify_py = (await sandbox.read_file(sid1, f"{WORKSPACE}/verify_game.py")).decode()
        assert "verify_built_game" in verify_py

        # 2. Second ensure_sandbox with live sandbox reuses it
        state["sandbox_id"] = sid1
        sid_same, recreated2 = await ensure_sandbox(sandbox, storage, state)
        assert sid_same == sid1
        assert recreated2 is False

        # 3. Modify a file in /workspace and snapshot to storage
        custom_marker = "// CUSTOM_MARKER_FOR_RESTORE_TEST\n"
        await sandbox.write_file(
            sid1,
            (custom_marker + main_ts).encode("utf-8"),
            f"{WORKSPACE}/src/main.ts",
        )
        key, manifest = await snapshot_source(sandbox, storage, sid1, "bld_lifecycle")
        assert key == "builds/bld_lifecycle/source.tgz"
        assert "src/main.ts" in manifest
        assert key in storage.objects
        state["source_key"] = key
        state["files"] = manifest

        # 4. Kill the sandbox behind our back; ensure_sandbox must recreate and restore from R2
        sandbox.kill(sid1)
        assert not await sandbox.exists(sid1)

        sid2, recreated3 = await ensure_sandbox(sandbox, storage, state)
        assert recreated3 is True
        assert sid2 != sid1
        restored = (await sandbox.read_file(sid2, f"{WORKSPACE}/src/main.ts")).decode()
        assert restored.startswith(custom_marker)
        state["sandbox_id"] = sid2

        # 5. Teardown takes a final snapshot and deletes the sandbox
        update = await teardown(sandbox, storage, state)
        assert update["sandbox_id"] is None
        assert update["source_key"] == "builds/bld_lifecycle/source.tgz"
        assert not await sandbox.exists(sid2)
    finally:
        sandbox.cleanup()
