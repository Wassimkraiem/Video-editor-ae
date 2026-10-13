from pathlib import Path
import asyncio

from worker.quality_harness.harness import AgentHarness
from worker.quality_harness.hooks import QualityHookRegistry, build_post_tool_use_hook
from worker.quality_harness.models import HookResult
from worker.quality_harness.sdk_runner import SDKRunConfig, build_sdk_options


def test_harness_pins_project_memory_and_plan_files(tmp_path: Path):
    options = AgentHarness(tmp_path).sdk_options()
    assert options["setting_sources"] == ["project"]
    assert "CLAUDE.md" in options["context_files"][0]
    assert "storyboard.json" in options["context_files"][1]
    assert "never fabricate" in options["system_prompt"]


def test_sdk_adapter_removes_harness_only_metadata():
    options = build_sdk_options(
        {"cwd": "/tmp/project", "setting_sources": ["project"], "context_files": ["x"], "compaction": {"enabled": True}},
        SDKRunConfig(),
        post_tool_use=lambda *_args: {},
    )
    assert options["setting_sources"] == ["project"]
    assert "context_files" not in options
    assert "compaction" not in options
    assert "wall_clock_timeout_s" not in options


def test_post_tool_use_returns_failed_updated_output():
    registry = QualityHookRegistry()
    registry.register("render_final", lambda **_: HookResult(ok=False, hook="render", message="duration mismatch"))
    callback = build_post_tool_use_hook(registry)
    result = asyncio.run(callback({"tool_name": "render_final", "tool_input": {}}, "tool-1", {}))
    assert result["continue_"] is False
    assert result["hookSpecificOutput"]["updatedToolOutput"]["is_error"] is True
