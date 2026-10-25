"""Export a finished HyperFrames video as an editable After Effects project (the ae-builder skill).

An agent run with the ``ae-builder`` skill reads the composition (HTML + GSAP: the exact timing
of every move is in the code) and writes ``exports/ae/<reel>/`` (the build ``.jsx``, README,
assets, fonts). The worker then zips that folder into ``renders/ae/<reel>_ae.zip`` so it can be
downloaded with a signed link like any render.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

SKILL = "ae-builder"
COMPOSITION = re.compile(r"^compositions/[A-Za-z0-9._-]+$")


def export_dir(composition: str) -> str:
    return f"exports/ae/{Path(composition).name}"


def zip_name(composition: str) -> str:
    return f"renders/ae/{Path(composition).name}_ae.zip"


def export_brief(composition: str, width: int | None, height: int | None, fps: float | None, duration_ms: int | None) -> str:
    """The run's request: the skill's method, adapted to the studio (no questions, fixed paths)."""

    out = export_dir(composition)
    size = f"{width}x{height}" if width and height else "the composition's data-width x data-height"
    return f"""Rebuild the finished video `{composition}/` as an editable After Effects project with the `ae-builder` skill.

The source is a HyperFrames composition: `{composition}/index.html` (HTML + a paused GSAP timeline;
every move's exact start, length and ease is in that code), plus its sub-compositions, `assets/`
and `fonts/`. Read the code for timing: do not track the MP4.

Answers to the skill's questions (do not ask the user, they are not watching this run):
- Resolution: {size}; frame rate: {fps or 30} fps; length: {round((duration_ms or 0) / 1000, 2) or "the composition's data-duration"} s.
- After Effects 2023 or later (JavaScript expression engine; keep feature detection).
- Footage: the script asks for the source clip when it runs (`assets/source.mp4` or the footage
  `<video>` in the composition); use a placeholder solid if the user cancels.

Studio rules that override the skill's paths:
- Work only inside the project folder. Write everything to `{out}/` (not /mnt/user-data or /home):
  `{out}/<Name>_Rebuild.jsx`, `{out}/README.txt`, `{out}/assets/`, `{out}/fonts/`, and keep your
  generator (`{out}/generator/`) and `keys.json`/`checks.json` there too.
- Fonts: copy the font files the composition already uses from `{composition}/fonts/` (and any it
  loads by name) into `{out}/fonts/`. Only run `scripts/fetch_fonts.py` for fonts that are missing.
- Copy images and other files the composition uses from `{composition}/assets/` into `{out}/assets/`
  (not the source footage).
- Run the skill's gate before finishing: `node .claude/skills/ae-builder/scripts/ae_mock_dryrun.js <jsx>`
  must report no issues, and `python .claude/skills/ae-builder/scripts/verify_curves.py` must pass.
  Commands here run one program with no shell features: instead of `DUMP_KEYS=keys.json node ...`
  (or SCALE2=1, ELSEWHERE=1, BREAK=...) pass `--set DUMP_KEYS=keys.json` after the .jsx path.
- The studio zips `{out}/` for the user when you finish: do not zip it yourself.

Finish with the skill's hand-off message (how to run it, comp map, controllers, worst easing
error, known gaps, and that it was verified in the mock, not in After Effects)."""


def zip_export(project: Path, composition: str) -> Path:
    """Zip the agent's export folder for download; raises when the build script is missing."""

    folder = project / export_dir(composition)
    if not any(folder.glob("*.jsx")):
        raise FileNotFoundError(f"The export has no .jsx build script in {export_dir(composition)}/")
    target = project / zip_name(composition)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(folder.rglob("*")):
            # The generator and verification files stay in the project; the user gets the deliverable.
            relative = path.relative_to(folder)
            if path.is_file() and relative.parts[0] not in ("generator", "__pycache__") and path.name not in ("keys.json", "checks.json"):
                bundle.write(path, Path(f"{Path(composition).name}_ae") / relative)
    shutil.move(temporary, target)
    return target
