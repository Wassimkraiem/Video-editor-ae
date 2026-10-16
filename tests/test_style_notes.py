from pathlib import Path

from services.worker import style_notes


def test_notes_learned_in_one_project_reach_the_next(tmp_path: Path):
    first, second = tmp_path / "p1", tmp_path / "p2"
    first.mkdir()
    second.mkdir()
    assert "first edit in `wassim-style`" in style_notes.prepare(first, "wassim-style")
    assert not style_notes.publish(first, "wassim-style"), "nothing written yet"
    (first / ".agent-context" / "style-notes" / "wassim-style.md").write_text("run prep_cutout.py first", encoding="utf-8")
    assert style_notes.publish(first, "wassim-style")
    section = style_notes.prepare(second, "wassim-style")
    assert ".agent-context/style-notes/wassim-style.md" in section and "read them first" in section
    assert (second / ".agent-context" / "style-notes" / "wassim-style.md").read_text(encoding="utf-8") == "run prep_cutout.py first"
    assert style_notes.prepare(second, None) == "" and not style_notes.publish(second, "devin-style")
