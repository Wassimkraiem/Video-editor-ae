"""Orchestration adapter around Claude Agent SDK query/ClaudeSDKClient."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context_store import ProjectContextStore
from .agent_prompt import AGENT_SYSTEM_PROMPT
from .hooks import QualityHookRegistry, register_quality_hooks
from .models import Storyboard
from .project_memory import create_project_memory, load_project_settings
from .planning import PlanGate, request_storyboard_approval, write_storyboard


@dataclass
class HarnessRunResult:
    status: str
    sdk_options: dict[str, object]
    hook_registry: QualityHookRegistry


class AgentHarness:
    """Configure a project-scoped SDK run without replacing its tool loop."""

    def __init__(self, project_dir: str | Path, *, hook_registry: QualityHookRegistry | None = None, plan_gate: PlanGate | None = None) -> None:
        self.project_dir = Path(project_dir).resolve()
        create_project_memory(self.project_dir)
        self.context = ProjectContextStore(self.project_dir)
        self.plan_gate = plan_gate
        self.hooks = hook_registry or register_quality_hooks(QualityHookRegistry(), plan_gate=plan_gate)

    def sdk_options(self, *, can_use_tool: Callable[..., Any] | None = None) -> dict[str, object]:
        options = load_project_settings(self.project_dir)
        options.update(self.context.sdk_context_options())
        # Append to the Claude Code preset so the agent keeps the built-in
        # tool guidance (Skill, Bash, Edit) that skills rely on.
        options["system_prompt"] = {"type": "preset", "preset": "claude_code", "append": AGENT_SYSTEM_PROMPT}
        if can_use_tool is not None:
            options["can_use_tool"] = can_use_tool
        return options

    def start(self, *, can_use_tool: Callable[..., Any] | None = None) -> HarnessRunResult:
        # The actual query()/ClaudeSDKClient invocation belongs to the worker's
        # session runner. This method returns the exact project-scoped options
        # that runner supplies to the Claude Agent SDK.
        return HarnessRunResult(status="ready", sdk_options=self.sdk_options(can_use_tool=can_use_tool), hook_registry=self.hooks)

    def prepare_storyboard(self, storyboard: Storyboard, ask_user: Callable[[str, list[str]], str]) -> Storyboard:
        """Persist and approve a plan before any composition/render call."""

        write_storyboard(self.project_dir, storyboard)
        decided = request_storyboard_approval(storyboard, ask_user)
        write_storyboard(self.project_dir, decided)
        if decided.status == "approved" and self.plan_gate is not None:
            self.plan_gate.approve()
        return decided
