import json
from pathlib import Path

from services.api.composition_timeline import composition_timeline


def write_reel(root: Path) -> None:
    reel = root / "compositions" / "reel"
    (reel / "edit").mkdir(parents=True)
    (reel / "index.html").write_text(
        '<div id="root" data-composition-id="main" data-start="0" data-duration="10" data-width="1080" data-height="1920">'
        '<video id="bg-video" data-start="0" data-duration="10" data-track-index="0"></video>'
        '<div id="kinetic-host" class="clip" data-composition-id="kinetic" data-start="2" data-duration="3" data-track-index="2"></div>'
        '<div id="captions-host" data-track-kind="captions" class="clip" data-start="0" data-duration="10" data-track-index="1"></div>'
        '<audio id="sfx" data-start="0" data-duration="10" data-track-index="3"></audio></div>',
        encoding="utf-8",
    )
    words = [{"text": "hello", "start": 0.5, "end": 0.9}, {"text": "world", "start": 0.9, "end": 1.4}, {"text": "again", "start": 2.0, "end": 2.6}]
    (reel / "transcript.json").write_text(json.dumps(words), encoding="utf-8")
    (reel / "edit" / "captions.json").write_text(json.dumps({"groups": [{"words": [["hello", [0]], ["world", [1]]]}, {"words": [["again", [2]]]}]}), encoding="utf-8")
    (reel / "edit" / "sfx.json").write_text(json.dumps({"cues": [["pop", 0.5, 0.2], ["whoosh", 2.0, 0.1]]}), encoding="utf-8")


def test_style_edits_show_up_as_timeline_tracks(tmp_path: Path):
    write_reel(tmp_path)
    timeline = composition_timeline(tmp_path)
    data = timeline["data"]
    assert timeline["source"] == "compositions/reel"
    assert (data["duration_ms"], data["width"], data["height"]) == (10_000, 1080, 1920)
    tracks = {track["type"]: track["items"] for track in data["tracks"]}
    assert tracks["video"][0]["end_ms"] == 10_000
    assert tracks["graphics"][0] == {"id": "kinetic-host", "type": "graphics", "start_ms": 2000, "end_ms": 5000, "label": "kinetic"}
    # Caption groups come from word timestamps, replacing the full-length host clip.
    assert [(item["start_ms"], item["end_ms"], item["label"]) for item in tracks["caption"]] == [(500, 1400, "hello world"), (2000, 2600, "again")]
    assert [item["label"] for item in tracks["sfx"]] == ["pop", "whoosh"]
    assert "audio" not in tracks


def test_no_composition_means_no_composition_timeline(tmp_path: Path):
    assert composition_timeline(tmp_path) is None
