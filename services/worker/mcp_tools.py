"""In-process MCP server exposed to the Claude Agent SDK."""

from __future__ import annotations

import json
from typing import Any

from .agent_tools import ProjectToolService


def create_project_mcp_server(service: ProjectToolService):
    """Create the SDK server; imports are lazy so API-only installs stay small."""

    from claude_agent_sdk import create_sdk_mcp_server, tool

    @tool("list_assets", "List project assets", {})
    async def list_assets(_: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.list_assets())}]}

    @tool("describe_asset", "Describe an asset before editing", {"asset_id": str})
    async def describe_asset(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.describe_asset(args["asset_id"]))}]}

    @tool("get_timeline", "Read the current timeline", {})
    async def get_timeline(_: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": service.get_timeline().model_dump_json()}]}

    @tool("apply_timeline_ops", "Apply validated timeline operations", {"ops": list})
    async def apply_ops(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.apply_timeline_ops(args["ops"]))}]}

    @tool("get_transcript", "Read word-level transcript timestamps", {"asset_id": str, "start_ms": int, "end_ms": int})
    async def get_transcript(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.get_transcript(args["asset_id"], args.get("start_ms"), args.get("end_ms")))}]}

    @tool("search_transcript", "Find transcript matches and their timestamps", {"query": str})
    async def search_transcript(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.search_transcript(args["query"]))}]}

    @tool("auto_cut_silence", "Find silence ranges for a source asset", {"asset_id": str, "threshold_db": float, "min_silence_ms": int, "padding_ms": int})
    async def auto_cut_silence(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.auto_cut_silence(args["asset_id"], args["threshold_db"], args["min_silence_ms"], args["padding_ms"]))}]}

    @tool("remove_filler_words", "Find filler words to remove from a transcript", {"asset_id": str, "fillers": list})
    async def remove_filler_words(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.remove_filler_words(args["asset_id"], args["fillers"]))}]}

    @tool("extract_frames", "Extract frames for visual inspection", {"asset_id": str, "timestamps": list})
    async def extract_frames(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.extract_frames(args["asset_id"], args["timestamps"]))}]}

    @tool("render_preview", "Queue a verified preview render", {})
    async def render_preview(_: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.render_preview())}]}

    @tool("render_final", "Queue a verified final render", {"preset": str})
    async def render_final(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.render_final(args["preset"]))}]}

    @tool("get_render_status", "Read render progress", {"render_id": str})
    async def get_render_status(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.get_render_status(args["render_id"]))}]}

    @tool("generate_image", "Generate and cache an image asset", {"prompt": str, "size": str, "transparent_background": bool})
    async def generate_image(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.generate_image(args["prompt"], args["size"], args.get("transparent_background", False)))}]}

    @tool("generate_voiceover", "Queue optional voiceover generation", {"script": str, "voice_id": str})
    async def generate_voiceover(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.generate_voiceover(args["script"], args["voice_id"]))}]}

    @tool("ask_user", "Pause the run for a user decision", {"question": str, "options": list})
    async def ask_user(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.ask_user(args["question"], args["options"]))}]}

    @tool("preview_composition", "Queue a HyperFrames composition preview", {"composition_path": str})
    async def preview_composition(args: dict[str, Any]) -> dict[str, Any]:
        return {"content": [{"type": "text", "text": json.dumps(service.preview_composition(args["composition_path"]))}]}

    return create_sdk_mcp_server(
        name="video-editing",
        version="1.0.0",
        tools=[
            list_assets, describe_asset, get_timeline, apply_ops, get_transcript,
            search_transcript, auto_cut_silence, remove_filler_words, extract_frames,
            render_preview, render_final, get_render_status, generate_image,
            generate_voiceover, ask_user, preview_composition,
        ],
    )
