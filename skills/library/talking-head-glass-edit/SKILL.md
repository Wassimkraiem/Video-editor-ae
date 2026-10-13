---
name: talking-head-glass-edit
description: Edit a vertical talking-head / product video (people speaking to camera, e.g. a clothing or brand ad, often in Tunisian Darija / Arabic / French) into a premium social reel — footage untouched, small word-synced captions only in the gaps, Apple-style liquid-glass pop-up cards, big animated keyword cards, kinetic word-by-word text with self-drawing icons over the footage, slow smooth punch-in zooms, soft sound effects, price/order cards and a logo end card — built and rendered with HyperFrames. Use this whenever the user hands over a talking-head, UGC, testimonial or product-showcase clip (mp4/mov) and asks for captions, motion graphics, "animations", "effects", "glass", "kinetic text", zooms with sound, or "edit it like the last one / like Kachabiti", even if they don't name the skill. Not for videos built from scratch with no footage (use product-launch-video / faceless-explainer) or plain subtitles only (embedded-captions).
---

# Talking-head glass edit

Turns a finished talking-head clip into a premium reel without touching the footage: the
people and the product stay visible the whole time; everything you add is a light layer on top,
synced to the exact moment each word is spoken.

This style was developed with a real client through many feedback rounds. Their rules are the
heart of the skill — read `references/design-system.md` before designing anything; it has the
exact glass CSS, sizes, placement, motion and sound levels, each with the reason behind it.
A complete working build lives in `references/example/` — copy from it rather than inventing.

**The client's non-negotiables (why the style looks the way it does):**
1. **The product must stay visible.** No full-screen panels or backgrounds over the footage;
   cards are compact frosted glass; kinetic text floats with only a soft shadow.
2. **Never write the same words twice.** While an animation shows a phrase, its caption is
   hidden. Captions only fill the gaps between animations.
3. **Everything synced to the voice.** Cards, keyword words and captions start on the real
   spoken onset — never in the silence before it, never just before a shot cut.
4. **Smooth, never shaky.** No bouncy/overshoot eases, slow small GPU zooms, verified on the render.
5. **Faces stay clear.** Middle band is home; move things below faces when people stand low.
6. **Sound on every animation, but soft** — always under the voices.
7. **Only claim what's said.** Flag anything derived (totals, savings, "100%").

## Tools this relies on
HyperFrames CLI (`npx hyperframes …`), ffmpeg, Python with numpy/scipy/Pillow,
`pip install faster-whisper soundfile` for transcription, the SFX library at
`~/.claude/skills/media-use/audio/assets/sfx`. Load `/hyperframes-core` before writing
composition HTML if you haven't this session — sub-composition rules (styles/scripts inside
`<template>`, matching ids, one paused timeline) matter.

## Workflow

### 1. Intake (ask once, briefly)
Ask only what you can't see: brand name + logo file (and what the wall/packaging logo says),
caption language/script (default: Arabic script for Darija), prices/offers to show, and any
claims they want emphasised. Don't interrogate — the footage and transcript answer the rest.

### 2. Project + footage prep
```bash
npx hyperframes init "videos/<brand>-<product>" --non-interactive --example=blank --skill=talking-head-recut
cd videos/<brand>-<product>
python <skill>/scripts/prep_footage.py "<input.mp4>" --logo "<logo.png>"
```
Gives `assets/source.mp4` (dense keyframes), shot cuts, `edit/contact.jpg` (2 fps sheet — study
where faces, garments and empty wall sit per shot) and white/ink logo PNGs. Copy fonts
(design-system §10).

### 3. Transcribe → user confirms the wording
```bash
python <skill>/scripts/transcribe.py assets/source.mp4 --lang ar --prompt "<brand, product, key words>"
```
Show the user the segment lines, cleaned into natural spelling (Darija: keep French words in
Latin — *haut de gamme*, *en famille*, *pack de trois*). Ask them to correct it. Their wording
is the display text; Whisper only supplies the timing.

### 4. Plan the edit (one table, then build)
Walk the transcript line by line and assign each phrase exactly one treatment:

| treatment | for |
|---|---|
| intro title card | the product name, first seconds |
| chip(s) | short benefit words |
| hero chip | the premium/quality claim |
| big keyword card | the 2–3 strongest claims (durability, quality, fabric…) |
| kinetic text beats | a run of lifestyle phrases (who / where / when you wear it) |
| price cards | spoken prices, offers, packs |
| order checklist + delivery card | how to order |
| logo end card (top) | sign-off |
| **caption** | everything else — the connective lines |
| **zoom + whoosh** | 3–4 emotional/important lines (also captioned or carded) |

Post the plan to the user as a short table (time · words · treatment) and proceed unless
they object. Write it down as `edit/captions.json` (groups + `hidden` for animated ones + `keys`)
and `edit/sfx.json` cues.

### 5. Build
* `index.html` — copy `references/example/index.html`; set duration, video src, zoom pushes,
  hosts for graphics / kinetic (only its window) / captions, `<audio id="sfx">`.
* `compositions/graphics.html` — copy the example; keep its glass CSS, icon symbols and
  helpers (`popIn`, `out`, `kw()` keyword cards, price count-ups); replace content and times.
  Card in-time = the phrase's snapped onset (± 0.05), out-time = just before the next caption.
* `compositions/kinetic.html` — copy the example; one `.k-beat` per phrase, words fire on
  their onsets; position it on garments below faces.
* Captions + sound:
  ```bash
  python <skill>/scripts/build_captions.py   # prints each visible phrase with onset times
  python <skill>/scripts/build_sfx.py
  python <skill>/scripts/publish_audio.py   # content-hashed audio names → no stale audio in Studio
  ```
Card/keyword times should use the *snapped* onsets that `build_captions.py` prints for the
neighbouring phrases — use the same onset logic (or read the times it prints) so cards and
captions hand off cleanly.

### 6. Check, look, fix
```bash
npx hyperframes lint && npx hyperframes check
npx hyperframes snapshot --at <every card's hold time, every caption, the kinetic beats, end>
```
Read the contact sheets yourself: faces covered? text over a busy spot? caption and card on
screen together? a card visible before its words? Fix, re-snapshot. Contrast warnings on a
single caption word over a bright floor are acceptable; layout overlaps are not.

### 7. Preview → render → verify
`npx hyperframes preview --background`, open it, ask *render now or what changes?*
Render: `npx hyperframes render -q delivery -o renders/<name>.mp4`. Then
`python <skill>/scripts/verify_zoom.py renders/<name>.mp4 assets/source.mp4 <zoom windows>`
and report the result — if the user says zooms "shake", check the render this way before
changing anything; the live preview can stutter by itself.

## Feedback the client gave (apply up front, don't wait for it)
* "Captions show before the scene/speaker" → onset snapping + shot-cut rule.
* "Zooms shake" → slower (1.5–2.4 s), smaller (1.06–1.07), sine, force3D; no two-step punches.
* "Remove the shakes" → no `back.out`/elastic anywhere, no icon wobble.
* "Pop-ups in the middle, in the eye line"; "logo should be up".
* "Make important keywords bigger with animation" → big keyword cards.
* "Don't caption what's animated"; "captions in the middle".
* "Liquid glass backgrounds"; then "remove the background, users must see the product" →
  glass only on compact cards, kinetic text bare with shadow, smaller (≈86/54/98 px, 64 px icons).
* "Add sound effects for captions and pop-ups, not loud."
* "Music and sound effects stop before the end" → Studio cached the old (shorter) audio by URL.
  Run `publish_audio.py` after every audio rebuild, and fully reload the preview
  (`http://localhost:<port>/?r=<n>#project/<name>`) — a hash-only navigation keeps the old page.
