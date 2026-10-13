"""Run the API for local development with the in-process worker.

Uses the in-memory repository and `./.local/` for uploads and project
workspaces, so no Postgres or Docker is needed. Values already set in the
shell win; `.env` still supplies ANTHROPIC_API_KEY and AGENT_MODEL.

    python scripts/dev_api.py [--port 8010] [--reload]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    local = ROOT / ".local"
    # Environment variables take precedence over `.env` in pydantic-settings,
    # so these override the Docker-oriented paths and Postgres URL there.
    os.environ.setdefault("DATABASE_URL", "memory://")
    os.environ.setdefault("STORAGE_ROOT", str(local / "storage"))
    os.environ.setdefault("PROJECTS_ROOT", str(local / "projects"))
    os.environ.setdefault("LOCAL_WORKER_ENABLED", "true")
    os.environ.setdefault("WEB_ORIGIN", "http://localhost:3010")
    os.chdir(ROOT)

    import uvicorn

    uvicorn.run("services.api.main:app", host="127.0.0.1", port=args.port, reload=args.reload, reload_dirs=[str(ROOT / "services"), str(ROOT / "packages")] if args.reload else None)


if __name__ == "__main__":
    main()
