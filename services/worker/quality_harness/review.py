"""Blind final review using the Claude Agent SDK."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from .models import ReviewInput, ReviewResult


class Reviewer(Protocol):
    def review(self, review_input: ReviewInput) -> tuple[bool, list[str]]: ...


class SDKReviewer:
    """Adapter that gives the reviewer only the approved review payload."""

    def __init__(self, query: Callable[..., Any], model: str = "claude-opus-5-5") -> None:
        self.query = query
        self.model = model

    def review(self, review_input: ReviewInput) -> tuple[bool, list[str]]:
        payload = review_input.model_dump(mode="json")
        prompt = (
            "You are a blind video quality reviewer. Review only the JSON below. "
            "Return JSON with keys passed (boolean) and issues (array of strings). "
            "Do not invent media facts.\n<review-payload>\n"
            + json.dumps(payload, ensure_ascii=False)
            + "\n</review-payload>"
        )
        # The reviewer is a dedicated Agent SDK subagent with no project
        # settings, filesystem tools, or editing context. Its only input is
        # the bounded review payload above.
        try:
            from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

            options = ClaudeAgentOptions(
                model=self.model,
                setting_sources=[],
                allowed_tools=["Agent"],
                agents={
                    "quality-reviewer": AgentDefinition(
                        description="Blindly reviews a rendered video against its brief",
                        prompt="Review only the payload supplied by the parent. Return JSON with passed and issues. Never read files or call editing tools.",
                        tools=[],
                        model=self.model,
                        maxTurns=4,
                    )
                },
            )
            result = self.query(prompt="Use the quality-reviewer subagent to review this payload:\n" + prompt, options=options)
        except ImportError:
            # Keeps the pure unit-test adapter usable when the optional SDK is
            # not installed; production workers always install it.
            result = self.query(prompt=prompt, model=self.model)
        if hasattr(result, "text"):
            result = result.text
        parsed = json.loads(str(result))
        return bool(parsed.get("passed", False)), [str(item) for item in parsed.get("issues", [])]


async def run_blind_sdk_review(review_input: ReviewInput, *, model: str = "claude-opus-5-5") -> tuple[bool, list[str]]:
    """Spawn a reviewer subagent with only the bounded review payload."""

    from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query

    payload = json.dumps(review_input.model_dump(mode="json"), ensure_ascii=False)
    prompt = "Review only this JSON payload. Return JSON with keys passed (boolean) and issues (array of strings).\n" + payload
    options = ClaudeAgentOptions(
        model=model,
        setting_sources=[],
        allowed_tools=["Agent"],
        agents={"quality-reviewer": AgentDefinition(description="Blind video quality reviewer", prompt="Review only the payload supplied by the parent. Never read files or call editing tools.", tools=[], model=model, maxTurns=4)},
    )
    responses: list[Any] = []
    async for message in query(prompt="Use the quality-reviewer subagent to review the following payload:\n" + prompt, options=options):
        responses.append(message)
    for message in reversed(responses):
        candidate = getattr(message, "result", None) or getattr(message, "text", None)
        if candidate:
            try:
                parsed = json.loads(str(candidate))
                return bool(parsed.get("passed", False)), [str(item) for item in parsed.get("issues", [])]
            except json.JSONDecodeError:
                continue
    return False, ["Reviewer returned no structured result"]


def review_with_retries(
    review_input: ReviewInput,
    reviewer: Reviewer,
    fix_after_failure: Callable[[list[str]], ReviewInput],
    *,
    max_cycles: int = 2,
) -> list[ReviewResult]:
    """Run a blind review and send failures back to the editing agent."""

    if not review_input.verification_report.ok:
        raise ValueError("Blind review can start only after render verification passes")
    if max_cycles < 1 or max_cycles > 2:
        raise ValueError("Review cycles must be between 1 and 2")
    results: list[ReviewResult] = []
    current = review_input
    for cycle in range(1, max_cycles + 1):
        passed, issues = reviewer.review(current)
        result = ReviewResult(passed=passed, issues=issues, cycle=cycle)
        results.append(result)
        if passed:
            return results
        if cycle < max_cycles:
            current = fix_after_failure(issues)
    return results
