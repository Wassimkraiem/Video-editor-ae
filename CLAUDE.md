@AGENTS.md

## Claude Code notes

- This file is for developing the studio. Each *user project* gets its own
  generated `CLAUDE.md` (project memory, `quality_harness/project_memory.py`)
  inside its workspace under `PROJECTS_ROOT`; do not confuse the two.
- `.claude/launch.json` defines `api` (scripts/dev_api.py, port 8010) and
  `web` (Next dev, port 3010) for the preview browser. The Docker stack may
  already be running on 3000/8000; leave it alone.
- The style skills in `skills/library/` are the same ones installed in
  `~/.claude/skills`. When the user edits a style there, offer to sync the
  copy in this repo.
- Real agent runs spend the user's Anthropic credits. Verify wiring with the
  tests (`tests/test_sdk_adapter.py` builds real `ClaudeAgentOptions`) and
  ask before starting a live run.
- Use the `.venv` interpreter (`.venv/Scripts/python` on Windows).
