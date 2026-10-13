"""Durable job enqueueing with a local fallback for tests and offline work."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4


async def enqueue_postgres_job(database_url: str, job_type: str, payload: dict[str, Any]) -> str | None:
    """Insert a job when PostgreSQL is configured.

    The API keeps its in-memory repository for fast local development, but a
    deployed process must also publish into the shared Postgres queue used by
    workers. The import is lazy so the pure unit-test install has no database
    driver requirement.
    """

    if not database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        return None
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    job_id = str(uuid4())
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO jobs (id, type, payload, status, attempts, run_after) "
                    "VALUES (:id, :type, CAST(:payload AS jsonb), 'queued', 0, :run_after)"
                ),
                {"id": job_id, "type": job_type, "payload": json.dumps(payload), "run_after": datetime.now(timezone.utc)},
            )
    finally:
        await engine.dispose()
    return job_id
