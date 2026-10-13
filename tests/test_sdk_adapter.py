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
    assert options["system_prompt"]["preset"] == "claude_code"
    assert "never fabricate" in options["system_prompt"]["append"]


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


def test_post_tool_use_feeds_failures_back_to_the_agent():
    registry = QualityHookRegistry()
    registry.register("render_final", lambda **_: HookResult(ok=False, hook="render", message="duration mismatch"))
    callback = build_post_tool_use_hook(registry)
    # The SDK reports MCP tools with their server prefix.
    result = asyncio.run(callback({"tool_name": "mcp__video-editing__render_final", "tool_input": {}}, "tool-1", {}))
    assert result["decision"] == "block"
    assert "duration mismatch" in result["hookSpecificOutput"]["additionalContext"]
    assert "continue_" not in result


def test_post_tool_use_stops_the_run_on_plan_gate():
    registry = QualityHookRegistry()
    registry.register("Write", lambda **_: HookResult(ok=False, hook="plan_gate", message="approve first"))
    result = asyncio.run(build_post_tool_use_hook(registry)({"tool_name": "Write", "tool_input": {}}, None, {}))
    assert result["continue_"] is False


def test_post_tool_use_survives_a_crashing_hook():
    registry = QualityHookRegistry()
    registry.register("render_preview", lambda **_: 1 / 0)
    result = asyncio.run(build_post_tool_use_hook(registry)({"tool_name": "render_preview", "tool_input": {}}, None, {}))
    assert result["decision"] == "block"


def test_runtime_builds_real_sdk_options_with_sandbox_and_skills(tmp_path: Path):
    import pytest

    sdk = pytest.importorskip("claude_agent_sdk")
    from worker.agent_runtime import AUTO_APPROVED_TOOLS, permission_callback
    from worker.quality_harness.sdk_runner import make_claude_agent_options
    from worker.sandbox_policy import ProjectSandboxPolicy

    harness = AgentHarness(tmp_path)
    base = harness.sdk_options(can_use_tool=permission_callback(ProjectSandboxPolicy(tmp_path)))
    base.update({"allowed_tools": list(AUTO_APPROVED_TOOLS), "skills": "all"})
    options = make_claude_agent_options(base, SDKRunConfig(), harness.hooks)
    assert isinstance(options, sdk.ClaudeAgentOptions)
    assert options.skills == "all"
    # Writing tools must reach can_use_tool, so they are never auto-approved.
    assert not {"Bash", "Write", "Edit"} & set(options.allowed_tools)
    assert options.hooks["PostToolUse"][0].matcher is None


def test_permission_callback_denies_escapes(tmp_path: Path):
    from worker.agent_runtime import permission_callback
    from worker.sandbox_policy import ProjectSandboxPolicy

    check = permission_callback(ProjectSandboxPolicy(tmp_path))
    denied = asyncio.run(check("Write", {"file_path": str(tmp_path.parent / "escape.txt"), "content": "x"}))
    allowed = asyncio.run(check("Write", {"file_path": "compositions/reel/index.html", "content": "x"}))
    raw = asyncio.run(check("Edit", {"file_path": "raw/clip.mp4"}))
    assert getattr(denied, "behavior", None) == "deny" and getattr(raw, "behavior", None) == "deny"
    assert getattr(allowed, "behavior", None) == "allow"
