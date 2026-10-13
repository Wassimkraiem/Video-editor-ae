import pytest

from packages.timeline_schema import Timeline, TimelineItem, TimelineOp, TimelineTrack, apply_timeline_ops


def test_timeline_ops_create_split_and_move_items():
    timeline = Timeline(fps=30, width=1920, height=1080, duration_ms=5000, tracks=[TimelineTrack(id="v1", type="video")])
    clip = TimelineItem(id="clip-1", type="clip", src_asset_id="asset-1", start_ms=0, end_ms=4000)
    updated, diff = apply_timeline_ops(timeline, [TimelineOp(op="add_item", track_id="v1", item=clip)])
    assert updated.tracks[0].items[0].id == "clip-1"
    updated, _ = apply_timeline_ops(updated, [TimelineOp(op="split_item", track_id="v1", item_id="clip-1", at_ms=2000)])
    assert [item.id for item in updated.tracks[0].items] == ["clip-1", "clip-1-split"]
    updated, _ = apply_timeline_ops(updated, [TimelineOp(op="move_item", track_id="v1", item_id="clip-1-split", at_ms=2500)])
    assert updated.tracks[0].items[1].start_ms == 2500
    assert diff


def test_hyperframes_requires_composition_path():
    with pytest.raises(ValueError):
        TimelineItem(id="g1", type="hyperframes", start_ms=0, end_ms=1000)
