"""Postgres job-queue contract with SKIP LOCKED semantics and local fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported only by type checkers
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

INTERRUPTED = "Interrupted: the worker restarted while this was running. Start it again."

@dataclass
class JobRecord:
    type: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "queued"
    attempts: int = 0
    run_after: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    locked_by: str | None = None
    locked_at: datetime | None = None
    last_error: str | None = None


class InMemoryJobQueue:
    def __init__(self):
        self.jobs: list[JobRecord] = []

    def enqueue(self, job_type: str, payload: dict[str, Any]) -> JobRecord:
        job = JobRecord(job_type, payload)
        self.jobs.append(job)
        return job

    def claim(self, worker_id: str) -> JobRecord | None:
        for job in self.jobs:
            if job.status == "queued":
                job.status = "running"
                job.attempts += 1
                job.locked_by = worker_id
                job.locked_at = datetime.now(timezone.utc)
                return job
        return None

    def complete(self, job: JobRecord) -> None:
        job.status = "succeeded"

    def fail(self, job: JobRecord, error: str) -> None:
        job.status = "dead" if job.attempts >= 3 else "queued"
        job.last_error = error
        job.run_after = datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** max(job.attempts - 1, 0)))


class PostgresJobQueue:
    """Postgres-backed queue used by deployed API and worker processes.

    Claiming is one transaction with ``FOR UPDATE SKIP LOCKED`` so multiple
    workers can safely share the queue without a broker or a duplicate job.
    """

    def __init__(self, sessions: "async_sessionmaker[AsyncSession]", *, max_attempts: int = 3):
        self.sessions = sessions
        self.max_attempts = max_attempts

    async def claim(self, worker_id: str) -> JobRecord | None:
        async with self.sessions() as session:
            from sqlalchemy import text

            result = await session.execute(text(POSTGRES_CLAIM_SQL), {"worker_id": worker_id})
            row = result.mappings().first()
            await session.commit()
        if not row:
            return None
        return JobRecord(
            id=str(row["id"]),
            type=str(row["type"]),
            payload=dict(row["payload"] or {}),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            run_after=row.get("run_after") or datetime.now(timezone.utc),
            locked_by=row.get("locked_by"),
            locked_at=row.get("locked_at"),
            last_error=row.get("last_error"),
        )

    async def recover(self, worker_id: str, no_retry: set[str]) -> list[JobRecord]:
        """Release jobs this worker id still holds from before a restart.

        A worker restarts with the same id, so anything still marked running
        under it was cut off mid-way. Jobs that are safe to repeat go back in
        the queue; the rest are marked dead and returned so the caller can
        tell the user (they would otherwise show "running" forever).
        """

        from sqlalchemy import text

        async with self.sessions() as session:
            result = await session.execute(text("SELECT * FROM jobs WHERE status='running' AND locked_by=:worker_id FOR UPDATE"), {"worker_id": worker_id})
            rows = list(result.mappings())
            dead: list[JobRecord] = []
            for row in rows:
                status = "dead" if row["type"] in no_retry else "queued"
                await session.execute(
                    text("UPDATE jobs SET status=:status, last_error=:error, locked_by=NULL, locked_at=NULL, run_after=now() WHERE id=:id"),
                    {"status": status, "error": INTERRUPTED, "id": row["id"]},
                )
                if status == "dead":
                    dead.append(JobRecord(id=str(row["id"]), type=str(row["type"]), payload=dict(row["payload"] or {}), status=status, attempts=int(row["attempts"])))
            await session.commit()
        return dead

    async def complete(self, job: JobRecord) -> None:
        async with self.sessions() as session:
            from sqlalchemy import text

            await session.execute(text("UPDATE jobs SET status='succeeded', locked_by=NULL, locked_at=NULL WHERE id=:id"), {"id": job.id})
            await session.commit()
        job.status = "succeeded"

    async def fail(self, job: JobRecord, error: str, *, retry: bool = True) -> None:
        next_status = "dead" if not retry or job.attempts >= self.max_attempts else "queued"
        async with self.sessions() as session:
            from sqlalchemy import text

            await session.execute(
                text("UPDATE jobs SET status=:status, last_error=:error, locked_by=NULL, locked_at=NULL, run_after=:run_after WHERE id=:id"),
                {"status": next_status, "error": error[:4000], "id": job.id, "run_after": datetime.now(timezone.utc) + timedelta(seconds=min(300, 2 ** max(job.attempts - 1, 0)))},
            )
            await session.commit()
        job.status = next_status
        job.last_error = error


POSTGRES_CLAIM_SQL = """
UPDATE jobs
SET status = 'running', attempts = attempts + 1, locked_by = :worker_id,
    locked_at = now()
WHERE id = (
  SELECT id FROM jobs
  WHERE status = 'queued' AND run_after <= now()
  ORDER BY run_after, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING *
"""
