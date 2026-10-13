# AI Video Editing Studio

This repository contains a runnable vertical slice of the AI video editing
studio. It includes the browser shell, FastAPI API, worker boundaries, shared
timeline schema, sandbox definition, skills, HyperFrames composition starter,
and the Claude Agent SDK quality harness.

The worker harness provides:

- project `CLAUDE.md` memory created from a profile and loaded with
  `setting_sources=["project"]`;
- `PostToolUse` verification for render and composition tools;
- storyboard plan mode with an explicit `ask_user` approval gate;
- a blind SDK reviewer subagent with a maximum of two repair cycles;
- file-backed transcript, scene, and composition context slices;
- a fixed ten-case evaluation set with CI reporting of pass rate and cost.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,api]'
pytest

# optional browser dependencies
cd apps/web && npm ci && cd ../..
```

To run all services with PostgreSQL and the sandbox:

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

Then open http://localhost:3000. FastAPI docs are at http://localhost:8000/docs.

The worker environment installs the SDK with `pip install -e '.[agent]'` in
addition to the API dependencies. The worker calls `query()` for one-shot runs
and `ClaudeSDKClient` for continuing sessions. Media gates use typed FFmpeg and
ffprobe commands, while HyperFrames work stays in the sandbox.

Three workflows are supported by the project shell: raw footage/talking-head
editing, motion graphics, and no-talking-head explainers. Each creates a
project, accepts streamed assets or a brief, runs agent work through the API,
surfaces storyboard approval when needed, and exposes render progress over SSE.
