"""Clone an editing style from reference videos into a reusable skill.

The worker downloads the references (the agent sandbox has no network),
then an agent session studies them and writes a skill shaped like
``wassim-style``. The finished skill is installed in the shared user-skills
folder, which every project picks up on its next run.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

USER_SKILLS_DIR = "_skills"
STYLES_DIR = "_styles"
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


def validate_user_urls(urls: list[str]) -> list[str]:
    if not urls:
        raise ValueError("At least one URL is required")
    cleaned: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Only credential-free http(s) URLs are accepted")
        host = parsed.hostname.lower()
        if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".local"):
            raise ValueError("Local network URLs are not allowed")
        cleaned.append(url)
    return cleaned


def slugify_skill_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:63]
    if not SKILL_NAME.match(slug):
        raise ValueError("Style name needs at least two letters or digits")
    return slug


def user_skills_root(projects_root: Path) -> Path:
    return projects_root / USER_SKILLS_DIR


def download_references(urls: list[str], target: Path) -> list[Path]:
    """Fetch each reference as an MP4 (up to 1080p) with yt-dlp."""

    from yt_dlp import YoutubeDL

    target.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    for index, url in enumerate(urls, start=1):
        options = {
            "outtmpl": str(target / f"{index}.%(ext)s"),
            "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*[height<=1080]+ba/b",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "max_filesize": 1024 * 1024 * 1024,
        }
        with YoutubeDL(options) as downloader:
            downloader.download([url])
        matches = sorted(target.glob(f"{index}.*"))
        if not matches:
            raise RuntimeError(f"Could not download {url}")
        files.append(matches[0])
    return files


# Proven engines a cloned style can fork. Each has a working pipeline
# (transcribe -> words.json -> captions -> beats -> build -> sfx -> render);
# a clone keeps the pipeline and restyles the look.
BASE_STYLES = {
    "wassim-style": "talking-head explainer: scene switches between full footage, a paper page with a card and a navy panel; caption pills with keyword boxes; headlines, browser shots, terminals, stat cards",
    "devin-style": "creator talking head on a studio background: big hard-swapped uppercase captions with one glowing keyword line, jump-cut punch-ins, zoom-blur whips, dark glass UI cards",
    "talking-head-glass-edit": "footage left untouched: small word-synced captions in the gaps, liquid-glass pop-up cards, big keyword cards, kinetic word-by-word text with self-drawing icons, slow punch-ins",
    "kinetic-editorial-reel": "faceless: word-by-word animated captions with one coloured keyword per line, a literal hero object per phrase, cream vs black scenes, slam hits, camera pushes",
}

FORK_SCRIPT = '''"""Fork a base style engine into the new skill: python tools/fork_base.py <base>"""
import re
import shutil
import sys
from pathlib import Path

NAME = {name!r}
BASES = {bases!r}
base = sys.argv[1] if len(sys.argv) > 1 else ""
source = Path(".claude/skills") / base
if base not in BASES or not (source / "SKILL.md").is_file():
    sys.exit("choose a base: " + ", ".join(BASES))
target = Path("skill-out") / NAME
shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
skill = target / "SKILL.md"
skill.write_text(re.sub(r"(?m)^name:.*$", "name: " + NAME, skill.read_text(encoding="utf-8"), count=1), encoding="utf-8")
(target / "BASE").write_text(base, encoding="utf-8")
print("forked", base, "into", target)
'''


def split_urls(values: list[str]) -> list[str]:
    """Accept URLs separated by commas, spaces or new lines."""

    return [url for value in values for url in re.split(r"[\s,]+", value) if url]


def fork_base(workspace: Path, name: str, base: str, skills_root: Path) -> None:
    """Copy a base engine into ``skill-out/<name>`` (renamed) before the agent starts."""

    source = skills_root / base
    target = workspace / "skill-out" / name
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    skill = target / "SKILL.md"
    skill.write_text(re.sub(r"(?m)^name:.*$", f"name: {name}", skill.read_text(encoding="utf-8"), count=1), encoding="utf-8")
    (target / "BASE").write_text(base, encoding="utf-8")


def write_fork_tool(workspace: Path, name: str) -> None:
    tools = workspace / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    (tools / "fork_base.py").write_text(FORK_SCRIPT.format(name=name, bases=list(BASE_STYLES)), encoding="utf-8")


STYLE_BRIEF = """Clone the EDITING STYLE of the reference video(s) below into the skill `{name}`. Copy the style, never the videos: no frames, footage, audio, logos, faces or on-screen text go into the skill.

References:
{references}
{notes}
## How to work
This is a restyle of a proven engine, not a skill written from scratch. Keep the base pipeline and the scripts that work (transcribe -> `edit/words.json` -> caption phrases and keywords -> beats / edit plan -> build -> sfx -> lint -> snapshot -> render) and change the look and motion to match the references.

1. {fork}
2. Study every reference. They may differ: extract what they share and note where one differs.
   - frames: `ffmpeg -i <ref> -vf "select=gt(scene\\,0.3),scale=540:-2" -vsync vfr analysis/frames/<n>-cut-%03d.jpg`, plus `-vf fps=2,scale=540:-2 -t 15` for the opening. Read the frames and look closely.
   - speech: `python .claude/skills/wassim-style/scripts/transcribe.py <ref>` to see how captions follow the words (chunk size, timing, which words get highlighted).
   - measure, and write `analysis/style-spec.json`: aspect ratio; cut and scene rhythm (seconds); caption font family, weight, case, size and position; how words appear (pop, fill, typewriter, swap); keyword treatment (colour box, glow, scale); palette (hex); background and grade; graphic elements (cards, chips, lower thirds, emojis, icons, screenshots, stickers); transitions (whip, zoom blur, wipe, cut); camera moves (punch-in amounts, easing); b-roll; SFX and music moments; overall energy.
3. Restyle the fork in `skill-out/{name}/`:
   - design tokens: add a palette preset and fonts (Google fonts HyperFrames can load offline, closest match) and make them the default;
   - captions: position, font, case, size, chunking, word-by-word animation and keyword treatment exactly as observed;
   - scenes and graphics: adapt or add beat / scene types so the reference's recurring visuals exist; drop base visuals the references never use from the defaults;
   - motion: durations and eases of entrances, exits, scene switches and pushes; transitions as observed;
   - SFX: map the reference's sound moments to names in `.claude/skills/media-use/audio/assets/sfx`;
   - keep `fast.json` working if the base has one: the studio's cheap fast edits run your style through it (setup, plan files, build). Update it if you add plan files or setup steps;
   - rewrite `SKILL.md` (frontmatter `name: {name}`, a description of the look with trigger phrases including "{name}") and `references/style-guide.md` with the spec. Keep the commands and file names the pipeline relies on.
4. Write these content-matching rules into `SKILL.md` and bake them into the engine defaults:
   - every animation, scene switch, card and sound starts on a word onset from `edit/words.json`, never at arbitrary times;
   - each beat's visual is chosen from what is said at that moment (keywords, numbers, names, lists and tools get their matching graphic);
   - pacing follows the speaker's energy and the reference vibe: calm delivery gets fewer, slower moves, punchy delivery gets faster cuts;
   - captions and graphics never fight: a graphic appears on the phrase it illustrates, and captions hide or move only the way the references do.
5. Prove it: in `test-run/`, build a 10-15 s sample with the new skill on the opening of reference 1 (its words as the transcript), run `npx hyperframes lint test-run/<project>` and `npx hyperframes snapshot` at 4 moments, then compare the snapshots with the reference frames. Fix colours, fonts, sizes, positions and motion until they match, and say what still differs.

The run is non-interactive. Finish with a short summary: the base used, what changed, and how close the sample is.
"""


def style_brief(name: str, references: list[str], notes: str, base: str | None) -> str:
    if base:
        fork = f"The base engine `{base}` is already forked into `skill-out/{name}/` (SKILL.md renamed). Read it fully first."
    else:
        options = "\n".join(f"   - `{key}`: {value}" for key, value in BASE_STYLES.items())
        fork = f"Pick the base engine closest to the references (structure and scene system, not colours):\n{options}\n   then fork it with `python tools/fork_base.py <base>` (copies it into `skill-out/{name}/`, renamed)."
    user_notes = f"\n## The user's notes (they override the references)\n{notes.strip()}\n" if notes.strip() else ""
    return STYLE_BRIEF.format(name=name, references="\n".join(f"- `{path}`" for path in references), notes=user_notes, fork=fork)


def install_user_skill(workspace: Path, name: str, projects_root: Path) -> Path:
    """Validate the agent's skill and publish it for every project."""

    from .skill_parser import parse_skill, repair_skill_file

    source = workspace / "skill-out" / name
    repair_skill_file(source / "SKILL.md")
    package = parse_skill(source / "SKILL.md")
    if package.frontmatter.name != name:
        raise ValueError(f"SKILL.md names the skill {package.frontmatter.name!r}, expected {name!r}")
    target = user_skills_root(projects_root) / name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.mp4", "*.mov", "*.webm"))
    return target


def skill_summary(skill_dir: Path) -> dict[str, Any]:
    from .skill_parser import parse_skill

    package = parse_skill(skill_dir / "SKILL.md")
    return {"name": package.frontmatter.name, "description": " ".join(package.frontmatter.description.split()), "body": (skill_dir / "SKILL.md").read_text(encoding="utf-8"), "fast": True, "engine": "style" if (skill_dir / "fast.json").is_file() else "generic"}
