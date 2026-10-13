"""Async PostgreSQL persistence used by deployed API processes.

The memory repository remains useful for tests and an offline single-process
demo. This adapter keeps route code independent from SQLAlchemy while making
auth, projects, assets, timelines, and durable jobs survive restarts when a
Postgres URL is configured.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class PostgresPersistence:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.enabled = database_url.startswith(("postgresql://", "postgresql+asyncpg://"))
        self._engine = None
        self._sessions = None

    def _session_factory(self):
        if not self.enabled:
            return None
        if self._sessions is None:
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            self._engine = create_async_engine(self.database_url, pool_pre_ping=True)
            self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)
        return self._sessions

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def create_user(self, email: str, password_hash: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        from services.api.db_models import User

        record = User(email=email.lower(), password_hash=password_hash)
        async with self._session_factory()() as session:
            try:
                session.add(record)
                await session.commit()
                await session.refresh(record)
            except Exception:
                await session.rollback()
                return None
        return {"id": record.id, "email": record.email, "password_hash": record.password_hash, "created_at": record.created_at}

    async def user_by_email(self, email: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        from sqlalchemy import select
        from services.api.db_models import User

        async with self._session_factory()() as session:
            record = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        return None if record is None else {"id": record.id, "email": record.email, "password_hash": record.password_hash, "created_at": record.created_at}

    async def user_by_id(self, user_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        from sqlalchemy import select
        from services.api.db_models import User

        async with self._session_factory()() as session:
            record = await session.get(User, user_id)
        return None if record is None else {"id": record.id, "email": record.email, "password_hash": record.password_hash, "created_at": record.created_at}

    async def create_project(self, owner_id: str, name: str, workflow: str, profile: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
        from services.api.db_models import Project

        record = Project(id=project_id or str(uuid4()), owner_id=owner_id, name=name, workflow=workflow, profile=profile)
        async with self._session_factory()() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return self._project_dict(record)

    @staticmethod
    def _project_dict(record: Any) -> dict[str, Any]:
        return {"id": record.id, "owner_id": record.owner_id, "name": record.name, "workflow": record.workflow, "profile": record.profile or {}, "created_at": record.created_at, "updated_at": record.updated_at}

    async def project(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        from sqlalchemy import or_, select
        from services.api.db_models import Project, ProjectMember

        async with self._session_factory()() as session:
            query = select(Project).outerjoin(ProjectMember, ProjectMember.project_id == Project.id).where(Project.id == project_id, or_(Project.owner_id == user_id, ProjectMember.user_id == user_id))
            # One row per membership: take the first rather than demanding one.
            record = (await session.execute(query)).scalars().first()
        return None if record is None else self._project_dict(record)

    async def projects(self, user_id: str) -> list[dict[str, Any]]:
        from sqlalchemy import or_, select
        from services.api.db_models import Project, ProjectMember

        async with self._session_factory()() as session:
            # No DISTINCT: Postgres cannot compare the JSON ``profile`` column.
            # The outer join can repeat a project, so dedupe by id here.
            query = select(Project).outerjoin(ProjectMember, ProjectMember.project_id == Project.id).where(or_(Project.owner_id == user_id, ProjectMember.user_id == user_id)).order_by(Project.created_at.desc())
            records = (await session.execute(query)).scalars().all()
        unique = {record.id: record for record in records}
        return [self._project_dict(record) for record in unique.values()]

    async def update_project(self, project_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        from sqlalchemy import update
        from services.api.db_models import Project

        async with self._session_factory()() as session:
            await session.execute(update(Project).where(Project.id == project_id).values(**values, updated_at=datetime.now(timezone.utc)))
            await session.commit()
        async with self._session_factory()() as session:
            record = await session.get(Project, project_id)
        return None if record is None else self._project_dict(record)

    async def create_asset(self, values: dict[str, Any]) -> None:
        from services.api.db_models import Asset

        record = Asset(id=values["id"], project_id=values["project_id"], filename=values["filename"], kind=values["kind"], mime_type=values["mime_type"], size_bytes=values["size_bytes"], storage_key=values["storage_key"], probe_json=values.get("probe"), status=values["status"])
        async with self._session_factory()() as session:
            session.add(record)
            await session.commit()

    async def save_timeline_version(self, project_id: str, record: dict[str, Any], user_id: str | None = None) -> None:
        from services.api.db_models import TimelineVersion

        version = TimelineVersion(project_id=project_id, version=record["version"], schema_version=record["schema_version"], data_json=record["data"], diff_json=record.get("diff", []), parent_version=record.get("parent_version"), created_by=user_id)
        async with self._session_factory()() as session:
            session.add(version)
            await session.commit()

    async def enqueue_job(self, job_type: str, payload: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        from services.api.db_models import Job

        record = Job(type=job_type, payload=payload, status="queued", attempts=0)
        async with self._session_factory()() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return record.id

    async def create_agent_run(self, run_id: str, project_id: str, brief: str, budget: dict[str, Any]) -> None:
        if not self.enabled:
            return
        from services.api.db_models import AgentRun

        record = AgentRun(id=run_id, project_id=project_id, brief=brief, status="queued", budget_json=budget)
        async with self._session_factory()() as session:
            session.add(record)
            await session.commit()

    async def agent_run(self, run_id: str, user_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        from sqlalchemy import or_, select
        from services.api.db_models import AgentRun, Project, ProjectMember

        async with self._session_factory()() as session:
            query = select(AgentRun, Project).join(Project, Project.id == AgentRun.project_id).outerjoin(ProjectMember, ProjectMember.project_id == Project.id).where(AgentRun.id == run_id, or_(Project.owner_id == user_id, ProjectMember.user_id == user_id))
            row = (await session.execute(query)).first()
        if not row:
            return None
        run, project = row
        return {"id": run.id, "project_id": run.project_id, "status": run.status, "brief": run.brief, "sdk_session_id": run.sdk_session_id, "usage": run.budget_json or {}, "created_at": run.started_at or project.created_at}

    async def update_agent_run(self, run_id: str, values: dict[str, Any]) -> None:
        if not self.enabled:
            return
        from sqlalchemy import update
        from services.api.db_models import AgentRun

        async with self._session_factory()() as session:
            await session.execute(update(AgentRun).where(AgentRun.id == run_id).values(**values))
            await session.commit()

    async def add_agent_message(self, run_id: str, role: str, content: dict[str, Any]) -> None:
        if not self.enabled:
            return
        from services.api.db_models import AgentMessage

        async with self._session_factory()() as session:
            session.add(AgentMessage(run_id=run_id, role=role, content=content))
            await session.commit()

    async def add_job_event(self, stream_id: str, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        from services.api.db_models import JobEvent

        async with self._session_factory()() as session:
            session.add(JobEvent(stream_id=stream_id, event=event))
            await session.commit()

    async def latest_job_event_id(self) -> int:
        from sqlalchemy import func, select
        from services.api.db_models import JobEvent

        async with self._session_factory()() as session:
            return int((await session.execute(select(func.max(JobEvent.id)))).scalar() or 0)

    async def job_events_after(self, after_id: int, limit: int = 500) -> list[tuple[int, str, dict[str, Any]]]:
        from sqlalchemy import select
        from services.api.db_models import JobEvent

        async with self._session_factory()() as session:
            rows = (await session.execute(select(JobEvent.id, JobEvent.stream_id, JobEvent.event).where(JobEvent.id > after_id).order_by(JobEvent.id).limit(limit))).all()
        return [(int(row.id), str(row.stream_id), dict(row.event or {})) for row in rows]
