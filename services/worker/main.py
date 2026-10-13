"""Worker entrypoint; production deployments connect this loop to Postgres."""

from __future__ import annotations

import logging
import os
import time
import asyncio
from pathlib import Path

from .handlers import WorkerContext, handle_job
from .jobs import InMemoryJobQueue, PostgresJobQueue

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("video-editor-worker")


def run_forever() -> None:
    worker_id = os.getenv("WORKER_ID", "local-worker")
    logger.info("worker_ready worker_id=%s", worker_id)
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        asyncio.run(_run_postgres(worker_id, database_url))
        return
    queue = InMemoryJobQueue()
    _run_local(queue, worker_id)


def _run_local(queue: InMemoryJobQueue, worker_id: str) -> None:
    context = WorkerContext(Path(os.getenv("PROJECTS_ROOT", "/work/projects")), Path(os.getenv("STORAGE_ROOT", "/work/storage")))
    while True:
        job = queue.claim(worker_id)
        if job is None:
            time.sleep(1)
            continue
        try:
            logger.info("job_started id=%s type=%s", job.id, job.type)
            queue.complete(job)
        except Exception as exc:  # pragma: no cover
            queue.fail(job, str(exc))


async def _run_postgres(worker_id: str, database_url: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    queue = PostgresJobQueue(sessions)
    from services.api.persistence import PostgresPersistence

    context = WorkerContext(Path(os.getenv("PROJECTS_ROOT", "/work/projects")), Path(os.getenv("STORAGE_ROOT", "/work/storage")), agent_persistence=PostgresPersistence(database_url))
    try:
        while True:
            job = await queue.claim(worker_id)
            if job is None:
                await asyncio.sleep(1)
                continue
            try:
                logger.info("job_started id=%s type=%s", job.id, job.type)
                await handle_job(job, context)
                await queue.complete(job)
            except Exception as exc:  # pragma: no cover - deployment retry path
                logger.exception("job_failed id=%s", job.id)
                await queue.fail(job, str(exc))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    run_forever()
