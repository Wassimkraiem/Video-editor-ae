# AGENTS.md

Guide for coding agents working on this repository. Read this before editing.

## What this is

An AI video editing studio. A user uploads footage in the web app, picks a
style (for example `wassim-style`), and describes an edit. A Claude Agent SDK
session then edits the video inside an isolated per-project folder using
HyperFrames (HTML + GSAP compositions rendered to MP4), FFmpeg, and the
project's skills.

```
apps/web            Next.js 15 studio (React 19, Tailwind 3)
services/api        FastAPI: auth, projects, uploads, runs, renders, SSE
services/worker     Agent runtime, job handlers, ingest, sandbox policy
  quality_harness   SDK options, PostToolUse gates, review, project memory
packages/           Shared timeline schema (Python + TS) and OpenAPI client
skills/builtin      Small generic recipes (talking-head-cleanup, ...)
skills/library      House styles + the skills they call (see below)
infra/              Dockerfiles and docker-compose (Postgres stack)
tests/              pytest suite (API, worker, harness, sandbox)
```

## Run it

```bash
python -m venv .venv && .venv/Scripts/activate      # source .venv/bin/activate on macOS/Linux
pip install -e ".[dev,api,agent]"
pytest                                              # must stay green

python scripts/dev_api.py                           # API + in-process worker on :8010
npm --prefix apps/web install && npm --prefix apps/web run dev   # studio on :3010
```

Local dev needs no Postgres or Docker: with a non-Postgres `DATABASE_URL`
the API keeps data in memory and runs jobs in-process
(`services/api/local_worker.py`). `ffmpeg`/`ffprobe` and `npx` must be on
PATH. `ANTHROPIC_API_KEY` comes from `.env` (never commit it; `.env` is
git-ignored). The Docker stack (`infra/docker-compose.yml`) uses ports
3000/8000 and Postgres with a separate worker container.

## How an agent run works

1. `POST /projects/{id}/runs` with `brief` and optional `skill` creates a run.
   Multi-scene or motion-graphics briefs first write `storyboard.json` and
   wait for approval (`POST /runs/{id}/messages` with `Approve`).
2. The worker job (`services/worker/handlers.py`) calls
   `AgentSessionRunner.run` (`services/worker/agent_runtime.py`), which
   bootstraps the project folder, installs every skill into
   `<project>/.claude/skills/`, and calls the SDK `query()` with:
   - `cwd` = project folder, `setting_sources=["project"]`, `skills="all"`;
   - the in-process MCP server `video-editing` (`mcp_tools.py`);
   - `can_use_tool` = `ProjectSandboxPolicy` (`sandbox_policy.py`);
   - `PostToolUse` quality gates (`quality_harness/hooks.py`).
3. Every SDK message is emitted as an `agent.message` event (with `_type`
   such as `AssistantMessage`) and streamed to the studio over SSE.
4. A follow-up message resumes the same SDK session (`resume=sdk_session_id`).

## Rules that are easy to break

- **Never add `Bash`, `Write`, `Edit`, `MultiEdit` or `NotebookEdit` to
  `allowed_tools`.** Tools in that list are auto-approved and skip
  `can_use_tool`, which disables the sandbox. Only read-only and domain MCP
  tools belong in `AUTO_APPROVED_TOOLS`.
- MCP tools reach hooks and permissions as `mcp__video-editing__<name>`;
  `normalize_tool_name` strips the prefix. Hook matchers stay `None` and the
  registry filters by name.
- A failed quality gate returns `decision: "block"` with
  `additionalContext` so the agent repairs its work. Only the plan gate sets
  `continue_: False`.
- Agent file access is confined to the project folder; `raw/` is read-only.
  Bash runs exactly one allowlisted program (`npx hyperframes|skills`,
  `ffmpeg`, `ffprobe`, `node`, `python`) with no pipes or redirection.
- Media commands are argv lists (`services/worker/media.py`), never shell
  strings. Use `shutil.which("npx")` for subprocesses so Windows finds
  `npx.cmd`.
- `pydantic-settings` reads `.env` into `Settings` only. Anything the agent
  subprocess needs from the environment must be exported
  (`export_agent_environment` in `services/api/main.py`).
- Tests pin `DATABASE_URL=memory://` in `tests/conftest.py`; keep new tests
  independent of a developer's `.env`.
- Signed URLs (`LocalStorage.url`) are the credential for `<video>` tags.
  Only mint them for project owners; `/project-files` serves only
  `renders/`, `compositions/` and `proxies/`.

## Skills

`skills/library/` vendors the house styles from `~/.claude/skills`:
`wassim-style`, `devin-style`, `talking-head-glass-edit`,
`kinetic-editorial-reel`, `talking-head-recut`, `product-launch-*`,
`general-video`, plus `hyperframes*` and `media-use`, which the styles call.
`project_bootstrap.install_skills` copies `builtin` and `library` into each
project and refreshes a skill when its `SKILL.md` changes. Skill scripts find
sibling skills relative to their own path (see `build_sfx.py`), so they work
both in `~/.claude/skills` and in a project's `.claude/skills`.

To update a style, edit it in `skills/library/<name>/` (or re-copy it from
`~/.claude/skills`, then drop `__pycache__`/`.git`). The studio's style
picker lists every non-helper skill; featured order lives in
`apps/web/src/components/AgentPanel.tsx` (`FEATURED`).

## Conventions

- Python 3.12+, type hints, pydantic v2 models, `from __future__ import annotations`.
- Keep comments for the non-obvious "why"; match the surrounding density.
- Web: client components, Tailwind tokens from `tailwind.config.ts`
  (`ink`, `panel`, `line`, `accent`), shared primitives in
  `components/ui.tsx`, icons in `components/icons.tsx`. Run
  `npx tsc --noEmit -p apps/web` and `npm --prefix apps/web run build`.
- Add or update tests in `tests/` with every backend change.
