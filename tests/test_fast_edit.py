import asyncio
import json
import sys
from pathlib import Path

import pytest

from services.worker import fast_edit
from services.worker.fast_edit import FastManifest, _parse_plan, _resolve, run_fast_edit, skill_supports_fast


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "p1"
    folder = project / "proxies" / "a1"
    folder.mkdir(parents=True)
    (project / "raw").mkdir()
    (project / "raw" / "clip.mp4").write_bytes(b"x")
    (folder / "asset.json").write_text(json.dumps({"id": "a1", "filename": "clip.mp4", "path": str(project / "raw" / "clip.mp4"), "probe": {"duration_ms": 4000, "width": 1080, "height": 1920}}), encoding="utf-8")
    (folder / "words.json").write_text(json.dumps([{"t": "هيا", "s": 0.0, "e": 0.4}, {"t": "الـAI", "s": 0.4, "e": 0.9}]), encoding="utf-8")
    return project


class FakeEngine:
    """Stands in for npx/python: init makes index.html, render writes the mp4."""

    def __init__(self, fail_builds: int = 0):
        self.calls: list[list[str]] = []
        self.fail_builds = fail_builds

    def __call__(self, argv, cwd, timeout):
        self.calls.append(argv)
        if "init" in argv:
            target = Path(cwd) / argv[argv.index("init") + 1]
            target.mkdir(parents=True, exist_ok=True)
            (target / "index.html").write_text("<div></div>", encoding="utf-8")
        if "prep_cutout.py" in " ".join(argv):
            (Path(cwd) / "assets").mkdir(exist_ok=True)
            (Path(cwd) / "assets" / "source.mp4").write_bytes(b"x")
        if "build_comp.py" in " ".join(argv) and self.fail_builds:
            self.fail_builds -= 1
            return 1, "KeyError: 'mode'"
        if "render" in argv:
            Path(argv[argv.index("-o") + 1]).write_bytes(b"video")
        return 0, "ok"


PLAN = {"phrases": ["هيا الـAI"], "keys": {"AI": "maroon"}, "beats": [{"type": "scene", "t": 0.4, "mode": "paper"}], "style": {}, "sfx": {"word_ticks": True}, "notes": "Paper scene on AI."}


def test_fast_edit_plans_once_builds_and_renders(tmp_path: Path, monkeypatch):
    project = make_project(tmp_path)
    engine = FakeEngine()
    prompts: list[str] = []

    async def fake_ask(system, prompt):
        prompts.append(prompt)
        assert "never change, add, drop or reorder words" in system.lower()
        return "Here you go:\n" + json.dumps(PLAN, ensure_ascii=False), 0.12

    monkeypatch.setattr(fast_edit, "_run", engine)
    monkeypatch.setattr(fast_edit, "_ask", fake_ask)
    events: list[dict] = []

    async def emit(event):
        events.append(event)

    result = asyncio.run(run_fast_edit(project, run_id="run12345", skill="wassim-style", request="make it punchy", emit=emit, quick=True))
    folder = project / "compositions" / "wassim-style-a1"
    assert result["usage"] == {"total_cost_usd": 0.12, "mode": "fast", "turns": 1}
    assert Path(result["output"]).name == "wassim-style-a1-run12345-v1.mp4"
    assert (folder / "edit" / "phrases.txt").read_text(encoding="utf-8") == "هيا الـAI\n"
    assert json.loads((folder / "edit" / "sfx.json").read_text(encoding="utf-8"))["duration"] == 4.0
    # The reviewed words are handed over with their timing, not rewritten.
    assert json.loads((folder / "edit" / "words.json").read_text(encoding="utf-8"))[1]["t"] == "الـAI"
    assert "1\t0.40-0.90\tالـAI" in prompts[0]
    assert [call for call in engine.calls if "--skip-cutout" in call], "quick mode skips the cut-out"
    assert [event["label"] for event in events if event.get("type") == "fast.step" and event["status"] == "done"][-1] == "Rendering the video"

    # A follow-up revises the existing plan instead of starting over.
    asyncio.run(run_fast_edit(project, run_id="run12345", skill="wassim-style", request="bigger captions", emit=emit, quick=True))
    assert "Current plan:" in prompts[1] and "bigger captions" in prompts[1]
    state = json.loads((project / ".agent-context" / "fast" / "run12345.json").read_text(encoding="utf-8"))
    assert state["turns"] == 2 and state["cost"] == pytest.approx(0.24)
    assert sum("init" in call for call in engine.calls) == 1, "setup is reused"


def test_build_errors_go_back_to_claude_for_a_repair(tmp_path: Path, monkeypatch):
    project = make_project(tmp_path)
    prompts: list[str] = []

    async def fake_ask(system, prompt):
        prompts.append(prompt)
        return json.dumps(PLAN, ensure_ascii=False), 0.05

    monkeypatch.setattr(fast_edit, "_run", FakeEngine(fail_builds=1))
    monkeypatch.setattr(fast_edit, "_ask", fake_ask)

    async def emit(event):
        return None

    result = asyncio.run(run_fast_edit(project, run_id="run2", skill="wassim-style", request="", emit=emit, quick=True))
    assert len(prompts) == 2 and "KeyError: 'mode'" in prompts[1]
    assert result["usage"]["total_cost_usd"] == pytest.approx(0.10)


def test_plan_parsing_and_placeholders(tmp_path: Path):
    from services.worker.project_bootstrap import SKILLS_ROOT

    manifest = FastManifest.load(SKILLS_ROOT / "library" / "devin-style")
    assert manifest is not None and "keys" in manifest.plan_files
    with pytest.raises(ValueError):
        _parse_plan('{"keys": {}}', manifest)
    folder = tmp_path / "reel"
    (folder / "edit").mkdir(parents=True)
    (folder / "edit" / "subject.json").write_text('{"head_y": 0.31}', encoding="utf-8")
    argv = _resolve(["python", "{skill}/scripts/studio_plate.py", "--head-y", "{subject.head_y}", "{clip}"], skill_dir=Path("/skills/devin"), clip=Path("/raw/c.mp4"), folder=folder)
    assert argv[0] == sys.executable and argv[3] == "0.31" and argv[1].replace("\\", "/").endswith("devin/scripts/studio_plate.py")
    assert skill_supports_fast(tmp_path, "talking-head-recut") and not skill_supports_fast(tmp_path, "hyperframes-core") and not skill_supports_fast(tmp_path, "nope")


def test_attached_resources_reach_the_plan_and_stay_for_follow_ups(tmp_path: Path, monkeypatch):
    project = make_project(tmp_path)
    logo = project / "proxies" / "r1"
    logo.mkdir(parents=True)
    (project / "raw" / "uuid-logo.png").write_bytes(b"png")
    # Newer than the clip, but a resource is never picked as the footage.
    (logo / "asset.json").write_text(json.dumps({"id": "r1", "role": "resource", "filename": "logo.png", "path": str(project / "raw" / "uuid-logo.png"), "probe": {"width": 512, "height": 512}}), encoding="utf-8")
    prompts: list[str] = []

    async def fake_ask(system, prompt):
        prompts.append(prompt)
        return json.dumps(PLAN, ensure_ascii=False), 0.01

    async def emit(event):
        return None

    monkeypatch.setattr(fast_edit, "_run", FakeEngine())
    monkeypatch.setattr(fast_edit, "_ask", fake_ask)
    asyncio.run(run_fast_edit(project, run_id="run3", skill="wassim-style", request="show my logo at the end", emit=emit, quick=True, resources=["r1"]))
    folder = project / "compositions" / "wassim-style-a1"
    assert (folder / "assets" / "resources" / "logo.png").read_bytes() == b"png"
    assert "`assets/resources/logo.png`: logo.png (image 512x512)" in prompts[0]
    asyncio.run(run_fast_edit(project, run_id="run3", skill="wassim-style", request="smaller logo", emit=emit, quick=True))
    assert "assets/resources/logo.png" in prompts[1]


def test_glass_engine_spec_has_the_plan_schema_not_the_code():
    from services.worker.project_bootstrap import SKILLS_ROOT

    manifest = FastManifest.load(SKILLS_ROOT / "library" / "talking-head-glass-edit")
    assert manifest is not None and set(manifest.plan_files) == {"plan", "sfx"}
    spec = manifest.spec()
    assert "edit/plan.json" in spec and '"type": "image"' in spec
    assert "def build_graphics" not in spec and "GRAPHICS_CSS" not in spec


def test_build_glass_turns_a_plan_into_compositions(tmp_path: Path):
    import subprocess

    from services.worker.project_bootstrap import SKILLS_ROOT

    (tmp_path / "edit").mkdir()
    words = [{"t": t, "s": i * 0.5, "e": i * 0.5 + 0.4} for i, t in enumerate(["قشابية", "الكشمير", "79", "DT", "Livraison"])]
    (tmp_path / "edit" / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "edit" / "footage.json").write_text(json.dumps({"duration": 3.0, "shot_cuts": [1.2]}), encoding="utf-8")
    plan = {
        "captions": [{"from": 0, "to": 1, "hidden": "intro"}, {"from": 2, "to": 4, "keys": [0]}],
        "cards": [
            {"type": "intro", "t": 0.0, "out": 0.9, "kicker": "KACHABITI", "title": "قشابية الكشمير"},
            {"type": "price", "t": 1.0, "out": 2.0, "label": "PRIX", "value": 79, "unit": "DT"},
            {"type": "image", "t": 1.5, "out": 2.5, "src": "assets/resources/logo.png", "caption": "<b>"},
        ],
        "kinetic": [{"t": 2.0, "out": 2.6, "icon": "truck", "lines": [{"style": "latin", "text": "livraison", "t": 2.0}]}],
        "zooms": [{"t": 0.5, "to": 1.05, "dur": 0.8}],
    }
    (tmp_path / "edit" / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    script = SKILLS_ROOT / "library" / "talking-head-glass-edit" / "scripts" / "build_glass.py"
    done = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    captions = json.loads((tmp_path / "edit" / "captions.json").read_text(encoding="utf-8"))
    assert captions["groups"][0]["hidden"] == "intro" and captions["groups"][1]["words"][0] == ["79", [2]]
    graphics = (tmp_path / "compositions" / "graphics.html").read_text(encoding="utf-8")
    assert 'count("#g1-n", 79.0' in graphics and 'src="assets/resources/logo.png"' in graphics and "&lt;b&gt;" in graphics
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "compositions/kinetic.html" in index and "push(1, 1.05, 0.5, 0.8, true)" in index and 'id="music"' not in index
    assert json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))[0] == {"text": "قشابية", "start": 0.0, "end": 0.4}


HTML = '<!doctype html><html><body><div id="root" data-composition-id="main" data-width="1080" data-height="1920" data-duration="4"></div></body></html>'


def test_styles_without_an_engine_use_the_generic_one(tmp_path: Path, monkeypatch):
    project = make_project(tmp_path)
    engine = FakeEngine()
    calls: list[tuple[str, str]] = []

    async def fake_ask(system, prompt):
        calls.append((system, prompt))
        return json.dumps({"composition": HTML, "notes": "done"}), 0.3

    async def emit(event):
        return None

    monkeypatch.setattr(fast_edit, "_run", engine)
    monkeypatch.setattr(fast_edit, "_ask", fake_ask)
    result = asyncio.run(run_fast_edit(project, run_id="gen1", skill="talking-head-recut", request="clean it up", emit=emit))
    folder = project / "compositions" / "talking-head-recut-a1"
    assert (folder / "index.html").read_text(encoding="utf-8") == HTML
    system, prompt = calls[0]
    assert '<doc path="@style/SKILL.md">' in system and "Generic fast engine" in system and '"composition": a string holding the whole file' in system
    assert "1\t0.40-0.90\tالـAI" in prompt
    joined = [" ".join(call) for call in engine.calls]
    assert any("fast_generic" in call and "prep.py" in call for call in joined) and any("check.py" in call for call in joined)
    assert result["usage"]["mode"] == "fast"

    # A hand edit made in Studio is what the next turn revises.
    (folder / "index.html").write_text(HTML.replace("main", "main").replace("<body>", "<body><!-- studio edit -->"), encoding="utf-8")
    asyncio.run(run_fast_edit(project, run_id="gen1", skill="talking-head-recut", request="faster", emit=emit))
    assert "studio edit" in calls[1][1]


def test_generic_engine_makes_videos_without_footage(tmp_path: Path, monkeypatch):
    project = tmp_path / "p2"
    project.mkdir()
    engine = FakeEngine()
    prompts: list[str] = []

    async def fake_ask(system, prompt):
        prompts.append(prompt)
        return json.dumps({"composition": HTML, "notes": "launch"}), 0.2

    async def emit(event):
        return None

    monkeypatch.setattr(fast_edit, "_run", engine)
    monkeypatch.setattr(fast_edit, "_ask", fake_ask)
    asyncio.run(run_fast_edit(project, run_id="launch99", skill="product-launch-motion", request="launch video for Notion AI", emit=emit))
    assert prompts[0].startswith("No footage")
    assert (project / "compositions" / "product-launch-motion-launch99" / "index.html").is_file()
    assert not any("prep.py" in " ".join(call) for call in engine.calls)
