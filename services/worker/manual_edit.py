"""Manual (no-AI) edits: cut, trim, sound fixes, captions and text, exported with FFmpeg.

An edit is one JSON document in ``<project>/edits/<id>/edit.json``. The studio
changes it directly; export turns it into a single FFmpeg command (one input
per clip, concat, an ASS file for captions and text, and an audio chain), so
basic editing never spends API credits.

Times are milliseconds on the edit's own timeline unless named ``in_ms`` /
``out_ms``, which are positions in the source clip.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

EDITS_DIR = "edits"
FONTS = ["Inter", "Inter Display", "Noto Sans", "Noto Sans Arabic", "DejaVu Sans"]
HEX = r"^#[0-9a-fA-F]{6}$"


def new_id(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:8]}"


class Clip(BaseModel):
    id: str = Field(default_factory=lambda: new_id("c"), max_length=40)
    asset_id: str = Field(max_length=64)
    in_ms: int = Field(ge=0)
    out_ms: int = Field(gt=0)
    volume: float = Field(default=1.0, ge=0, le=4)

    @model_validator(mode="after")
    def _ordered(self) -> "Clip":
        if self.out_ms - self.in_ms < 40:
            raise ValueError("a clip must be at least 40 ms long")
        return self

    @property
    def duration_ms(self) -> int:
        return self.out_ms - self.in_ms


class CaptionLine(BaseModel):
    id: str = Field(default_factory=lambda: new_id("l"), max_length=40)
    text: str = Field(max_length=300)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class CaptionStyle(BaseModel):
    enabled: bool = True
    font: str = "Inter Display"
    size: float = Field(default=5.0, ge=1, le=20, description="percent of the video height")
    color: str = Field(default="#FFFFFF", pattern=HEX)
    background: str | None = Field(default="#000000", pattern=HEX)
    background_opacity: float = Field(default=0.55, ge=0, le=1)
    bold: bool = True
    y: float = Field(default=0.78, ge=0.05, le=0.95, description="vertical centre, 0 = top")
    uppercase: bool = False


class TextLayer(BaseModel):
    id: str = Field(default_factory=lambda: new_id("t"), max_length=40)
    text: str = Field(max_length=500)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.2, ge=0, le=1)
    size: float = Field(default=7.0, ge=1, le=30)
    font: str = "Inter Display"
    color: str = Field(default="#FFFFFF", pattern=HEX)
    background: str | None = Field(default=None, pattern=HEX)
    bold: bool = True


class AudioSettings(BaseModel):
    volume: float = Field(default=1.0, ge=0, le=4)
    normalize: bool = False
    denoise: bool = False
    fade_in_ms: int = Field(default=0, ge=0, le=10_000)
    fade_out_ms: int = Field(default=0, ge=0, le=10_000)


class EditDoc(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12], pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(default="Untitled edit", max_length=120)
    width: int = Field(default=1080, ge=16, le=4096)
    height: int = Field(default=1920, ge=16, le=4096)
    fps: int = Field(default=30, ge=1, le=60)
    clips: list[Clip] = Field(default_factory=list, max_length=500)
    captions: list[CaptionLine] = Field(default_factory=list, max_length=2000)
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    texts: list[TextLayer] = Field(default_factory=list, max_length=200)
    audio: AudioSettings = Field(default_factory=AudioSettings)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("width", "height")
    @classmethod
    def _even(cls, value: int) -> int:
        # yuv420p needs even dimensions.
        return value - value % 2

    @property
    def duration_ms(self) -> int:
        return sum(clip.duration_ms for clip in self.clips)


# -- storage -------------------------------------------------------------------


def edit_dir(project: Path, edit_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", edit_id):
        raise ValueError("bad edit id")
    return project / EDITS_DIR / edit_id


def load_edit(project: Path, edit_id: str) -> EditDoc:
    return EditDoc.model_validate_json((edit_dir(project, edit_id) / "edit.json").read_text(encoding="utf-8"))


def save_edit(project: Path, doc: EditDoc) -> EditDoc:
    doc.updated_at = datetime.now(timezone.utc).isoformat()
    folder = edit_dir(project, doc.id)
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / "edit.json.tmp"
    temporary.write_text(doc.model_dump_json(indent=1), encoding="utf-8")
    temporary.replace(folder / "edit.json")
    return doc


def list_edits(project: Path) -> list[EditDoc]:
    docs = []
    for path in (project / EDITS_DIR).glob("*/edit.json"):
        try:
            docs.append(EditDoc.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(docs, key=lambda doc: doc.updated_at, reverse=True)


def new_edit(name: str, assets: list[dict[str, Any]]) -> EditDoc:
    """An edit holding each clip whole, in order, sized like the first clip."""

    clips = [Clip(asset_id=asset["id"], in_ms=0, out_ms=max(int((asset.get("probe") or {}).get("duration_ms") or 0), 40)) for asset in assets]
    probe = (assets[0].get("probe") or {}) if assets else {}
    width, height = int(probe.get("width") or 1080), int(probe.get("height") or 1920)
    if probe.get("rotation") in (90, -90, 270):
        width, height = height, width
    return EditDoc(name=name, width=width, height=height, fps=min(int(round(float(probe.get("fps") or 30))), 60) or 30, clips=clips)


# -- captions ------------------------------------------------------------------


def read_words(project: Path, asset_id: str) -> list[dict[str, Any]]:
    """The clip's reviewed transcript words: ``{text, start_ms, end_ms}``."""

    try:
        words = json.loads((project / "proxies" / asset_id / "transcript.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [word for word in words if isinstance(word, dict) and str(word.get("text", "")).strip()]


def captions_from_words(clips: list[Clip], words_by_asset: dict[str, list[dict[str, Any]]], *, max_words: int = 4, max_ms: int = 2200, gap_ms: int = 450) -> list[CaptionLine]:
    """Caption lines on the edit timeline from the words kept by the cuts.

    A word survives when its middle falls inside a clip; it moves with the
    clip. Lines break on a pause, on sentence punctuation, at a cut, or when
    they get too long, so they read like hand-made short-form captions.
    """

    lines: list[CaptionLine] = []
    offset = 0
    for clip in clips:
        current: list[tuple[str, int, int]] = []

        def flush() -> None:
            if current:
                lines.append(CaptionLine(text=" ".join(text for text, _, _ in current), start_ms=current[0][1], end_ms=max(current[-1][2], current[0][1] + 200)))
                current.clear()

        for word in words_by_asset.get(clip.asset_id, []):
            start, end = int(word["start_ms"]), int(word["end_ms"])
            if not clip.in_ms <= (start + end) / 2 < clip.out_ms:
                continue
            start = offset + max(start, clip.in_ms) - clip.in_ms
            end = offset + min(end, clip.out_ms) - clip.in_ms
            if current and (len(current) >= max_words or end - current[0][1] > max_ms or start - current[-1][2] > gap_ms):
                flush()
            current.append((str(word["text"]).strip(), start, end))
            if re.search(r"[.!?؟…]$", current[-1][0]):
                flush()
        flush()
        offset += clip.duration_ms
    return lines


# -- ASS subtitles (captions + text layers) -----------------------------------


def ass_color(hex_color: str, opacity: float = 1.0) -> str:
    red, green, blue = hex_color[1:3], hex_color[3:5], hex_color[5:7]
    alpha = round((1 - opacity) * 255)
    return f"&H{alpha:02X}{blue}{green}{red}".upper()


def ass_time(ms: int) -> str:
    centis = max(ms, 0) // 10
    return f"{centis // 360000}:{centis // 6000 % 60:02d}:{centis // 100 % 60:02d}.{centis % 100:02d}"


def ass_text(text: str) -> str:
    # Braces start override blocks; newlines are \N in ASS.
    return text.replace("\\", "⧵").replace("{", "(").replace("}", ")").replace("\r", "").replace("\n", "\\N")


def _style(name: str, font: str, size_px: int, color: str, background: str | None, opacity: float, bold: bool, alignment: int, margin_v: int) -> str:
    # BorderStyle 3 draws an opaque box behind the text; 1 is an outline.
    box = background is not None
    outline_color = ass_color(background, opacity) if box else "&H00000000"
    border, outline, shadow = (3, max(size_px // 5, 4), 0) if box else (1, max(size_px // 14, 2), max(size_px // 22, 1))
    return f"Style: {name},{font},{size_px},{ass_color(color)},{ass_color(color)},{outline_color},{outline_color},{-1 if bold else 0},0,0,0,100,100,0,0,{border},{outline},{shadow},{alignment},20,20,{margin_v},1"


def build_ass(doc: EditDoc) -> str | None:
    """Captions and text layers as one ASS script, or None when there are none."""

    style = doc.caption_style
    captions = [line for line in doc.captions if line.text.strip()] if style.enabled else []
    texts = [layer for layer in doc.texts if layer.text.strip()]
    if not captions and not texts:
        return None
    height = doc.height
    styles = [_style("Caption", style.font, round(style.size * height / 100), style.color, style.background, style.background_opacity, style.bold, 5, 0)]
    events = []
    cx, cy = doc.width // 2, round(style.y * height)
    for line in captions:
        text = line.text.upper() if style.uppercase else line.text
        events.append(f"Dialogue: 1,{ass_time(line.start_ms)},{ass_time(line.end_ms)},Caption,,0,0,0,,{{\\an5\\pos({cx},{cy})}}{ass_text(text)}")
    for index, layer in enumerate(texts):
        name = f"Text{index}"
        styles.append(_style(name, layer.font, round(layer.size * height / 100), layer.color, layer.background, 0.85, layer.bold, 5, 0))
        x, y = round(layer.x * doc.width), round(layer.y * height)
        events.append(f"Dialogue: 2,{ass_time(layer.start_ms)},{ass_time(layer.end_ms)},{name},,0,0,0,,{{\\an5\\pos({x},{y})}}{ass_text(layer.text)}")
    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {doc.width}", f"PlayResY: {height}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles, "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    return "\n".join(header + events) + "\n"


# -- FFmpeg --------------------------------------------------------------------


def export_command(doc: EditDoc, sources: dict[str, Path], has_audio: dict[str, bool], output: Path, *, subtitles: str | None) -> list[str]:
    """One FFmpeg argv for the whole edit.

    Each clip is its own input seeked with ``-ss``/``-t`` (fast and frame
    accurate when re-encoding), scaled and padded to the edit size, then all
    are concatenated. ``subtitles`` is an ASS file name relative to the
    command's working directory, which keeps Windows drive letters out of the
    filter string.
    """

    if not doc.clips:
        raise ValueError("The edit has no clips")
    argv = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for clip in doc.clips:
        argv += ["-ss", f"{clip.in_ms / 1000:.3f}", "-t", f"{clip.duration_ms / 1000:.3f}", "-i", str(sources[clip.asset_id])]
    width, height, fps = doc.width, doc.height, doc.fps
    parts: list[str] = []
    for index, clip in enumerate(doc.clips):
        parts.append(f"[{index}:v:0]setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p[v{index}]")
        if has_audio.get(clip.asset_id, True):
            parts.append(f"[{index}:a:0]asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={clip.volume:.3f},apad,atrim=duration={clip.duration_ms / 1000:.3f}[a{index}]")
        else:
            parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={clip.duration_ms / 1000:.3f},aformat=sample_fmts=fltp[a{index}]")
    joined = "".join(f"[v{index}][a{index}]" for index in range(len(doc.clips)))
    parts.append(f"{joined}concat=n={len(doc.clips)}:v=1:a=1[vcat][acat]")
    video = "vcat"
    if subtitles:
        parts.append(f"[vcat]ass={subtitles}[vout]")
        video = "vout"
    audio_chain = []
    settings = doc.audio
    if settings.denoise:
        audio_chain.append("afftdn=nf=-25")
    if settings.normalize:
        # Social platforms play around -14 LUFS.
        audio_chain.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    if settings.volume != 1:
        audio_chain.append(f"volume={settings.volume:.3f}")
    duration = doc.duration_ms / 1000
    if settings.fade_in_ms:
        audio_chain.append(f"afade=t=in:st=0:d={settings.fade_in_ms / 1000:.3f}")
    if settings.fade_out_ms:
        fade = min(settings.fade_out_ms / 1000, duration)
        audio_chain.append(f"afade=t=out:st={duration - fade:.3f}:d={fade:.3f}")
    audio_chain.append("aresample=48000")
    parts.append(f"[acat]{','.join(audio_chain)}[aout]")
    argv += [
        "-filter_complex", ";".join(parts), "-map", f"[{video}]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-shortest", str(output),
    ]
    return argv
