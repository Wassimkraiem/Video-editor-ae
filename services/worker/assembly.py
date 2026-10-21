"""Cut and join several talking-head clips into one before the style edits it.

The user picks the clips and their order. With ``cut`` on, one Claude call
reads every clip's timed words and keeps the takes worth keeping (false
starts, repeated takes and filler go), then pauses inside the kept takes are
tightened into jump cuts. The kept pieces are re-encoded to one size and
frame rate and joined into ``proxies/<asm-id>/assembled.mp4`` with a re-timed
transcript, so every style engine sees a single reviewed clip.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Awaitable, Callable

from .agent_tools import load_project_media
from .ingest import summarize_probe
from .media import ffprobe_command
from .transcription import write_transcript

Ask = Callable[[str, str], Awaitable[tuple[str, float]]]
Emit = Callable[[dict[str, Any]], Awaitable[None]]

PAD_IN, PAD_OUT = 0.12, 0.18  # breathing room around kept words
MAX_PAUSE = 0.6  # longer silences inside a take become jump cuts

CUT_SYSTEM = """You cut raw talking-head footage into one tight edit. You get the clips in the order the user put them, each with its timed words (index, seconds, word).

Return ONE JSON object and nothing else:
{"segments": [{"clip": <clip number>, "from": <first word index>, "to": <last word index>}], "notes": "<one sentence for the user>"}

Rules:
- Segments are inclusive word ranges, listed in final order. Keep the clips in the user's order and each clip's words in their order.
- Drop false starts, abandoned or repeated takes (keep the last complete one), stumbles, filler used as filler (euh, umm, ya3ni...) and off-topic chatter before or after the message.
- Keep every sentence that carries the message, and keep sentences whole.
- Never change words; you only choose ranges."""


def _words(project: Path, clip_id: str) -> list[dict[str, Any]]:
    path = project / "proxies" / clip_id / "words.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def _parse(answer: str) -> list[dict[str, int]]:
    start, end = answer.find("{"), answer.rfind("}")
    data = json.loads(answer[start : end + 1])
    return [{"clip": int(item["clip"]), "from": int(item["from"]), "to": int(item["to"])} for item in data.get("segments", [])]


def spans_from_ranges(ranges: list[dict[str, int]], words: list[list[dict[str, Any]]], durations: list[float]) -> list[tuple[int, float, float]]:
    """Word ranges -> (clip, start s, end s) pieces, with long pauses cut out."""

    spans: list[tuple[int, float, float]] = []
    for item in ranges:
        clip, first, last = item["clip"], item["from"], item["to"]
        if not 0 <= clip < len(words) or not 0 <= first <= last < len(words[clip]):
            raise ValueError(f"segment {item} is outside clip {clip}'s words")
        kept = words[clip][first : last + 1]
        start = max(0.0, kept[0]["s"] - PAD_IN)
        for previous, word in zip(kept, kept[1:]):
            if word["s"] - previous["e"] > MAX_PAUSE:
                spans.append((clip, start, previous["e"] + PAD_OUT))
                start = word["s"] - PAD_IN
        spans.append((clip, start, min(durations[clip], kept[-1]["e"] + PAD_OUT)))
    return spans


def _probe(path: Path) -> dict[str, Any]:
    done = subprocess.run(list(ffprobe_command(path).argv), capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


def _render(sources: list[Path], spans: list[tuple[int, float, float]], size: tuple[int, int], folder: Path) -> list[float]:
    """Encode every piece at one size/fps, then join them without re-encoding."""

    parts = folder / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    width, height = size
    scale = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30"
    lengths, listing = [], []
    for index, (clip, start, end) in enumerate(spans):
        length = round(end - start, 3)
        part = parts / f"{index:04d}.mp4"
        # Short audio fades keep the jump cuts from clicking.
        fade = f"afade=t=in:d=0.02,afade=t=out:st={max(0.0, length - 0.03):.3f}:d=0.03,aresample=48000"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(sources[clip]), "-t", f"{length:.3f}",
                        "-vf", scale, "-af", fade, "-ac", "2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                        "-g", "30", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(part)], check=True, capture_output=True)
        lengths.append(float(_probe(part)["format"]["duration"]))
        listing.append(f"file '{part.as_posix()}'")
    (folder / "parts.txt").write_text("\n".join(listing) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(folder / "parts.txt"), "-c", "copy",
                    "-movflags", "+faststart", str(folder / "assembled.mp4")], check=True, capture_output=True)
    return lengths


def retime(spans: list[tuple[int, float, float]], lengths: list[float], words: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The kept words on the joined clip's clock (studio transcript format)."""

    out, offset = [], 0.0
    for index, ((clip, start, end), length) in enumerate(zip(spans, lengths)):
        for word in words[clip]:
            if word["s"] >= start - 0.01 and word["e"] <= end + 0.01:
                s = offset + max(0.0, word["s"] - start)
                e = min(offset + length, offset + word["e"] - start)
                out.append({"id": f"a{len(out)}", "text": word["t"], "start_ms": round(s * 1000), "end_ms": round(max(s + 0.04, e) * 1000), "segment": index})
        offset += length
    return out


async def assemble(project: Path, clip_ids: list[str], *, cut: bool, ask: Ask, emit: Emit, run_id: str) -> tuple[str, float]:
    """Build (or reuse) the joined clip for this run; returns its asset id and the cost."""

    cache = project / ".agent-context" / "assembly" / f"{run_id}.json"
    if cache.is_file():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if (project / "proxies" / cached["asset_id"] / "asset.json").is_file():
            return cached["asset_id"], 0.0

    assets, _ = load_project_media(project)
    missing = [clip for clip in clip_ids if clip not in assets]
    if missing:
        raise FileNotFoundError(f"clips not found: {', '.join(missing)}")
    sources = [Path(str(assets[clip]["path"])) for clip in clip_ids]
    words = [_words(project, clip) for clip in clip_ids]
    durations = [float((assets[clip].get("probe") or {}).get("duration_ms") or 0) / 1000 for clip in clip_ids]

    cost, notes = 0.0, ""
    if cut and any(words):
        await emit({"type": "fast.step", "step": "cut", "label": f"Choosing the best takes across {len(clip_ids)} clip(s)", "status": "running"})
        listing = "\n\n".join(f"Clip {n} ({assets[clip].get('filename')}, {durations[n]:.1f}s):\n" + "\n".join(f"{i}\t{w['s']:.2f}-{w['e']:.2f}\t{w['t']}" for i, w in enumerate(words[n])) for n, clip in enumerate(clip_ids))
        answer, cost = await ask(CUT_SYSTEM, listing)
        data = json.loads(answer[answer.find("{") : answer.rfind("}") + 1])
        notes = str(data.get("notes", ""))
        chosen = spans_from_ranges(_parse(answer), words, durations)
        # The user's clip order wins; clips without speech (b-roll) stay whole.
        spans = [piece for n in range(len(clip_ids)) for piece in ([(n, 0.0, durations[n])] if not words[n] else [s for s in chosen if s[0] == n])]
        await emit({"type": "fast.step", "step": "cut", "label": "Takes chosen", "status": "done", "cost": cost, "detail": notes})
    else:
        spans = [(n, 0.0, durations[n]) for n in range(len(clip_ids))]
    if not spans:
        raise ValueError("the cut kept nothing")

    first = assets[clip_ids[0]].get("probe") or {}
    size = (int(first.get("width") or 1080) // 2 * 2, int(first.get("height") or 1920) // 2 * 2)
    asset_id = "asm-" + hashlib.sha1(json.dumps([clip_ids, spans, size]).encode()).hexdigest()[:12]
    folder = project / "proxies" / asset_id
    if not (folder / "asset.json").is_file():
        await emit({"type": "fast.step", "step": "assemble", "label": f"Cutting and joining {len(spans)} pieces", "status": "running"})
        lengths = await asyncio.to_thread(_render, sources, spans, size, folder)
        transcript = retime(spans, lengths, words)
        language = None
        meta_path = project / "proxies" / clip_ids[0] / "transcript.meta.json"
        if meta_path.is_file():
            language = json.loads(meta_path.read_text(encoding="utf-8")).get("language")
        # The sources were reviewed by the user; the joined words are theirs.
        write_transcript(folder, transcript, language=language, reviewed=True)
        probe = await asyncio.to_thread(_probe, folder / "assembled.mp4")
        manifest = {"id": asset_id, "role": "assembly", "filename": f"Assembled from {len(clip_ids)} clip(s)", "path": str(folder / "assembled.mp4"), "sources": clip_ids, "notes": notes, "probe": summarize_probe(probe)}
        (folder / "asset.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        await emit({"type": "fast.step", "step": "assemble", "label": "Clips joined", "status": "done"})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"asset_id": asset_id}), encoding="utf-8")
    return asset_id, cost
