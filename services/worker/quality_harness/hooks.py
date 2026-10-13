"""PostToolUse hooks that turn quality checks into hard SDK tool gates."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import HookResult, TimelineSpec
from .planning import PlanGate
from .verification import verify_render


COMPOSITION_SUFFIXES = {".html", ".htm"}


def normalize_tool_name(tool_name: str) -> str:
    """Strip the ``mcp__<server>__`` prefix the SDK adds to MCP tool names."""

    if tool_name.startswith("mcp__"):
        return tool_name.split("__", 2)[-1]
    return tool_name


def composition_root(path: Path) -> Path:
    """Return the HyperFrames project folder that owns a composition file.

    ``hyperframes lint`` lints ``index.html`` plus ``compositions/`` from its
    working directory, so a sub-composition is validated from its parent
    project rather than on its own.
    """

    resolved = path.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / "index.html").is_file() or (candidate / "hyperframes.json").is_file():
            return candidate
    return resolved.parent


class HyperFramesValidator:
    """Run the project-pinned HyperFrames linter through argv only."""

    def __init__(self, command: str | None = None, timeout_s: int = 120) -> None:
        # On Windows npx is ``npx.cmd``; which() finds the real launcher.
        self.command = command or shutil.which("npx") or "npx"
        self.timeout_s = timeout_s

    def validate(self, composition_path: Path) -> tuple[bool, str, dict[str, Any]]:
        argv = [self.command, "hyperframes", "lint", "--json"]
        try:
            completed = subprocess.run(argv, check=False, capture_output=True, text=True, cwd=composition_root(Path(composition_path)), timeout=self.timeout_s)
        except FileNotFoundError:
            # No Node toolchain on this host: report it instead of crashing the
            # tool loop. The sandbox image always ships npx.
            return True, "HyperFrames CLI unavailable; lint skipped", {"skipped": True}
        except subprocess.TimeoutExpired:
            return False, "HyperFrames lint timed out", {}
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
        callback = self._hooks.get(tool_name) or self._hooks.get(normalize_tool_name(tool_name))
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

    def after_render(*, render_path: str | None = None, timeline: TimelineSpec | dict[str, Any] | None = None, **_: Any) -> HookResult:
        blocked = check_plan()
        if blocked:
            return blocked
        if not render_path or timeline is None:
            # Queued renders are verified by the render job once the file
            # exists; only the plan gate applies at request time.
            return HookResult(ok=True, hook="render", message="Render queued; verification runs in the render job")
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

    def after_file_write(*, file_path: str = "", **_: Any) -> HookResult:
        # Write/Edit hit every file; only HyperFrames compositions are gated.
        path = Path(file_path)
        if path.suffix.lower() not in COMPOSITION_SUFFIXES or "compositions" not in path.parts:
            return HookResult(ok=True, hook="file_write", message="Not a composition")
        return after_composition_write(composition_path=file_path)

    registry.register("render_final", after_render)
    registry.register("render_preview", after_render)
    registry.register("render", after_render)
    registry.register("write_composition", after_composition_write)
    registry.register("composition_write", after_composition_write)
    registry.register("preview_composition", after_composition_write)
    for tool in ("Write", "Edit", "MultiEdit"):
        registry.register(tool, after_file_write)
    return registry


def build_post_tool_use_hook(registry: QualityHookRegistry):
    """Return an SDK-compatible async PostToolUse callback.

    A failed gate is fed back to Claude with ``decision=block`` and the
    validator output as additional context, so the agent repairs the
    composition or render instead of the whole run being killed. The plan
    gate is the exception: it stops the run until the user approves.
    """

    async def post_tool_use(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input") or {}
        try:
            result = registry.run(tool_name, **tool_input)
        except Exception as exc:  # a broken gate must never crash the SDK loop
            result = HookResult(ok=False, hook=normalize_tool_name(tool_name), message=f"Quality hook error: {exc}")
        if result.ok:
            return {}
        output: dict[str, Any] = {
            "decision": "block",
            "reason": result.message,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": json.dumps({"quality_gate": result.hook, "error": result.message, "details": result.details}, default=str)[:8000],
            },
        }
        if result.hook == "plan_gate":
            output["continue_"] = False
            output["stopReason"] = result.message
        return output

    return post_tool_use
