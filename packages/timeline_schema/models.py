"""Pydantic timeline schema and validated mutation operations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Transform(BaseModel):
    x: float = 0
    y: float = 0
    scale: float = Field(default=1, gt=0)
    rotation: float = 0
    opacity: float = Field(default=1, ge=0, le=1)


class TimelineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    type: Literal["clip", "audio", "text", "image", "hyperframes", "transition"]
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    in_ms: int = Field(default=0, ge=0)
    out_ms: int | None = Field(default=None, ge=0)
    src_asset_id: str | None = None
    composition_path: str | None = None
    text: str | None = None
    transform: Transform = Field(default_factory=Transform)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    transitions_in: dict[str, Any] | None = None
    transitions_out: dict[str, Any] | None = None
    props: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_range(self) -> "TimelineItem":
        if self.end_ms <= self.start_ms:
            raise ValueError("Timeline item end_ms must be after start_ms")
        if self.type == "hyperframes" and not self.composition_path:
            raise ValueError("HyperFrames items require composition_path")
        if self.type in {"clip", "audio", "image"} and not self.src_asset_id:
            raise ValueError(f"{self.type} items require src_asset_id")
        return self


class TimelineTrack(BaseModel):
    id: str
    type: Literal["video", "audio", "text", "graphics", "image"]
    items: list[TimelineItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_order(self) -> "TimelineTrack":
        previous = -1
        seen: set[str] = set()
        for item in self.items:
            if item.id in seen:
                raise ValueError(f"Duplicate timeline item id: {item.id}")
            if item.start_ms < previous:
                raise ValueError("Track items must be ordered by start_ms")
            seen.add(item.id)
            previous = item.start_ms
        return self


class CaptionWord(BaseModel):
    id: str
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    transcript_word_id: str | None = None


class Timeline(BaseModel):
    schema_version: str = "1.0"
    fps: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    background: str = "#000000"
    tracks: list[TimelineTrack] = Field(default_factory=list)
    markers: list[dict[str, Any]] = Field(default_factory=list)
    captions: list[CaptionWord] = Field(default_factory=list)


class TimelineOp(BaseModel):
    op: Literal[
        "add_item",
        "update_item",
        "delete_item",
        "split_item",
        "move_item",
        "add_track",
        "set_caption_style",
        "set_background",
    ]
    track_id: str | None = None
    item_id: str | None = None
    item: TimelineItem | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
    at_ms: int | None = Field(default=None, ge=0)
    track: TimelineTrack | None = None
    value: Any = None


class TimelineVersion(BaseModel):
    version: int = Field(gt=0)
    parent_version: int | None = None
    schema_version: str
    data: Timeline
    diff: list[dict[str, Any]] = Field(default_factory=list)


def _find_track(timeline: Timeline, track_id: str) -> TimelineTrack:
    for track in timeline.tracks:
        if track.id == track_id:
            return track
    raise ValueError(f"Unknown track: {track_id}")


def apply_timeline_ops(timeline: Timeline, ops: list[TimelineOp]) -> tuple[Timeline, list[dict[str, Any]]]:
    """Apply a validated operation list and return a new timeline plus diff."""

    result = Timeline.model_validate(deepcopy(timeline.model_dump(mode="json")))
    diff: list[dict[str, Any]] = []
    for operation in ops:
        if operation.op == "add_track":
            if operation.track is None:
                raise ValueError("add_track requires track")
            if any(track.id == operation.track.id for track in result.tracks):
                raise ValueError(f"Track already exists: {operation.track.id}")
            result.tracks.append(operation.track)
            diff.append({"op": operation.op, "track_id": operation.track.id})
            continue
        if operation.op == "set_background":
            result.background = str(operation.value)
            diff.append({"op": operation.op, "value": result.background})
            continue
        if operation.op == "set_caption_style":
            result.markers.append({"type": "caption_style", "props": operation.value or {}})
            diff.append({"op": operation.op})
            continue
        if not operation.track_id:
            raise ValueError(f"{operation.op} requires track_id")
        track = _find_track(result, operation.track_id)
        if operation.op == "add_item":
            if operation.item is None:
                raise ValueError("add_item requires item")
            if any(item.id == operation.item.id for item in track.items):
                raise ValueError(f"Item already exists: {operation.item.id}")
            track.items.append(operation.item)
        elif operation.op == "delete_item":
            track.items = [item for item in track.items if item.id != operation.item_id]
        elif operation.op in {"update_item", "move_item"}:
            target = next((item for item in track.items if item.id == operation.item_id), None)
            if target is None:
                raise ValueError(f"Unknown item: {operation.item_id}")
            patch = dict(operation.patch)
            if operation.op == "move_item":
                patch["start_ms"] = operation.at_ms
                if operation.at_ms is None:
                    raise ValueError("move_item requires at_ms")
                duration = target.end_ms - target.start_ms
                patch["end_ms"] = operation.at_ms + duration
            updated = target.model_copy(update=patch)
            track.items[track.items.index(target)] = TimelineItem.model_validate(updated.model_dump(mode="json"))
            track.items.sort(key=lambda item: item.start_ms)
        elif operation.op == "split_item":
            if operation.at_ms is None:
                raise ValueError("split_item requires at_ms")
            target = next((item for item in track.items if item.id == operation.item_id), None)
            if target is None or not target.start_ms < operation.at_ms < target.end_ms:
                raise ValueError("split_item point must be inside an item")
            index = track.items.index(target)
            first = target.model_copy(update={"end_ms": operation.at_ms})
            second = target.model_copy(update={"id": f"{target.id}-split", "start_ms": operation.at_ms})
            track.items[index:index + 1] = [first, second]
        else:
            raise ValueError(f"Unsupported timeline operation: {operation.op}")
        diff.append(operation.model_dump(mode="json", exclude_none=True))
    result.tracks = [TimelineTrack.model_validate(track.model_dump(mode="json")) for track in result.tracks]
    return result, diff
