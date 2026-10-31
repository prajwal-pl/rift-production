"""Deterministic verification runner (`tsc --noEmit`, `vite build`, forbidden-API scan, Playwright)."""

import json
from typing import Any

from rift.core.ports.sandbox import SandboxProvider

WORKSPACE = "/workspace"

_FORBIDDEN_GREP = (
    r"localStorage|sessionStorage|indexedDB|document\.cookie|"
    r"fetch\(|XMLHttpRequest|new WebSocket|eval\(|new Function"
)


async def run_build(sandbox: SandboxProvider, sandbox_id: str) -> None:
    """Run `pnpm build` inside `/workspace` and raise `RuntimeError` if it fails."""
    res = await sandbox.exec(
        sandbox_id,
        ["sh", "-c", f"cd {WORKSPACE} && pnpm build"],
        timeout=180,
    )
    if res.exit_code != 0:
        raise RuntimeError(f"pnpm build failed (exit {res.exit_code}):\n{res.stderr or res.stdout}")


async def run_verify(sandbox: SandboxProvider, sandbox_id: str) -> dict[str, Any]:
    """Run static + runtime checks inside the sandbox and return a structured report.

    Report shape:
        {
            "passed": bool,
            "errors": list[str],
            "screenshots": list[str],
            "checks": {
                "typecheck": bool,
                "forbidden_apis": bool,
                "build": bool,
                "bundle_exists": bool,
                "runtime": dict[str, Any] | None,
            },
        }
    """
    errors: list[str] = []
    screenshots: list[str] = []
    checks: dict[str, Any] = {
        "typecheck": False,
        "forbidden_apis": False,
        "build": False,
        "bundle_exists": False,
        "runtime": None,
    }

    # 1. TypeScript static typecheck
    tsc_res = await sandbox.exec(
        sandbox_id,
        ["sh", "-c", f"cd {WORKSPACE} && pnpm exec tsc --noEmit"],
        timeout=120,
    )
    if tsc_res.exit_code == 0:
        checks["typecheck"] = True
    else:
        errors.append(f"TypeScript errors:\n{(tsc_res.stderr or tsc_res.stdout).strip()[:2000]}")

    # 2. Forbidden API scan across /workspace/src
    grep_res = await sandbox.exec(
        sandbox_id,
        [
            "sh",
            "-c",
            f"cd {WORKSPACE} && grep -rnE --include='*.ts' '{_FORBIDDEN_GREP}' src || true",
        ],
        timeout=30,
    )
    hits = [
        line
        for line in (grep_res.stdout or "").splitlines()
        if line.strip() and not line.split(":", 2)[-1].lstrip().startswith("//")
    ]
    if not hits:
        checks["forbidden_apis"] = True
    else:
        errors.append("Forbidden browser/network APIs detected:\n" + "\n".join(hits[:20]))

    # 3. Vite single-file build (only if typecheck passed)
    if checks["typecheck"]:
        build_res = await sandbox.exec(
            sandbox_id,
            ["sh", "-c", f"cd {WORKSPACE} && pnpm build"],
            timeout=180,
        )
        if build_res.exit_code == 0:
            checks["build"] = True
        else:
            errors.append(f"Vite build failed:\n{(build_res.stderr or build_res.stdout).strip()[:2000]}")

    # 4. Verify dist/index.html exists and is non-empty
    if checks["build"]:
        try:
            bundle = await sandbox.read_file(sandbox_id, f"{WORKSPACE}/dist/index.html")
            if len(bundle) > 100:
                checks["bundle_exists"] = True
            else:
                errors.append(f"dist/index.html is unexpectedly small ({len(bundle)} bytes)")
        except FileNotFoundError:
            errors.append("dist/index.html was not produced by `pnpm build`")

    # 5. Headless browser verification via Playwright (when bundle exists)
    if checks["bundle_exists"]:
        pw_res = await sandbox.exec(
            sandbox_id,
            ["python3", f"{WORKSPACE}/verify_game.py"],
            timeout=60,
        )
        raw_out = (pw_res.stdout or "").strip()
        last_line = raw_out.splitlines()[-1] if raw_out else ""
        try:
            verdict = json.loads(last_line)
        except json.JSONDecodeError:
            verdict = None

        if isinstance(verdict, dict):
            checks["runtime"] = verdict
            screenshots = list(verdict.get("screenshots") or [])
            if not verdict.get("passed", False):
                rt_errs = verdict.get("errors") or ["Runtime verification failed"]
                errors.append("Runtime errors:\n" + "\n".join(str(e) for e in rt_errs))
        elif pw_res.exit_code != 0:
            errors.append(
                f"Playwright harness failed (exit {pw_res.exit_code}):\n"
                f"{(pw_res.stderr or pw_res.stdout).strip()[:1500]}"
            )

    passed = len(errors) == 0 and checks["typecheck"] and checks["build"] and checks["bundle_exists"]
    return {
        "passed": passed,
        "errors": errors,
        "screenshots": screenshots,
        "checks": checks,
    }
