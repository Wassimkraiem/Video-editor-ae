# Local Services

The Compose stack starts Postgres, the FastAPI service, the background worker,
the Next.js web app, and a locked-down HyperFrames sandbox.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

`ANTHROPIC_API_KEY` must be an Anthropic Console API key. A Claude subscription
does not work as an API key for SDK/API calls.

- Web: http://localhost:3000
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/api/v1/healthz

The API and worker images run as a non-root user and share named volumes for
`/work/storage` and `/work/projects`. The API service runs migrations on start
before serving traffic.

The sandbox image uses system Chromium and FFmpeg, runs as a non-root user, has
no network, has a read-only root filesystem, drops Linux capabilities, and only
gets writable temporary storage through `/tmp`.

Useful commands:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs -f api worker
docker compose -f infra/docker-compose.yml down
docker compose -f infra/docker-compose.yml down -v
```

`down -v` deletes the local Postgres and project/storage volumes.
