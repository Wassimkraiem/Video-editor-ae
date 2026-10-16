# AI Video Editing Studio

Upload a clip, pick a style, describe the edit — a Claude Agent SDK session
cuts, captions and animates it with HyperFrames, checks its own work, and
renders an MP4 you can preview in the browser.

- **Web studio** (`apps/web`): projects, media library with live ingest
  status, video preview of sources and outputs, timeline, a chat-style agent
  panel with a style picker, storyboard approval, and an editor for each
  project's `CLAUDE.md` memory.
- **API** (`services/api`): auth, projects, streamed uploads, runs, renders,
  signed media URLs, SSE event streams.
- **Worker** (`services/worker`): ingest (probe, proxy, audio, thumbnails),
  the agent runtime, HyperFrames/FFmpeg renders, and the quality harness.
- **Skills** (`skills/`): your house styles — `wassim-style`, `devin-style`,
  `talking-head-glass-edit`, `kinetic-editorial-reel`, … — plus the
  `hyperframes*` and `media-use` skills they build on. Every project gets
  them in `.claude/skills/` and the agent loads them with `skills="all"`.

## Quality harness

- Project `CLAUDE.md` memory, loaded with `setting_sources=["project"]`.
- A sandbox `can_use_tool` policy: file access stays in the project, `raw/`
  is read-only, Bash runs one allowlisted program with no shell tricks.
- `PostToolUse` gates: HyperFrames lint on every composition write, plan
  gate on renders; failures are fed back so the agent repairs its work.
- Storyboard approval for multi-scene and motion-graphics briefs.
- ffprobe verification of renders and a blind reviewer for final renders.
- A fixed evaluation set reported in CI.

## Run locally (no Docker)

Requires Python 3.12+, Node 22, and `ffmpeg`/`ffprobe` on PATH.

```bash
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,api,agent,skills]"
cp .env.example .env              # then set ANTHROPIC_API_KEY
pytest

python scripts/dev_api.py         # API + in-process worker → http://localhost:8010/docs
npm --prefix apps/web install
npm --prefix apps/web run dev     # studio → http://localhost:3010
```

Local mode keeps data in memory (it resets when the API restarts) and stores
uploads and project workspaces in `.local/`.

## Run with Docker (Postgres + separate worker)

```bash
cp .env.example .env              # set ANTHROPIC_API_KEY and WHISPER_MODELS_HOST_DIR
python scripts/fetch_models.py    # once: faster-whisper large-v3 into ~/.cache/fw-large-v3
docker compose --env-file .env -f infra/docker-compose.yml up -d --build
```

The worker mounts `WHISPER_MODELS_HOST_DIR` read-only at `/models`, or your
`~/.cache` when it is unset (Compose reads variables only from a `.env` beside
the compose file, so `--env-file .env` is what makes a custom path apply).
Edits never download speech models; a missing model fails fast instead.

Then open http://localhost:3000. FastAPI docs are at http://localhost:8000/docs.

## Workflows

Raw footage / talking-head editing, motion graphics, and no-talking-head
explainers. Each run streams the agent's messages, tool calls and skill use to
the studio; reply in the same panel to continue the session. Finished videos
in the project's `renders/` (or a composition folder) show up under the
preview player.

See [AGENTS.md](AGENTS.md) for architecture and contributor rules, and
[docs/](docs/) for the API routes, harness, and composition notes.
