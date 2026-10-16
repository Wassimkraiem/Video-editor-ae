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

## Fast edit (the default, cheap path)

Every style runs as a fast edit (`mode: "fast"`, the default). Styles that
ship a `fast.json` (wassim-style, devin-style, talking-head-glass-edit, and
clones forked from them) use their own engine (`fast_engine: "style"`).
Every other style, including newly cloned or uploaded ones, uses the generic
engine in `services/worker/fast_generic/` (`fast_engine: "generic"`): one
call writes the whole `index.html` from the style's SKILL.md plus
`ENGINE.md` (the HyperFrames contract and the three fonts `check.py` puts in
`fonts/`), `check.py` lint-gates it, and follow-ups revise the file on disk,
so Studio hand edits are kept. It also works with no footage. Only helper
skills (`hyperframes*`, `media-use`) are excluded (`fast_edit.is_style`).
Glass's engine is `scripts/build_glass.py`: one `edit/plan.json`
becomes index/graphics/kinetic/captions, and it hides any caption that would
show while a card is up (the style's gap-only rule). A `spec` entry like
`scripts/x.py:doc` sends only that script's docstring to the planner.
`services/worker/fast_edit.py` runs the engine's own `setup` scripts (reused
per clip), copies the user's reviewed `words.json`, asks Claude ONCE for the
plan files listed in `plan_files` (the style's SKILL.md and style guide are
the spec), runs the `build` scripts, retries a failed build with at most two
repair calls, and renders. Follow-ups revise the stored plan
(`.agent-context/fast/<run>.json`). `FAST_EDIT_MODEL` / `FAST_EDIT_EFFORT`
tune the planning call. `mode: "agent"` keeps the full Claude Code agent,
which now loads only the chosen style plus its helper skills
(`handlers.skills_for`). Transcripts are the user's: neither path corrects
words. The ingest cleanup pass runs on Haiku (`TRANSCRIPT_CLEANUP=off`
disables it).

- **Resources**: uploads with form field `role=resource` (stored under
  `projects/<id>/resources/`, which is how the role survives replays) are
  probed but never transcribed or picked as the clip. Runs and follow-up
  messages take `resources: [asset ids]`; fast edits copy them into
  `<composition>/assets/resources/` and list them in the plan prompt, and
  agent turns get `agent_tools.resource_brief`.
- **Cost caching across videos**: the planner's system prompt is the style
  docs only (byte-identical per style), and both paths set
  `ENABLE_PROMPT_CACHING_1H` (`PROMPT_CACHE_1H=0` turns it off). Agent runs
  also keep per-style notes (`services/worker/style_notes.py`,
  `<PROJECTS_ROOT>/_style_notes/<skill>.md`) that the next run in that style
  reads first.

## Studio, history and styles

- **Hand editing** uses HyperFrames Studio, embedded as an iframe
  (`apps/web/src/components/StudioPanel.tsx`). `POST /projects/{id}/studio`
  queues a `studio_open` job; the worker's `StudioManager`
  (`services/worker/studio.py`) runs `npx hyperframes preview <dir>` and, in
  Docker, a TCP forwarder on published ports 3400-3409 (Studio itself binds
  127.0.0.1). Studio writes edits into the composition files; Render picks
  them up. The timeline panel reads the same composition
  (`services/api/composition_timeline.py`).
- **History**: with Postgres, `job_events` is the source of truth. Creation
  events carry the full record (`run.created`, `asset.uploaded`,
  `render.created`, `style.created`), state changes follow, and
  `event_state.apply_event` folds them into the in-memory repo. The API
  replays the log on startup and tails it for worker events; API-originated
  events go through `publish_event` (tagged `eid` so the tail skips them).
- **Transcripts**: ingest transcribes every clip with audio (local
  faster-whisper large-v3, `services/worker/transcription.py`) into
  `proxies/<asset>/transcript.json` (studio format), `words.json` (the skills'
  `edit/words.json` format) and `transcript.meta.json`. The Transcript tab
  edits it (`PUT /assets/{id}/transcript`, which marks it reviewed);
  `POST /assets/{id}/transcribe {language}` re-runs Whisper. The agent is
  told to use these files instead of re-transcribing.
  The default language `tn` (Tunisian) runs Whisper as Arabic with a Darija
  prompt, then `clean_mixed` asks Claude (Agent SDK, no tools) to put
  French/English back in Latin script; it may merge words but `apply_spans`
  keeps Whisper's timing, and a failure keeps the raw words
  (`transcript.raw.json`). Every agent turn starts with `media_brief`: each
  clip with its full timed transcript and review status; runs wait for
  clips still marked `.transcribing`.
- **Style cloning**: `POST /style-extractions {urls, name, notes}` queues
  `style_extraction`; `clone_style` downloads with yt-dlp (outside the agent
  sandbox), runs an agent with `style_brief`, validates `skill-out/<name>`,
  and installs it into `<PROJECTS_ROOT>/_skills`, which `bootstrap_project`
  adds to every project's skills.

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
- Agent runs set `WHISPER_OFFLINE=1`/`HF_HUB_OFFLINE=1`: the skills'
  `transcribe.py` loads faster-whisper `large-v3` from `$WHISPER_MODELS_DIR`
  or `~/.cache/fw-large-v3` and never downloads. Docker mounts
  `WHISPER_MODELS_HOST_DIR` (default: the host's `~/.cache`) at `/models`.
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
