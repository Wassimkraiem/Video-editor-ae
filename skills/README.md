# Skills

Every project gets these skills copied into `<project>/.claude/skills/` at
run start (`services/worker/project_bootstrap.py`), and the agent session
enables them with `skills="all"`. A skill is refreshed in existing projects
when its `SKILL.md` changes.

- `builtin/` — small generic recipes (talking-head cleanup, lower thirds,
  vertical reframe, explainers, launch promos).
- `library/` — the house styles and the skills they depend on:
  - styles: `wassim-style`, `devin-style`, `talking-head-glass-edit`,
    `kinetic-editorial-reel`, `talking-head-recut`, `product-launch-video`,
    `product-launch-motion`, `general-video`;
  - helpers: `hyperframes`, `hyperframes-*` (core, animation, audio, cli,
    creative, keyframes, registry, studio) and `media-use` (SFX library,
    transcription, background removal).

The studio's style picker lists every non-helper skill. Picking one tells the
agent to invoke it with the Skill tool.

`library/` is a copy of `~/.claude/skills`. After editing a style there,
re-copy it here (skip `__pycache__/` and `.git/`). Scripts locate sibling
skills relative to their own folder, so the same files work in both places.

Uploaded skill archives are stored separately and their scripts cannot run
until `approve-scripts` is called.
