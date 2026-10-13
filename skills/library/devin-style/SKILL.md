---
name: devin-style
description: Edit a vertical talking-head clip in Devin Jatho's (@devinjatho) Instagram editing style — replace the background with a professionally lit, out-of-focus studio set (night penthouse / dark studio / warm lounge), relight the speaker with a key-light grade and rim light, then add hard-swapped 1–4 word uppercase captions at chest height with one glowing coloured keyword line whose colour floods the wall behind him, jump-cut punch-ins, zoom-blur whips, dark glass UI cards with blurred background, iOS settings toggles with tap dots, example-post cards with view counts, and a "comment KEYWORD" / save-this CTA, plus SFX — built and rendered with HyperFrames. Use whenever the user says "devin style", "like Devin Jatho", wants a creator/marketing talking-head reel with bold glowing captions, or asks to swap a clip's background for a professional studio / better lighting, even if they don't name the skill.
---

# Devin-style edit

Turns a raw talking-head clip into a Devin Jatho-style reel. Read `references/style-guide.md`
once: it lists what the look is made of, and every rule below comes from it.

Pipeline: **relight + cut out speaker → studio plate → transcript → caption cards → edit plan
(beats) → build → check → preview → render**. Scripts live in `scripts/`. They need ffmpeg,
Python with numpy/scipy/Pillow/faster-whisper, and `npx hyperframes`. Load `/hyperframes-core`
once per session before hand-editing composition HTML.

## 1. Intake (one AskUserQuestion round, only for what's unknown)
- **Clip** path (and whether it's green screen; detection is automatic).
- **Background**: `penthouse` (his signature night city set, default), `studio` (charcoal
  seamless + soft key pool), `lounge` (warm, fairy lights + fireplace), or their own image.
- **Caption language/script**: English uppercase is the default. Arabic/Darija works (Cairo
  Black is used automatically; uppercase doesn't apply).
- **Look**: Devin (bold uppercase neon, hard punches) or Apple (smooth, glass, original background).
- **CTA**: comment keyword ("Comment GEAR…"), save-this, or none. Ask for any b-roll,
  screenshots or example posts they want shown.

## 2. Project + speaker
```bash
npx hyperframes init videos/<slug> --non-interactive --example=blank
cd videos/<slug>
python <skill>/scripts/prep_subject.py "<clip.mp4>" --key left      # key side: left|right|front
python <skill>/scripts/studio_plate.py assets/plate.png --preset penthouse --head-y <head_y from edit/subject.json>
python <skill>/scripts/prep_subject.py "<clip.mp4>" --skip-cutout --plate assets/plate.png   # preview only
```
`prep_subject.py` conforms the clip to 1080x1920/30fps, extracts `assets/voice.wav`, despills
green/blue screens, applies the studio key-light grade and cuts the speaker out to
`assets/subject.webm` (CPU: ~20 s per second of footage, so run it in the background for long
clips). **Look at `edit/bg_preview.jpg`**: hair edges, leftover chair or wall bits, colour fringes.
If the plate's light pool doesn't sit behind the head, re-run `studio_plate.py` with the
measured `--head-y`. A user-supplied background image replaces `assets/plate.png` (blur it
~8 px first so it stays behind the focus plane).

## 3. Transcript → user confirms wording
```bash
python <skill>/scripts/transcribe.py assets/voice.wav --lang en     # fr / ar / omit = auto
```
Show `edit/segments.txt` and fix the words in `edit/words.json` (`"t"` only; keep the times).

## 4. Caption cards + keywords
Pick the keywords: roughly 1 in 5 cards. The colour carries meaning: red = stop/never/money/
mistakes, green = easy/works/growth, yellow = quality/premium, blue = info/rules,
purple/pink = Instagram/brand. Write `edit/keys.json` (`{"stop using": "red", "super easy": "green"}`), then:
```bash
python <skill>/scripts/chunk_captions.py
```
Read the table. Cards should be 1–4 words, should not end on a dangling "THE / MY / AND", and
the keyword should sit on its own line. Re-run with different keys until it reads like a
headline sequence.

## 5. Edit plan → `edit/beats.json`
Walk the transcript and give it rhythm. Typical density for a 40 s reel: a punch every 2–4 s,
2–4 zoom-blur whips, 2–5 graphic moments, 1 CTA. Post a short table (time · words · beat) to the
user, then build unless they object.

| beat | fields | use for |
|---|---|---|
| `hook` | `until` | first card(s) bigger, the 0–2 s claim |
| `punch` | `t, scale (1–1.3), y (-0.05..0.05)` | instant jump-cut reframe; holds until the next camera beat |
| `push` | `t, dur, to, y` | rare slow push on an emotional line |
| `zoomblur` | `t, scale` | whip into/out of a section |
| `flash` | `t, dur, color` | extra wall wash (keyword cards flash automatically) |
| `shake` | `t` | impact on a punchline |
| `card` | `t, dur, title, body[], img?, top?` | glass panel with list; background blurs and darkens; captions hide |
| `toggles` | `t, dur, items[], on[] (times or null), top?` | settings list, rows light up, switches flip |
| `tap` | `t, x, y` | blue cursor tap (pair with toggles / cards) |
| `media` | `t, dur, src (image), pos left/center/right, w?, h?, top?, title?, views?, dim?` or `id` of a static b-roll video | example posts, screenshots, PiP |
| `comment` | `t, dur, word, avatar?` | "comment KEYWORD" CTA |
| `notify` | `t, dur, title, body` | Instagram notification drop |
| `save` | `t, dur` | SAVE THIS FOR LATER + bookmark |
| `kinetic` | `t, dur, color, icon (shield/bolt/chart/spark/warning/building/brain/check or an SVG path), lines:[{words:[{t,s}], size: small/big}], top?` | big kinetic phrase: icon draws, words rise on their onsets, Latin words letter-stagger; captions hide underneath |

B-roll **videos** must be static elements: put them in `edit/extra.html` (example in the
template comment) and reference them with a `media` beat's `id`. Optional `edit/style.json`:
`{"captionFont": "pixel"}` for game topics, `"autoFlash": false`, `"capOffset": 0.03` to move
captions down, `"glowPeak": 0.6`.

## 6. Build + sound
```bash
python <skill>/scripts/build_comp.py [--music assets/music.mp3 --music-volume 0.12]
echo {"duration": <dur>} > edit/sfx.json      # add manual "cues" if needed
python <skill>/scripts/build_sfx.py           # beat sounds + keyword hits, content-hashed file
```
`build_comp.py` regenerates `index.html` from the template each time, so make edits in `edit/*`,
not in the HTML. Bespoke graphics (retention graph, pyramids, montage wall) go into
`edit/extra.html` with their own GSAP code if needed. Keep one timeline: add tweens through a
small inline script that reads `window.__timelines.main`, or extend the template copy deliberately.

## 7. Check → preview → render
```bash
npx hyperframes lint                            # 0 errors
npx hyperframes snapshot --at <hook, every keyword card, each beat midpoint, CTA>
```
Look at `snapshots/contact-sheet.jpg`. Check that captions sit on the chest and not the face,
that no card overlaps a caption, that the glow wash isn't blowing out, that cutout edges are
clean and that the CTA is readable. Then
`npx hyperframes preview --background`, open it, and ask "render now or what changes?".
Render only on approval: `npx hyperframes render -q delivery -o renders/<slug>.mp4`, then check
the duration and that the audio is present.

## Variant: Apple look on the original footage (user feedback, first real edit)
The first client preferred: their **own background kept** ("let the background how it was"),
**smooth** zooms (hard punches/whips/shakes read as "too harsh"), a **sound on every caption**,
and an **Apple style**. Offer it at intake; build it with:
```bash
cp <clip.mp4> assets/source.mp4          # no cutout needed (skip prep_subject's remove-background: --skip-cutout)
echo {"look":"apple","bg":"original","capPill":true,"capOffset":0.1} > edit/style.json
echo {"duration":<d>,"card_ticks":true,"tick_gain":0.14,"keyword_sound":"soft"} > edit/sfx.json
python <skill>/scripts/build_comp.py --video assets/source.mp4
```
Camera: write `push` beats (in 1.06–1.07 over 1.6–2.2 s, back to 1.0 over 1.3–1.6 s, sine) on
the 4–5 strongest lines instead of punch/zoomblur/shake (or set `"smoothCam": true` to convert
them). Apple look = Inter / IBM Plex Sans Arabic 700 in normal case, a soft rise + blur-in, Apple
system colours, liquid-glass cards that let the footage show through, and frosted caption pills
so white text reads on light clothes. **Kinetic variant (user's favourite):** `"kineticWords": true`
(no `capPill`): captions build word by word on each spoken onset, with a strong dark halo, plus
4–5 `kinetic` beats on the strongest phrases, and `"word_ticks": true, "tick_gain": 0.12` in
sfx.json for a soft tick on every word. Keep cards and toggles on the chest (top ≈ 1060–1130), never over the face.

## Known limits (say them up front)
- Background removal is per-frame segmentation: curly hair, fast hand motion and objects held
  in hand can flicker at the edges. Green screen or a plain wall behind the speaker gives the
  cleanest result.
- The studio plates are painted procedurally (offline, deterministic). For a photoreal set,
  supply an image or generate one, e.g. *"dark luxury penthouse office at night, floor-to-ceiling
  window, blurred city lights, warm LED shelves, shallow depth of field, empty, vertical 9:16"*.
- Lighting is a grade plus rim glow, not true 3D relighting. It can't add light from a direction
  the original footage has no light from.
