# Architecture

The studio is split into a browser client, an API, a worker, and an isolated
sandbox. The browser calls `/api/v1` and consumes SSE. The API owns auth,
authorization, metadata, version records, signed media routes, and job
enqueueing. The worker claims Postgres jobs with `FOR UPDATE SKIP LOCKED`,
runs the Claude Agent SDK, and performs media work. The sandbox is the only
place where HyperFrames, FFmpeg, and Chromium are executed.

Projects have two sources of truth: `timeline.json` is mutated only through
validated timeline operations, and each HyperFrames composition is an HTML
folder referenced by a timeline graphics item. All project-scoped agent runs
start in the project directory with `setting_sources=["project"]`.

## Runtime flow

1. The web client uploads media through the streaming API route.
2. The API stores metadata and enqueues ingest work.
3. The worker creates a proxy, probe data, transcript, scenes, and thumbnails.
4. The agent reads those artifacts and uses typed domain tools to create a new
   timeline version or composition.
5. Render and composition PostToolUse hooks hard-fail mismatches.
6. A verified final render is passed to a blind reviewer before completion.

The in-memory repository keeps local tests and the API shell runnable without
Postgres. `services/api/db_models.py`, Alembic, and the queue SQL provide the
production persistence boundary.
