# Storyboard template (what the user validates)

Write the plan to `<project>/STORYBOARD.md` AND present a readable version in chat. The user
approves it before any composition HTML exists.

## Frontmatter
```yaml
---
format: 1080x1920
duration: <voice length + ~0.5s hold>
message: <one line: the joke / thesis>
arc: <e.g. Claim → Twist → Excuse → Proof → Punchline>
speed: calm | standard | rapid
mode: collaborative
---
```

## Big idea block (3–5 lines, before the frames)
- The **world split**: which scenes are LIGHT (cream `#FFF8F3`) vs DARK (black), and why — tie
  it to the story (e.g. "the old way = warm cream paper, the new way = cold black screens").
- The single **accent** (`#E71F28` red) and what it literally is in this story (ink, a warning
  light, a price tag…).
- The **signature move** — one move, used ≤ 4 times (e.g. a stamp-slam on the key nouns).
- Sound identity (SFX only / music bed) and the recurring decor (grid, barcode, ribbon, tape…).

## One block per frame
```markdown
## Frame N — <short title>
- time: <start>–<end> s        (cut on pauses / clause boundaries from word_timing.py)
- bg: LIGHT | DARK
- voiceover: <exact words spoken in this window>
- caption: <lines, keyword in **bold** = red; mark SLAM>
- hero: <ONE literal object for this clause> (asset: <file or "to generate">)
- motion: <entry + camera + exit, named from composition-kit §5>
- transition out: cut | ripple | iris | prop wipe | rotate-through
- sfx: <cues with times>
- 3D: <only if Three.js adds something here>
```

## Speed presets (the user picks one; pacing and motion durations follow it)

| preset | avg frame | range | word reveal | camera | transitions |
|---|---|---|---|---|---|
| calm | ~2.0 s | 1.4–3 s | .3 s blur-in, softer eases | slow pushes 1→1.05 | mostly cuts + 1 crossfade |
| standard | ~1.4 s | 0.8–2 s | .2 s (.3 s keywords) | pushes 1→1.1, rotational entries | cuts + ripple / iris / wipe once each |
| rapid | ~0.9 s | 0.45–1.4 s | .15 s, snappier `expo.out` | constant motion, shakes on hits | hard cuts, blank 2-frame beats, more one-word frames |

One-word punch frames (a short interjection, a "no no", a "yes?") work at any speed: black
frame, huge red glowing word, shake + impact SFX.

## Asset list (when assets are missing)
For each hero: filename, what to generate, framing notes, and whether it's a CUT-OUT (render on
a plain solid background that contrasts with the object — white objects on mid-grey or green,
dark objects on white; transparent PNG if the tool supports it) or a FULL-FRAME photo (a room,
a desk, a street — no cut-out). Add the shared style line: *photoreal 3D product render, soft
studio lighting, subtle soft shadow, clean, high detail, isolated on a plain background, 4K,
no text, no logos*. Ask for NO text inside images (image models garble text, non-Latin scripts
especially) — captions, clock hands, screen UI and any printed wording are built in HTML.
Avoid real official emblems, real brands and real people's likenesses unless the user owns them.
