from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rift.db.models import (
    Artifact,
    ArtifactKind,
    Build,
    BuildStatus,
    Engine,
    Membership,
    Organization,
    Plan,
    Project,
    Role,
    User,
    Visibility,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, *, user_id: str, name: str, email: str, auth_system: str
    ) -> User:
        row = User(id=user_id, name=name, email=email, auth_system=auth_system)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, *, user_id: str) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, *, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        org_id: str,
        name: str,
        slug: str,
        plan: Plan = Plan.FREE,
    ) -> Organization:
        row = Organization(id=org_id, name=name, slug=slug, plan=plan)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, *, org_id: str) -> Organization | None:
        stmt = select(Organization).where(Organization.id == org_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, *, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        org_id: str,
        user_id: str,
        role: Role = Role.MEMBER,
    ) -> Membership:
        row = Membership(org_id=org_id, user_id=user_id, role=role)
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get(self, *, org_id: str, user_id: str) -> Membership | None:
        stmt = select(Membership).where(
            Membership.org_id == org_id,
            Membership.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(self, *, org_id: str) -> list[Membership]:
        stmt = select(Membership).where(Membership.org_id == org_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_user(self, *, user_id: str) -> list[Membership]:
        stmt = select(Membership).where(Membership.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        project_id: str,
        org_id: str,
        name: str,
        slug: str,
        engine: Engine = Engine.PHASER3,
        visibility: Visibility = Visibility.PUBLIC,
    ) -> Project:
        row = Project(
            id=project_id,
            org_id=org_id,
            name=name,
            slug=slug,
            engine=engine,
            visibility=visibility,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, *, org_id: str, project_id: str) -> Project | None:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.org_id == org_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, *, org_id: str, slug: str) -> Project | None:
        stmt = select(Project).where(
            Project.slug == slug,
            Project.org_id == org_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(self, *, org_id: str) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.org_id == org_id)
            .order_by(Project.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_current_build(
        self, *, org_id: str, project_id: str, build_id: str
    ) -> Project | None:
        row = await self.get_by_id(org_id=org_id, project_id=project_id)
        if row is None:
            return None
        row.current_build_id = build_id
        await self.session.commit()
        await self.session.refresh(row)
        return row


class BuildRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        build_id: str,
        project_id: str,
        org_id: str,
        prompt: str,
        thread_id: str | None = None,
        parent_build_id: str | None = None,
    ) -> Build:
        row = Build(
            id=build_id,
            project_id=project_id,
            org_id=org_id,
            prompt=prompt,
            thread_id=thread_id or build_id,
            parent_build_id=parent_build_id,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, *, org_id: str, build_id: str) -> Build | None:
        stmt = select(Build).where(
            Build.id == build_id,
            Build.org_id == org_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(self, *, org_id: str, project_id: str) -> list[Build]:
        stmt = (
            select(Build)
            .where(
                Build.project_id == project_id,
                Build.org_id == org_id,
            )
            .order_by(Build.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        *,
        org_id: str,
        build_id: str,
        status: BuildStatus,
        finished: bool = False,
    ) -> Build | None:
        row = await self.get_by_id(org_id=org_id, build_id=build_id)
        if row is None:
            return None
        row.status = status
        if finished:
            row.finished_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def update_outputs(
        self,
        *,
        org_id: str,
        build_id: str,
        brief: dict[str, Any] | None = None,
        gdd: dict[str, Any] | None = None,
        plan: list[dict[str, Any]] | None = None,
        verify_report: dict[str, Any] | None = None,
        artifact_key: str | None = None,
    ) -> Build | None:
        row = await self.get_by_id(org_id=org_id, build_id=build_id)
        if row is None:
            return None
        if brief is not None:
            row.brief = brief
        if gdd is not None:
            row.gdd = gdd
        if plan is not None:
            row.plan = plan
        if verify_report is not None:
            row.verify_report = verify_report
        if artifact_key is not None:
            row.artifact_key = artifact_key
        await self.session.commit()
        await self.session.refresh(row)
        return row


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        artifact_id: str,
        build_id: str,
        kind: ArtifactKind,
        storage_key: str,
    ) -> Artifact:
        row = Artifact(
            id=artifact_id,
            build_id=build_id,
            kind=kind,
            storage_key=storage_key,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def get_by_id(self, *, artifact_id: str) -> Artifact | None:
        stmt = select(Artifact).where(Artifact.id == artifact_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_build(self, *, build_id: str) -> list[Artifact]:
        stmt = select(Artifact).where(Artifact.build_id == build_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

