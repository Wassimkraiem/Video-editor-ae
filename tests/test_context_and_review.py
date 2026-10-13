from pathlib import Path
import pytest

from worker.quality_harness.context_store import ProjectContextStore
from worker.quality_harness.models import RenderProbe, ReviewInput, TimelineSpec, VerificationReport
from worker.quality_harness.review import review_with_retries


def test_context_is_read_in_time_slices(tmp_path: Path):
    store = ProjectContextStore(tmp_path)
    store.write_transcript("a", [{"start_ms": 0, "end_ms": 100, "text": "one"}, {"start_ms": 200, "end_ms": 300, "text": "two"}])
    assert [w["text"] for w in store.read_transcript_slice("a", 150, 350)] == ["two"]
    options = store.sdk_context_options()
    assert options["compaction"] == {"enabled": True, "preserve_files": ["CLAUDE.md", "storyboard.json"]}


class FakeReviewer:
    def __init__(self):
        self.calls = 0

    def review(self, review_input):
        self.calls += 1
        return (self.calls == 2), ([] if self.calls == 2 else ["title is too small"])


def test_blind_review_caps_cycles_and_sends_failures_back():
    report = VerificationReport(
        ok=True,
        render_path="render.mp4",
        expected=TimelineSpec(duration_ms=1000, width=1920, height=1080, fps=30),
        observed=RenderProbe(duration_ms=1000, width=1920, height=1080, fps=30, loudness_lufs=-14),
    )
    review_input = ReviewInput(original_brief="brief", timeline={}, frame_extracts=["frame-1.png"], verification_report=report)
    reviewer = FakeReviewer()
    seen = []
    results = review_with_retries(review_input, reviewer, lambda issues: (seen.append(issues) or review_input), max_cycles=2)
    assert results[-1].passed
    assert len(results) == 2
    assert seen == [["title is too small"]]


def test_blind_review_requires_passed_render_verification():
    report = VerificationReport(
        ok=False,
        render_path="render.mp4",
        expected=TimelineSpec(duration_ms=1000, width=1920, height=1080, fps=30),
        observed=RenderProbe(),
    )
    review_input = ReviewInput(original_brief="brief", timeline={}, verification_report=report)
    with pytest.raises(ValueError):
        review_with_retries(review_input, FakeReviewer(), lambda _: review_input)
