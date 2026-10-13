# Quality harness

The worker uses Claude Agent SDK features as the source of truth for project
settings, tool execution, subagents, plan approval, and compaction. `quality_harness` adds
the domain checks that must run around those SDK calls.

## Project memory

`create_project_memory()` creates `CLAUDE.md` once from a project profile. The
run options returned by `load_project_settings()` include
`setting_sources=["project"]`, so the SDK loads the file and project skills.
The append helper rejects writes without an explicit approval flag.

## Hard verification gates

The worker registers `PostToolUse` gates for `render_preview`, `render_final`,
and `write_composition`. Renders are probed with ffprobe and compared with the
captured timeline for duration, dimensions, frame rate, and integrated
loudness. Composition writes run the pinned `npx hyperframes validate` command.
A failed hook returns `continue_=false` with an updated failed tool output, so
Claude must repair the render or composition before it can report success.

## Plans and review

Runs with multiple scenes or motion graphics write `storyboard.json`, surface
it through the web `StoryboardPanel`, and call the SDK `ask_user` tool before
composition or render work. After verification, `review_with_retries()` gives
a blind reviewer subagent only the original brief, timeline, frame extracts, and
verification report. It has `setting_sources=[]`, no filesystem tools, and a
failure can trigger at most two editing cycles.

`run_project_query()` uses the SDK's `query()` for one-shot work and
`run_project_chat()` uses `ClaudeSDKClient` for continuing chat sessions. The
harness never replaces either SDK loop.

## Context and evals

Transcripts, scene data, and composition HTML live under `.agent-context/` and
are read in bounded slices. Claude Code's CLI owns automatic compaction; the
SDK adapter keeps it enabled and sets `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80`.
The harness pins `CLAUDE.md` and `storyboard.json` as reloadable files and never
places full transcripts in the prompt. The fixed ten-case suite is in
`evals/quality_eval_set.json`; CI runs its contract and stores pass rate and
cost in the workflow artifact.
