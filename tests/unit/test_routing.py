"""Unit tests for pure routing functions and `ReviewVerdict` validation."""

import pytest
from pydantic import ValidationError

from rift.core.domain.gdd import ReviewIssue, ReviewVerdict
from rift.core.studio.routing import (
    decide_after_review,
    exhausted,
    route_after_verify,
    route_from_start,
)


def test_exhausted_checks_rounds_and_tokens() -> None:
    assert not exhausted({"round": 1, "max_rounds": 4, "tokens_used": 1_000, "token_budget": 10_000})
    assert exhausted({"round": 4, "max_rounds": 4, "tokens_used": 1_000, "token_budget": 10_000})
    assert exhausted({"round": 1, "max_rounds": 4, "tokens_used": 10_000, "token_budget": 10_000})


def test_route_from_start_handles_fresh_and_refinement_builds() -> None:
    assert route_from_start({"prompt": "make a game"}) == "planner"
    assert route_from_start({"prompt": "faster player", "gdd": {"title": "Existing"}}) == "provision"


def test_route_after_verify_branches() -> None:
    assert route_after_verify({"verify_report": {"passed": True}, "round": 1, "max_rounds": 4}) == "reviewer"
    assert route_after_verify({"verify_report": {"passed": False}, "round": 1, "max_rounds": 4}) == "coder"
    assert route_after_verify({"verify_report": {"passed": False}, "round": 4, "max_rounds": 4}) == "fail"
    assert (
        route_after_verify(
            {
                "verify_report": {"passed": False},
                "round": 1,
                "max_rounds": 4,
                "tokens_used": 300_000,
                "token_budget": 250_000,
            }
        )
        == "fail"
    )


def test_decide_after_review_branches() -> None:
    approved = ReviewVerdict(approved=True, summary="All criteria pass.", issues=[])
    assert decide_after_review(approved, {"round": 1, "max_rounds": 4}) == "publish"

    minor_only = ReviewVerdict(
        approved=False,
        summary="Minor polish.",
        issues=[
            ReviewIssue(
                severity="minor",
                problem="Score text slightly small",
                fix_instruction="Increase font size to 22px",
            )
        ],
    )
    assert decide_after_review(minor_only, {"round": 1, "max_rounds": 4}) == "publish"

    major = ReviewVerdict(
        approved=False,
        summary="AC4 fails.",
        issues=[
            ReviewIssue(
                severity="major",
                criterion_id="AC4",
                file="src/scenes/GameScene.ts",
                problem="Score does not increment",
                fix_instruction="Increment score on enemy death",
            )
        ],
    )
    assert decide_after_review(major, {"round": 1, "max_rounds": 4}) == "coder"
    # When out of rounds, major (non-blocker) still ships because verify passed
    assert decide_after_review(major, {"round": 4, "max_rounds": 4}) == "publish"

    blocker = ReviewVerdict(
        approved=False,
        summary="Game soft-locks.",
        issues=[
            ReviewIssue(
                severity="blocker",
                criterion_id="AC5",
                file="src/scenes/GameOverScene.ts",
                problem="Restart key is not bound",
                fix_instruction="Bind R to restart GameScene",
            )
        ],
    )
    assert decide_after_review(blocker, {"round": 2, "max_rounds": 4}) == "coder"
    assert decide_after_review(blocker, {"round": 4, "max_rounds": 4}) == "fail"


def test_review_verdict_rejects_approved_with_blocker_or_major() -> None:
    with pytest.raises(ValidationError):
        ReviewVerdict(
            approved=True,
            summary="Contradictory verdict",
            issues=[
                ReviewIssue(
                    severity="blocker",
                    problem="Crash on boot",
                    fix_instruction="Fix null body",
                )
            ],
        )
