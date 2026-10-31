"""Pure routing functions for the Studio `StateGraph` (zero I/O, zero LLM calls)."""

from typing import Literal

from rift.core.domain.gdd import ReviewVerdict
from rift.core.studio.state import StudioState


def exhausted(state: StudioState) -> bool:
    """Return True if the coder round limit or token budget has been reached."""
    return (
        state.get("round", 0) >= state.get("max_rounds", 4)
        or state.get("tokens_used", 0) >= state.get("token_budget", 250_000)
    )


def route_from_start(state: StudioState) -> Literal["planner", "provision"]:
    """Start at `provision` for refinement builds that already carry a GDD; otherwise `planner`."""
    return "provision" if state.get("gdd") else "planner"


def route_after_verify(state: StudioState) -> Literal["reviewer", "coder", "fail"]:
    """Route after deterministic verification (`tsc`, `vite build`, Playwright)."""
    if (state.get("verify_report") or {}).get("passed") is True:
        return "reviewer"
    return "fail" if exhausted(state) else "coder"


def decide_after_review(
    verdict: ReviewVerdict, state: StudioState
) -> Literal["coder", "publish", "fail"]:
    """Decide whether to publish, loop back to coder, or fail after the reviewer's verdict."""
    blocking = [i for i in verdict.issues if i.severity in ("blocker", "major")]
    if verdict.approved or not blocking:
        # Minor issues never trigger another coder round
        return "publish"
    if not exhausted(state):
        return "coder"
    # Out of rounds/budget: verify already passed, so ship unless a hard blocker remains
    return "fail" if any(i.severity == "blocker" for i in blocking) else "publish"
