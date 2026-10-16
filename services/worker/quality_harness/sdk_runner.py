"""Thin Claude Agent SDK bridge.

This module intentionally does not implement an agent loop. `query()` and
`ClaudeSDKClient` remain the SDK's responsibility; this adapter only supplies
project settings, budgets, and the PostToolUse gate callback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
import asyncio
import os
from typing import Any

from .hooks import QualityHookRegistry, build_post_tool_use_hook


def _env_number(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class SDKRunConfig:
    model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "claude-opus-5-5"))
    max_turns: int = field(default_factory=lambda: int(_env_number("AGENT_MAX_TURNS", 80)))
    max_budget_usd: float = field(default_factory=lambda: _env_number("AGENT_MAX_BUDGET_USD", 10.0))
    wall_clock_timeout_s: int = field(default_factory=lambda: int(_env_number("AGENT_TIMEOUT_S", 1800)))


def build_sdk_options(
    base_options: dict[str, object],
    config: SDKRunConfig,
    *,
    post_tool_use: Callable[..., Any],
) -> dict[str, object]:
    """Build options accepted by the Claude Agent SDK.

    `setting_sources` is supplied by `load_project_settings`; the SDK loads
    CLAUDE.md and project skills. PostToolUse is an SDK hook, so a failed
    quality result is returned to the SDK as a failed tool result.
    """

    options = dict(base_options)
    options.pop("context_files", None)
    # `compaction` here is a harness metadata marker, not a made-up
    # ClaudeAgentOptions field. Python Agent SDK's CLI owns auto-compaction;
    # the file-backed context keeps the plan and memory reloadable.
    options.pop("compaction", None)
    # Claude Agent SDK delegates context management to the Claude Code
    # runtime. Keep automatic compaction enabled and make its trigger explicit
    # through the supported runtime environment variable rather than building
    # a second summarizer in application code.
    sdk_env = dict(options.get("env") or {})
    sdk_env.setdefault("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "80")
    # Speech models are preinstalled (scripts/fetch_models.py); a run must
    # never stall on a multi-GB download, so a missing model fails fast.
    sdk_env.setdefault("WHISPER_OFFLINE", "1")
    sdk_env.setdefault("HF_HUB_OFFLINE", "1")
    # Keep the cached prompt prefix (system prompt, skills, style docs) for an
    # hour instead of five minutes, so edits of other videos in the same style
    # read it at a tenth of the input price.
    if os.getenv("PROMPT_CACHE_1H", "1") != "0":
        sdk_env.setdefault("ENABLE_PROMPT_CACHING_1H", "1")
    sdk_env.pop("DISABLE_AUTO_COMPACT", None)
    sdk_env.pop("DISABLE_COMPACT", None)
    options["env"] = sdk_env
    # The CLI sends each message as one JSON line; a tool result holding an
    # image (a frame or snapshot the agent inspects) easily passes the SDK's
    # 1 MB default and kills the run with "JSON message exceeded maximum
    # buffer size".
    options.setdefault("max_buffer_size", 64 * 1024 * 1024)
    options.update(
        {
            "model": config.model,
            "max_turns": config.max_turns,
            "max_budget_usd": config.max_budget_usd,
            "hooks": {"PostToolUse": [post_tool_use]},
        }
    )
    return options


def make_claude_agent_options(
    base_options: dict[str, object],
    config: SDKRunConfig,
    registry: QualityHookRegistry,
):
    """Construct the real `ClaudeAgentOptions` when the SDK is installed."""

    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

    options = build_sdk_options(base_options, config, post_tool_use=build_post_tool_use_hook(registry))
    # No matcher: MCP tools arrive as ``mcp__video-editing__render_final`` and
    # compositions are written with Write/Edit, so the registry filters by
    # normalized tool name instead of a brittle matcher string.
    options["hooks"] = {"PostToolUse": [HookMatcher(matcher=None, hooks=[options["hooks"]["PostToolUse"][0]], timeout=180)]}
    return ClaudeAgentOptions(**options)


def post_tool_use_gate(registry: QualityHookRegistry, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Translate a quality hook result into the SDK hook result contract."""

    result = registry.run(tool_name, **tool_input)
    return {
        "continue_": result.ok,
        "decision": "approve" if result.ok else "block",
        "reason": result.message,
        "hook": result.hook,
        "details": result.details,
    }


async def query_once(query: Callable[..., AsyncIterator[Any]], prompt: str, options: dict[str, object], *, timeout_s: int | None = None) -> list[Any]:
    """Consume one SDK `query()` run while preserving streamed messages."""

    messages: list[Any] = []
    async def consume() -> None:
        async for message in query(prompt=prompt, options=options):
            messages.append(message)
    if timeout_s is None:
        await consume()
    else:
        async with asyncio.timeout(timeout_s):
            await consume()
    return messages


async def run_project_query(
    prompt: str,
    base_options: dict[str, object],
    config: SDKRunConfig,
    registry: QualityHookRegistry,
) -> list[Any]:
    """Run a one-shot project edit through the SDK's `query()` function."""

    from claude_agent_sdk import query

    options = make_claude_agent_options(base_options, config, registry)
    return await query_once(query, prompt, options, timeout_s=config.wall_clock_timeout_s)


async def run_project_chat(
    prompts: list[str],
    base_options: dict[str, object],
    config: SDKRunConfig,
    registry: QualityHookRegistry,
) -> list[Any]:
    """Continue a user-facing run with the SDK's `ClaudeSDKClient` session."""

    from claude_agent_sdk import ClaudeSDKClient

    options = make_claude_agent_options(base_options, config, registry)
    messages: list[Any] = []
    async with ClaudeSDKClient(options=options) as client:
        for prompt in prompts:
            await client.query(prompt)
            async for message in client.receive_response():
                messages.append(message)
    return messages
