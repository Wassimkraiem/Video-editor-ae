"""Worker entrypoint; production deployments connect this loop to Postgres."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from .handlers import WorkerContext, failure_event, handle_job
from .jobs import JobRecord, PostgresJobQueue

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("video-editor-worker")

# Jobs run concurrently so an upload is ingested while an agent works, but
# only one agent session runs at a time per worker.
MAX_CONCURRENT_JOBS = int(os.getenv("WORKER_CONCURRENCY", "3"))
# Agent runs spend API credits and have side effects: never retry them
# automatically. The user can reply to the run to try again.
NO_RETRY = {"agent_run", "style_extraction"}


def run_forever() -> None:
    worker_id = os.getenv("WORKER_ID", "local-worker")
    logger.info("worker_ready worker_id=%s", worker_id)
    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith(("postgresql://", "postgresql+asyncpg://")):
        asyncio.run(_run_postgres(worker_id, database_url))
        return
    # Without Postgres there is no shared queue to claim from: the API runs
    # jobs in-process (services/api/local_worker.py) instead.
    logger.error("worker_requires_postgres: set DATABASE_URL to a postgresql:// URL, or run the API alone for local development (scripts/dev_api.py)")
    raise SystemExit(2)


async def _run_postgres(worker_id: str, database_url: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from services.api.persistence import PostgresPersistence

    engine = create_async_engine(database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    queue = PostgresJobQueue(sessions)
    persistence = PostgresPersistence(database_url)

    async def publish(stream_id: str, event: dict[str, Any]) -> None:
        # The API tails job_events to feed its SSE streams and state.
        try:
            await persistence.add_job_event(stream_id, json.loads(json.dumps(event, default=str)))
        except Exception:  # an event write must never fail the job itself
            logger.exception("job_event_write_failed stream=%s type=%s", stream_id, event.get("type"))

    context = WorkerContext(
        Path(os.getenv("PROJECTS_ROOT", "/work/projects")),
        Path(os.getenv("STORAGE_ROOT", "/work/storage")),
        event_sink=publish,
        agent_persistence=persistence,
    )
    slots = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    agent_lane = asyncio.Semaphore(1)
    running: set[asyncio.Task[None]] = set()

    async def execute(job: JobRecord) -> None:
        try:
            lane = agent_lane if job.type in NO_RETRY else None
            if lane:
                await lane.acquire()
            try:
                logger.info("job_started id=%s type=%s", job.id, job.type)
                await handle_job(job, context)
                await queue.complete(job)
            finally:
                if lane:
                    lane.release()
        except Exception as exc:  # deployment retry path
            logger.exception("job_failed id=%s type=%s", job.id, job.type)
            await queue.fail(job, str(exc), retry=job.type not in NO_RETRY)
            if job.status == "dead" and (failed := failure_event(job, str(exc) or type(exc).__name__)):
                await publish(*failed)
        finally:
            slots.release()

    try:
        while True:
            await slots.acquire()
            job = await queue.claim(worker_id)
            if job is None:
                slots.release()
                await asyncio.sleep(1)
                continue
            task = asyncio.create_task(execute(job))
            running.add(task)
            task.add_done_callback(running.discard)
    finally:
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
        await persistence.close()
        await engine.dispose()


if __name__ == "__main__":
    run_forever()
