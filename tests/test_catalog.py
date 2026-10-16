import json
import os
import time
from pathlib import Path

from services.worker.catalog import composition_for, read_catalog, record_render, record_turn, snapshot


def reel(project: Path, name: str) -> Path:
    folder = project / "compositions" / name
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<div></div>", encoding="utf-8")
    (folder / "assets" / "source.mp4").write_bytes(b"footage")
    return folder


def test_agent_turn_links_new_videos_to_their_reel_and_style(tmp_path: Path):
    reel(tmp_path, "old")
    before = snapshot(tmp_path)
    time.sleep(0.05)
    new = reel(tmp_path, "glass")
    (tmp_path / "renders").mkdir()
    (tmp_path / "renders" / "glass.mp4").write_bytes(b"video")
    assert record_turn(tmp_path, before, run_id="r1", skill="talking-head-glass-edit", title="Premium reel") == ["renders/glass.mp4"]
    entry = read_catalog(tmp_path)["renders/glass.mp4"]
    assert entry["composition"] == "compositions/glass" and entry["skill"] == "talking-head-glass-edit" and entry["title"] == "Premium reel"
    meta = json.loads((new / ".studio-meta.json").read_text(encoding="utf-8"))
    assert meta["skill"] == "talking-head-glass-edit"

    # A later render of the same reel (Render button) inherits its style.
    later = tmp_path / "renders" / "v2.mp4"
    later.write_bytes(b"video")
    record_render(tmp_path, later, new, "render-2")
    assert read_catalog(tmp_path)["renders/v2.mp4"]["skill"] == "talking-head-glass-edit"


def test_older_videos_are_matched_to_the_reel_edited_before_them(tmp_path: Path):
    first = reel(tmp_path, "first")
    os.utime(first / "index.html", (1000, 1000))
    second = reel(tmp_path, "second")
    os.utime(second / "index.html", (3000, 3000))
    (tmp_path / "renders").mkdir()
    video = tmp_path / "renders" / "a.mp4"
    video.write_bytes(b"x")
    os.utime(video, (2000, 2000))
    assert composition_for(tmp_path, video) == first
    inside = second / "renders" / "b.mp4"
    inside.parent.mkdir()
    inside.write_bytes(b"x")
    assert composition_for(tmp_path, inside) == second
