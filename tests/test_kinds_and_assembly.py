import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.api.main import app, project_dir, repo
from services.worker.alignment import align_script
from services.worker.assembly import retime, spans_from_ranges
from services.worker.edit_brief import compose_request
from services.worker.transcription import write_transcript

HEARD = [
    {"text": "إيجا", "start_ms": 0, "end_ms": 160},
    {"text": "نفسرلك", "start_ms": 160, "end_ms": 660},
    {"text": "كيفاش", "start_ms": 660, "end_ms": 980},
    {"text": "إكسبير", "start_ms": 980, "end_ms": 1500},
    {"text": "في", "start_ms": 1500, "end_ms": 1700},
    {"text": "الخدمة", "start_ms": 1700, "end_ms": 2200},
]


def test_script_takes_whisper_timing_and_fills_unmatched_words():
    words = align_script("ايجا نفسرلك كيفاش\nexpert في الخدمة بتاعك", HEARD)
    assert [w["text"] for w in words] == ["ايجا", "نفسرلك", "كيفاش", "expert", "في", "الخدمة", "بتاعك"]
    # Fuzzy matches keep Whisper's times; "expert" sits on the word it replaces.
    assert (words[0]["start_ms"], words[2]["end_ms"]) == (0, 980)
    assert (words[3]["start_ms"], words[3]["end_ms"]) == (980, 1500)
    # Line breaks become segments; times never go backwards.
    assert [w["segment"] for w in words] == [0, 0, 0, 1, 1, 1, 1]
    assert all(a["end_ms"] <= b["start_ms"] for a, b in zip(words, words[1:]))
    assert words[-1]["end_ms"] >= words[-1]["start_ms"] + 40


def test_cut_ranges_become_jump_cuts_and_words_are_retimed():
    clip0 = [{"t": "a", "s": 1.0, "e": 1.3}, {"t": "b", "s": 1.4, "e": 1.7}, {"t": "c", "s": 3.0, "e": 3.4}]
    clip1 = [{"t": "d", "s": 0.5, "e": 0.9}]
    spans = spans_from_ranges([{"clip": 0, "from": 0, "to": 2}, {"clip": 1, "from": 0, "to": 0}], [clip0, clip1], [5.0, 2.0])
    # The 1.3 s pause between "b" and "c" is cut out.
    assert [(c, round(s, 2), round(e, 2)) for c, s, e in spans] == [(0, 0.88, 1.88), (0, 2.88, 3.58), (1, 0.38, 1.08)]
    words = retime(spans, [1.0, 0.7, 0.7], [clip0, clip1])
    assert [(w["text"], w["start_ms"]) for w in words] == [("a", 120), ("b", 520), ("c", 1120), ("d", 1820)]


def test_requests_carry_kind_intensity_and_script():
    text = compose_request("Launch our app", kind="product", intensity="minimal", script="Meet Flow.\nInvoices in one tap.")
    assert text.startswith("The user's ideas for this edit:\nLaunch our app") and "product launch" in text and "MINIMAL" in text and "exact words on screen" in text and "Invoices in one tap." in text
    assert compose_request("Edit it") == "The user's ideas for this edit:\nEdit it"


def test_brand_kit_overrides_the_style_palette_and_fonts():
    text = compose_request("Promo", brand={"colors": ["#FF5A1F", "#111827"], "fonts": ["Montserrat", "Inter"], "notes": "No emojis"})
    assert "Brand kit (these override the style's own colours and fonts)" in text
    assert "#FF5A1F, #111827" in text and "first = main/accent" in text and "Montserrat, Inter" in text and "No emojis" in text
    assert "Brand kit" not in compose_request("Promo", brand={"colors": [], "fonts": [], "notes": ""})


def login(client: TestClient) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": "kinds@example.com", "password": "correct horse battery"})
    token = client.post("/api/v1/auth/login", json={"email": "kinds@example.com", "password": "correct horse battery"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_runs_take_kind_clips_and_scripts_and_scripts_align():
    with TestClient(app) as client:
        headers = login(client)
        project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Kinds"}).json()["id"]
        clips = [client.post(f"/api/v1/projects/{project_id}/assets", headers=headers, files={"file": (f"take{n}.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")}).json()["id"] for n in range(2)]
        logo = client.post(f"/api/v1/projects/{project_id}/assets", headers=headers, files={"file": ("logo.png", b"\x89PNG\r\n\x1a\n", "image/png")}, data={"role": "resource"}).json()["id"]
        repo.jobs.clear()

        run = client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Ad", "skill": "wassim-style", "kind": "people", "intensity": "minimal", "clips": [clips[1], clips[0], logo], "cut": True}).json()
        payload = repo.jobs[-1]["payload"]
        assert payload["clips"] == [clips[1], clips[0]], "user order kept, resources are not clips"
        assert payload["cut"] is True and payload["intensity"] == "minimal" and payload["asset_id"] == clips[1] and run["mode"] == "fast"

        client.post(f"/api/v1/projects/{project_id}/runs", headers=headers, json={"brief": "Launch", "skill": "product-launch-motion", "kind": "product", "clips": clips, "script": "Meet Flow."})
        payload = repo.jobs[-1]["payload"]
        assert payload["kind"] == "product" and payload["clips"] == [] and payload["asset_id"] is None and payload["script"] == "Meet Flow."

        assert client.post(f"/api/v1/assets/{clips[0]}/transcript/align", headers=headers, json={"text": "hello"}).status_code == 409
        write_transcript(project_dir(project_id) / "proxies" / clips[0], [dict(word, id=f"w{i}", segment=0) for i, word in enumerate(HEARD)], language="tn", reviewed=False)
        aligned = client.post(f"/api/v1/assets/{clips[0]}/transcript/align", headers=headers, json={"text": "ايجا نفسرلك كيفاش expert في الخدمة"})
        assert aligned.status_code == 200, aligned.text
        assert aligned.json()["reviewed"] is False and aligned.json()["words"][3]["text"] == "expert"
        # Aligning only proposes: the saved transcript is unchanged until approved.
        saved = json.loads((Path(project_dir(project_id)) / "proxies" / clips[0] / "transcript.json").read_text(encoding="utf-8"))
        assert saved[3]["text"] == "إكسبير"
