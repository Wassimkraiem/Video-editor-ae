"""PostToolUse hooks that turn quality checks into hard SDK tool gates."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import HookResult, TimelineSpec
from .planning import PlanGate
from .verification import verify_render


class HyperFramesValidator:
    """Run the project-pinned HyperFrames validator through argv only."""

    def __init__(self, command: str = "npx") -> None:
        self.command = command

    def validate(self, composition_path: Path) -> tuple[bool, str, dict[str, Any]]:
        argv = [self.command, "hyperframes", "validate", str(composition_path.resolve()), "--json"]
        completed = subprocess.run(argv, check=False, capture_output=True, text=True)
        output = completed.stdout.strip() or completed.stderr.strip()
        details: dict[str, Any] = {}
        if output:
            try:
                details = json.loads(output)
            except json.JSONDecodeError:
                details = {"output": output}
        return completed.returncode == 0, output, details


class QualityHookRegistry:
    """Registry called by the SDK adapter after tool execution."""

    def __init__(self) -> None:
        self._hooks: dict[str, Callable[..., HookResult]] = {}

    def register(self, tool_name: str, callback: Callable[..., HookResult]) -> None:
        self._hooks[tool_name] = callback

    def run(self, tool_name: str, **payload: Any) -> HookResult:
        callback = self._hooks.get(tool_name)
        if callback is None:
            return HookResult(ok=True, hook=tool_name, message="No quality hook registered")
        return callback(**payload)


def register_quality_hooks(
    registry: QualityHookRegistry,
    *,
    validator: HyperFramesValidator | None = None,
    plan_gate: PlanGate | None = None,
) -> QualityHookRegistry:
    """Register the two required PostToolUse gates.

    The SDK adapter must call `registry.run(tool_name, ...)` from its
    PostToolUse callback and propagate `ok=False` as a failed tool result.
    """

    hyperframes = validator or HyperFramesValidator()

    def check_plan() -> HookResult | None:
        if plan_gate is None:
            return None
        ok, message = plan_gate.check()
        if not ok:
            return HookResult(ok=False, hook="plan_gate", message=message)
        return None

    def after_render(*, render_path: str, timeline: TimelineSpec, **_: Any) -> HookResult:
        blocked = check_plan()
        if blocked:
            return blocked
        if not isinstance(timeline, TimelineSpec):
            timeline = TimelineSpec.model_validate(timeline)
        report = verify_render(render_path, timeline)
        return HookResult(
            ok=report.ok,
            hook="render",
            message="Render passed ffprobe verification" if report.ok else "Render failed ffprobe verification",
            details={"report": report.model_dump(mode="json")},
        )

    def after_composition_write(*, composition_path: str, **_: Any) -> HookResult:
        blocked = check_plan()
        if blocked:
            return blocked
        ok, output, details = hyperframes.validate(Path(composition_path))
        return HookResult(
            ok=ok,
            hook="composition_write",
            message="Composition passed HyperFrames validation" if ok else "Composition blocked by HyperFrames validation",
            details={"output": output, "validation": details},
        )

    registry.register("render_final", after_render)
    registry.register("render_preview", after_render)
    registry.register("render", after_render)
    registry.register("write_composition", after_composition_write)
    registry.register("composition_write", after_composition_write)
    return registry


def build_post_tool_use_hook(registry: QualityHookRegistry):
    """Return an SDK-compatible async PostToolUse callback.

    The callback uses `updatedToolOutput` so a mismatch is returned to Claude
    as a failed quality result, while `continue_` and `decision=block` stop the
    run from reporting success.
    """

    async def post_tool_use(input_data: dict[str, Any], tool_use_id: str | None, context: dict[str, Any]) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input") or {}
        result = registry.run(tool_name, **tool_input)
        if result.ok:
            return {}
        return {
            "continue_": False,
            "decision": "block",
            "reason": result.message,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": {
                    "is_error": True,
                    "error": result.message,
                    "details": result.details,
                },
            },
        }

    return post_tool_use
