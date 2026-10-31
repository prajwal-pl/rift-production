from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

BuildStatus = Literal[
    "queued",
    "planning",
    "awaiting_input",
    "designing",
    "building",
    "verifying",
    "reviewing",
    "repairing",
    "awaiting_approval",
    "published",
    "failed",
    "budget_exceeded",
]


class User(BaseModel):
    id: str
    email: EmailStr
    name: str = Field(min_length=1, max_length=32)
    auth_subject: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Org(BaseModel):
    id: str
    name: str
    slug: str
    plan: Literal["free", "pro"] = "free"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Membership(BaseModel):
    user_id: str
    org_id: str
    role: Literal["member", "owner", "viewer", "admin"] = "member"


class Project(BaseModel):
    id: str
    slug: str
    name: str
    org_id: str
    engine: Literal["phaser3", "3d-engine"] = "phaser3"
    current_build_id: str | None = None
    visibility: Literal["public", "private"] = "public"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Build(BaseModel):
    id: str
    project_id: str
    org_id: str
    prompt: str
    status: BuildStatus = "queued"
    brief: dict[str, Any] = Field(default_factory=dict)
    gdd: dict[str, Any] = Field(default_factory=dict)
    plan: list[dict[str, Any]] = Field(default_factory=list)
    verify_report: dict[str, Any] = Field(default_factory=dict)
    artifact_key: str | None = None
    thread_id: str | None = None
    parent_build_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class Artifact(BaseModel):
    id: str
    build_id: str
    kind: Literal["source", "screenshot", "trace", "static_bundle"] = "source"
    storage_key: str | None = None


class SandboxSession(BaseModel):
    pass

