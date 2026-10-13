"""Claude Agent SDK run orchestration and durable event mapping."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .mcp_tools import create_project_mcp_server
from .sandbox_policy import ProjectSandboxPolicy
from .agent_tools import ProjectToolService, load_project_media
from .quality_harness.harness import AgentHarness
from .quality_harness.sdk_runner import SDKRunConfig, make_claude_agent_options
from .project_bootstrap import bootstrap_project


EventSink = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass(frozen=True)
class AgentRunResult:
    status: str
    messages: list[dict[str, Any]]
    session_id: str | None
    usage: dict[str, Any]


DOMAIN_TOOLS = [
    "list_assets", "describe_asset", "get_timeline", "apply_timeline_ops",
    "get_transcript", "search_transcript", "auto_cut_silence", "remove_filler_words",
    "extract_frames", "render_preview", "render_final", "get_render_status",
    "generate_image", "generate_voiceover", "ask_user", "preview_composition",
]

# Tools listed here are auto-approved by the CLI and never reach
# ``can_use_tool``. Anything that writes files or runs commands (Bash, Write,
# Edit, NotebookEdit) is deliberately left out so the sandbox policy sees it.
AUTO_APPROVED_TOOLS = [
    "Read", "Glob", "Grep", "TodoWrite",
    *(f"mcp__video-editing__{name}" for name in DOMAIN_TOOLS),
]


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        # Keep the SDK class name (AssistantMessage, ToolUseBlock, ...) so
        # the studio can render each message and block by kind.
        return {"_type": type(value).__name__, **{item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


async def _emit(sink: EventSink | None, event: dict[str, Any]) -> None:
    if sink is None:
        return
    result = sink(event)
    if asyncio.iscoroutine(result):
        await result


def permission_callback(policy: ProjectSandboxPolicy):
    """Build a ``can_use_tool`` callback compatible with SDK versions.

    The SDK's ``PermissionResult`` type is imported only when the optional
    agent package is installed. Returning a small mapping keeps local tests
    and dry runs importable without the provider SDK.
    """

    async def can_use_tool(tool_name: str, tool_input: dict[str, Any], *_args: Any, **_kwargs: Any):
        allowed, message = policy.can_use_tool(tool_name, tool_input)
        try:
            from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

            return PermissionResultAllow() if allowed else PermissionResultDeny(message=message)
        except ImportError:
            return {"behavior": "allow"} if allowed else {"behavior": "deny", "message": message}

    return can_use_tool


async def _stream_prompt(prompt: str):
    """Send the prompt in streaming mode, which ``can_use_tool`` requires."""

    yield {"type": "user", "message": {"role": "user", "content": prompt}, "parent_tool_use_id": None}


class AgentSessionRunner:
    def __init__(self, project_dir: str | Path, *, config: SDKRunConfig | None = None):
        self.project_dir = Path(project_dir).resolve()
        self.config = config or SDKRunConfig()
        self.project_dir.mkdir(parents=True, exist_ok=True)

    async def run(
        self,
        prompt: str,
        *,
        assets: dict[str, dict[str, Any]] | None = None,
        transcripts: dict[str, list[dict[str, Any]]] | None = None,
        event_sink: EventSink | None = None,
        resume: str | None = None,
    ) -> AgentRunResult:
        try:
            from claude_agent_sdk import query
        except ImportError as exc:
            raise RuntimeError("claude-agent-sdk is required for agent runs; install the agent extra") from exc

        bootstrap_project(self.project_dir)
        if assets is None and transcripts is None:
            assets, transcripts = load_project_media(self.project_dir)
        service = ProjectToolService(self.project_dir, assets=assets, transcripts=transcripts)
        mcp_server = create_project_mcp_server(service)
        policy = ProjectSandboxPolicy(self.project_dir)
        harness = AgentHarness(self.project_dir)
        base = harness.sdk_options(can_use_tool=permission_callback(policy))
        base.update({
            "allowed_tools": list(AUTO_APPROVED_TOOLS),
            # Every skill copied into .claude/skills (wassim-style, the
            # hyperframes family, ...) is listed to the model.
            "skills": "all",
            "mcp_servers": {"video-editing": mcp_server},
        })
        if resume:
            base["resume"] = resume
        options = make_claude_agent_options(base, self.config, harness.hooks)
        messages: list[dict[str, Any]] = []
        events_path = self.project_dir / ".agent-context" / "events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        session_id: str | None = None
        usage: dict[str, Any] = {}

        async def consume() -> None:
            nonlocal session_id, usage
            async for message in query(prompt=_stream_prompt(prompt), options=options):
                payload = _jsonable(message)
                if not isinstance(payload, dict):
                    payload = {"value": payload}
                payload["received_at"] = datetime.now(timezone.utc).isoformat()
                messages.append(payload)
                with events_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                await _emit(event_sink, {"type": "agent.message", "message": payload})
                if getattr(message, "session_id", None):
                    session_id = str(message.session_id)
                if getattr(message, "usage", None):
                    usage = _jsonable(message.usage)
                if getattr(message, "total_cost_usd", None) is not None:
                    usage["total_cost_usd"] = float(message.total_cost_usd)

        try:
            async with asyncio.timeout(self.config.wall_clock_timeout_s):
                await consume()
        except TimeoutError:
            await _emit(event_sink, {"type": "agent.failed", "reason": "wall_clock_timeout"})
            return AgentRunResult("failed", messages, session_id, {**usage, "reason": "wall_clock_timeout"})
        # Only the final ResultMessage decides the outcome; a tool error the
        # agent recovered from must not fail the whole run.
        result = next((item for item in reversed(messages) if item.get("_type") == "ResultMessage"), None)
        status = "failed" if result is None or result.get("is_error") else "succeeded"
        await _emit(event_sink, {"type": f"agent.{status}", "session_id": session_id, "usage": usage})
        return AgentRunResult(status, messages, session_id, usage)
