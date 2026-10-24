from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"


class Role(StrEnum):
    MEMBER = "member"
    VIEWER = "viewer"
    OWNER = "owner"
    ADMIN = "admin"


class Engine(StrEnum):
    PHASER3 = "phaser3"
    ENGINE3D = "3d-engine"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class BuildStatus(StrEnum):
    QUEUED = "queued"
    DESIGNING = "designing"
    BUILDING = "building"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    AWAITING_APPROVAL = "awaiting_approval"
    PUBLISHED = "published"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"


class ArtifactKind(StrEnum):
    SOURCE = "source"
    SCREENSHOT = "screenshot"
    TRACE = "trace"
    STATIC_BUNDLE = "static-bundle"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    auth_system: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    plan: Mapped[Plan] = mapped_column(default=Plan.FREE)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id"), primary_key=True, index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), primary_key=True, index=True
    )
    role: Mapped[Role] = mapped_column(default=Role.MEMBER)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64), index=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    engine: Mapped[Engine] = mapped_column(default=Engine.PHASER3)
    current_build_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("builds.id"), index=True, default=None
    )
    visibility: Mapped[Visibility] = mapped_column(default=Visibility.PUBLIC)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Build(Base):
    __tablename__ = "builds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("projects.id"), index=True
    )
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    prompt: Mapped[str] = mapped_column(String())
    status: Mapped[BuildStatus] = mapped_column(default=BuildStatus.QUEUED)
    gdd: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), default=dict
    )
    plan: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSONB), default=list
    )
    verify_report: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB), default=dict
    )
    artifact_key: Mapped[str | None] = mapped_column(String(255), default=None)
    thread_id: Mapped[str | None] = mapped_column(String(255), index=True, default=None)
    parent_build_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("builds.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    build_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("builds.id"), index=True
    )
    kind: Mapped[ArtifactKind] = mapped_column()
    storage_key: Mapped[str] = mapped_column(String(255))
