---
name: kinetic-editorial-reel
description: Make a vertical (9:16) "kinetic editorial" reel from a topic, script or voiceover — faceless, word-by-word animated captions with one red keyword per line, a literal hero object per phrase (3D renders, emojis, halftone cut-outs, photos), cream vs black scenes, slam hits, camera pushes, SFX-driven, built with HyperFrames + Three.js. Asks for topic, edit speed and assets, writes a storyboard for approval, prepares assets (accepts transparent PNGs or normal images and removes plain backgrounds), measures anchor points, generates an offline SFX pack, then builds and previews the video. Use this whenever the user wants a reel / short / TikTok / Instagram video with animated word-by-word captions over objects, a satirical or explainer reel in this editorial style, wants to replicate a kinetic-caption editing style for a new topic or voiceover, or asks to turn a voice note / script / idea into this kind of edited video — even if they don't name the skill.
---

# Kinetic editorial reel

A faceless, voice-driven reel where **every spoken word appears on screen as it is said**, over a
new hero object every ~1–2 s. Premium, deadpan motion design — the style is played straight,
which is what makes satire or strong opinions land.

The workflow has two approval gates: the **storyboard** (before any HTML) and the **final
preview** (before render). Between them, move fast and verify with snapshots rather than asking.

## 0. Before starting

- Load `/hyperframes` (entry point) → it routes to `/general-video`; read `/hyperframes-core`
  (composition contract) and skim the `/hyperframes-animation` rules you cite. This skill says
  WHAT to build; those skills own HOW HyperFrames works. Record `flow: companion`,
  `storyboard: yes` in BRIEF.md — this skill always validates the storyboard.
- Read `references/style-guide.md` once (palette, typography, motion, transitions, pacing).
- Scripts live in `scripts/` next to this file. They need python3 (numpy, scipy, Pillow) + ffmpeg.

## 1. Intake — ask, don't assume

Use AskUserQuestion (one round, several questions) for whatever the message didn't already say:

1. **Topic / message** — what is the video about, what's the joke or thesis? Is there a
   **voiceover file** (preferred: it drives all timing) and/or a transcript? If the transcript
   mixes scripts (e.g. a dialect written partly in Latin letters, partly in Arabic), ask which
   script the captions should use and convert consistently (loanwords included).
2. **Edit speed** — calm / standard / rapid (presets in `references/storyboard-template.md`).
3. **Assets** — (a) the user provides images (where? transparent or not — both are fine),
   (b) you produce a prompt list for them to generate with an image AI, or (c) a mix.
4. **Sound** — SFX only, or SFX + music bed; any ending / CTA, or none.

Don't run a speech-to-text model on the voiceover unless the user allows it — many creators
prefer to supply the transcript themselves. Timing can come from the loudness envelope (§3).

## 2. Concept + storyboard → user validation (gate 1)

1. With a voiceover, run `python3 scripts/word_timing.py segments voice.wav --plot env.png` —
   speech segments and pauses are the natural cut points. Look at the plot.
2. Write the concept + `STORYBOARD.md` using `references/storyboard-template.md`: the big idea
   (a light/dark world split tied to the story, what the accent colour literally represents,
   ONE signature move), then one block per frame: time, words, caption + keyword, hero object,
   motion, transition, sfx, and 3D only where it earns its place.
3. If assets are missing, append the **asset list** with generation prompts (no text inside
   images; cut-outs on a contrasting plain background; full-frame photos marked as such).
4. Present it and **wait for approval**. Fold corrections in and re-present; never build on an
   unconfirmed storyboard.

## 3. Prepare (parallelise with subagents)

Once the storyboard is approved and assets exist, send ONE message that starts:

- **Subagent A — SFX**: `python3 <skill>/scripts/make_sfx.py <project>/assets/audio/sfx`
  (deterministic, offline: tap, stamp thuds, paper rustle/flutter/slide, pen scratch, pin click,
  phone vibrate, accelerating clock, bell, sub boom, ripple, impact + bundled whoosh / cinematic
  whoosh / pop / ping / notification / click from the media-use library). If the storyboard
  needs a sound the pack lacks, the subagent adds a `make_<name>()` to a project copy of the
  script using its primitives + `finish()`, then checks a waveform sheet. The sounds are
  synthetic — say so and offer to swap in user-supplied files.
- **Subagent B — anchors**: measure semantic anchor points per `references/anchoring.md` into
  `assets/anchors.json`, verified visually.
- **You** — assets, timing, fonts:
  - `python3 scripts/prep_assets.py <incoming_dir> <project>/assets/img --keep <full-frame photos>`
    → transparent PNGs pass through; opaque images on plain backgrounds get their background
    removed (edge flood-fill + feather + de-spill); photographic / busy ones are flagged
    `NEEDS_CUTOUT`. For people use `npx hyperframes remove-background in.jpg -o out.png`; for
    objects ask for a plain-background version or keep them full-frame. **Look at
    `assets_sheet.png`**: an object the same colour as its background can lose an edge — re-run
    with `--tol 10` or ask for a contrasting background.
  - Texture helpers as needed: `scripts/textures.py halftone | grunge | split`.
  - Word timings: write `script.json` (the segments from §2.1 with the words spoken in each;
    the user's transcript timestamps help assign them), run
    `word_timing.py align voice.wav script.json`. These are ESTIMATES — tell the user and
    invite corrections by timestamp.
  - Fonts: embed locally (composition-kit §2).

## 4. Build

`npx hyperframes init videos/<slug> --non-interactive --example=blank --skill=general-video`,
write BRIEF.md, copy assets in, then write `index.html` following
`references/composition-kit.md` (single file, one section per frame, global-time GSAP timeline,
Three.js module for 3D scenes). Captions carry literal `data-t` values from words.json. Put
`<!-- sfx:start -->` / `<!-- sfx:end -->` markers in the root, write `cues.json`, and run
`python3 scripts/place_sfx.py index.html cues.json --taps` (a soft tap per caption word; slam
words get a heavier hit instead). Default levels: taps .2 / keywords .3, stamps/impacts .75–.9,
whooshes .3, pings/notifications ≈.08, ticking beds ≈.1, voice 1.0.

Author the scenes yourself, inline — subagents are for preparation work, not the final
composition (keeps one consistent hand on timing and style).

## 5. Verify

1. `npx hyperframes lint` → 0 errors (structural warnings from the single-file choice are fine).
2. `npx hyperframes snapshot --at <scene midpoints + every transition/impact frame> --no-end`,
   then `python3 scripts/contact_sheet.py snapshots sheet.png` and LOOK: anchors landing,
   captions not clipped, nothing peeking in early, wipes fully covering, text direction correct.
3. `npx hyperframes check` → must pass (layout/contrast fixes in composition-kit §9).
4. Animation map (`/hyperframes-animation` → `scripts/animation-map.mjs`; set
   `HYPERFRAMES_SKILL_BOOTSTRAP_DEPS=1` if it asks): no dead zones.

## 6. Preview + iterate (gate 2)

`npx hyperframes preview --background`, open the Studio URL in the browser pane and hand off:
what's in it, what to scrutinise (estimated word timings, synthetic SFX), and "render now, or
what changes?". Timing feedback often arrives as a screenshot of the Studio timeline with a
playhead — read the time from the ruler (px per second from two tick labels), re-inspect the
envelope there (`word_timing.py segments … --from A --to B`), pin the corrected word in
`script.json`, re-run `align`, then shift the dependent scenes (`SC`/`END` tables + section
times) and re-run `place_sfx.py`. A mis-heard transcript word can hide a whole beat — a short
interjection often deserves its own one-word punch frame. Log each revision in BRIEF.md.

Render only when the user says so: `npx hyperframes render`, verify the MP4 (duration, audio
present) and report its path.
