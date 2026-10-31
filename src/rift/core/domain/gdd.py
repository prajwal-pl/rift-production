from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Planner ⇄ human ─────────────────────────────────────────────────
class Question(BaseModel):
    id: str = Field(description="Short stable id, e.g. 'genre'")
    question: str
    options: list[str] = Field(
        default_factory=list, description="Suggested answers (may be empty)"
    )
    allow_free_text: bool = True


class GameBrief(BaseModel):
    """Planner output: everything the designer needs, with ambiguities resolved."""

    title: str = Field(min_length=2, max_length=60)
    genre: str
    elevator_pitch: str
    core_loop: str
    controls: list[str]
    win_condition: str
    lose_condition: str
    art_style: str
    session_length_minutes: int = Field(ge=1, le=30, default=3)
    assumptions: list[str] = Field(
        default_factory=list, description="Things we decided WITHOUT asking"
    )
    out_of_scope: list[str] = Field(default_factory=list)


# ── Designer ────────────────────────────────────────────────────────
class AcceptanceCriterion(BaseModel):
    id: str  # "AC1"
    description: str  # observable, testable statement
    check: Literal["runtime", "visual", "code"]


class FilePlanItem(BaseModel):
    path: str  # "src/scenes/GameScene.ts"
    purpose: str


class GameDesignDoc(BaseModel):
    title: str
    mechanics: list[str]
    entities: list[str]  # player, enemies, pickups, ... with behaviour
    levels_or_waves: list[str]
    hud_and_menus: list[str]
    palette_hex: list[str] = Field(min_length=3, max_length=8)
    audio: str = "WebAudio synthesized beeps; no external files"
    file_plan: list[FilePlanItem]
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=3)


# ── Reviewer ────────────────────────────────────────────────────────
class ReviewIssue(BaseModel):
    severity: Literal["blocker", "major", "minor"]
    criterion_id: str | None = None  # which acceptance criterion it violates
    file: str | None = None
    problem: str
    fix_instruction: str = Field(
        description="Imperative, specific instruction for the coder"
    )


class ReviewVerdict(BaseModel):
    approved: bool
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _approved_means_no_blockers(self) -> "ReviewVerdict":
        if self.approved and any(
            i.severity in ("blocker", "major") for i in self.issues
        ):
            raise ValueError("approved=True is incompatible with blocker/major issues")
        return self
