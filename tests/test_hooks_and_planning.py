from pathlib import Path

from worker.quality_harness.hooks import QualityHookRegistry, register_quality_hooks
from worker.quality_harness.models import StoryScene, Storyboard, TimelineSpec
from worker.quality_harness.planning import PlanGate, request_storyboard_approval, requires_plan, write_storyboard


class FakeValidator:
    def __init__(self, ok=True):
        self.ok = ok

    def validate(self, composition_path: Path):
        return self.ok, "ok" if self.ok else "lint error", {}


def test_composition_hook_blocks_validation_errors():
    registry = register_quality_hooks(QualityHookRegistry(), validator=FakeValidator(False))
    result = registry.run("write_composition", composition_path="composition.html")
    assert not result.ok
    assert "blocked" in result.message


def test_composition_and_render_are_blocked_until_storyboard_approval():
    gate = PlanGate(required=True)
    registry = register_quality_hooks(QualityHookRegistry(), validator=FakeValidator(True), plan_gate=gate)
    result = registry.run("write_composition", composition_path="composition.html")
    assert not result.ok
    gate.approve()
    # The validator is reached after approval; no real HyperFrames binary is needed.
    assert registry.run("write_composition", composition_path="composition.html").ok


def test_write_tool_only_gates_composition_html(tmp_path: Path):
    registry = register_quality_hooks(QualityHookRegistry(), validator=FakeValidator(False))
    assert registry.run("Write", file_path=str(tmp_path / "notes.md"), content="x").ok
    assert registry.run("Write", file_path=str(tmp_path / "timeline.html"), content="x").ok
    assert not registry.run("Write", file_path=str(tmp_path / "compositions" / "reel" / "index.html"), content="x").ok


def test_queued_render_tools_pass_without_a_render_file():
    registry = register_quality_hooks(QualityHookRegistry(), validator=FakeValidator(True))
    assert registry.run("mcp__video-editing__render_preview").ok


def test_plan_is_required_for_motion_and_multiple_scenes():
    assert requires_plan(scene_count=2)
    assert requires_plan(brief="new motion graphics title")
    assert not requires_plan(scene_count=1, brief="trim one clip")


def test_storyboard_is_written_and_approval_is_explicit(tmp_path: Path):
    storyboard = Storyboard(
        project_id="p1",
        brief="motion",
        scenes=[StoryScene(id="s1", title="Intro", start_ms=0, end_ms=1000)],
    )
    assert write_storyboard(tmp_path, storyboard).is_file()
    approved = request_storyboard_approval(storyboard, lambda question, options: "Approve")
    assert approved.status == "approved"
