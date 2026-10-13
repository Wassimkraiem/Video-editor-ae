from pathlib import Path

from worker.quality_harness.models import TimelineSpec
from worker.quality_harness.verification import parse_probe, verify_render


class FakeProbe:
    def __init__(self, payload):
        self.payload = payload

    def probe(self, media_path: Path):
        return self.payload


def payload(duration="5.000"):
    return {
        "format": {"duration": duration, "tags": {"integrated_lufs": "-14.2"}},
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"}],
    }


def test_probe_parses_duration_fps_and_loudness():
    parsed = parse_probe(payload())
    assert parsed.duration_ms == 5000
    assert parsed.fps == 30
    assert parsed.loudness_lufs == -14.2


def test_render_verification_blocks_mismatch(tmp_path: Path):
    report = verify_render(
        tmp_path / "render.mp4",
        TimelineSpec(duration_ms=5000, width=1920, height=1080, fps=30),
        FakeProbe(payload(duration="6.000")),
    )
    assert not report.ok
    assert {issue.field for issue in report.issues} == {"duration_ms"}


def test_render_verification_accepts_expected_output(tmp_path: Path):
    report = verify_render(
        tmp_path / "render.mp4",
        TimelineSpec(duration_ms=5000, width=1920, height=1080, fps=30),
        FakeProbe(payload()),
    )
    assert report.ok
