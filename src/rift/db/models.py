from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict


class Base(DeclarativeBase):
    pass


class PLAN(StrEnum):
    FREE = "free"
    PRO = "pro"

class ROLE(StrEnum):
    MEMBER = "member"
    VIEWER = "viewer"
    OWNER = "owner"

class ENGINE(StrEnum):
    PHASER3 = "phaser3"
    3DENGINE = "3d-engine"

class VISIBILITY(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"

class KIND(StrEnum):
    SOURCE = "source"
    SCREENSHOT = "screenshot"
    TRACE = "trace"
    STATIC_BUNDLE = "static-bundle"

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64))
    auth_system: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64))
    plan: Mapped[PLAN] = mapped_column(default=PLAN.FREE)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[str] = mapped_column(String(64), index=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[ROLE] = mapped_column(default=ROLE.MEMBER)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64))
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    prompt:Mapped[str] = mapped_column(String())
    gdd:Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSONB), default=dict)
    plan: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSONB), default=dict)
    verify_report: Mapped[dict[str, Any]] = mapped_column(MutableDict.as_mutable(JSONB), default=dict)
    engine: Mapped[ENGINE] = mapped_column(default=ENGINE.PHASER3)
    current_build_id: Mapped[str] = mapped_column(String(64), index=True, default=None)
    visibility:Mapped[VISIBILITY] = mapped_column(default=VISIBILITY.PUBLIC)

class Build(Base):
    __tablename__="builds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_key: Mapped[str] = mapped_column(String(64), default=None)
    parent_build_id: Mapped[str] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime] = mapped_column(default=None)

class Artifact(Base):
    __tablename__="artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    build_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[KIND] = mapped_column(default=None)
    storage_key: Mapped[str] = mapped_column(String(64), default=None)
