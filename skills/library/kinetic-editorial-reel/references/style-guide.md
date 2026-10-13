# Style guide — the kinetic editorial reel look

## One-line summary

Faceless, voiceover-driven **kinetic typography**: every spoken word appears the moment it is
said, over a new "object scene" every 1–2 s, alternating **warm cream paper** scenes and **pure
black glow** scenes, with **one red keyword per line**, blur-in word reveals and constant slow
camera motion. Premium "editorial / keynote-meets-scrapbook" feel.

## Format & pacing

| Property | Value |
|---|---|
| Aspect | 9:16 vertical, render 1080×1920, 30 fps |
| Scene length | avg ~1.4 s (0.8–2 s) at standard speed |
| Words on screen | 100 % of the voiceover, word by word |
| Talking head | none |
| Script shape | hook statement → "but…" twist → reason → consequence → reframe → proof → payoff |

Rule: a new visual idea on every new clause. Never hold one static layout for more than ~2 s —
a new word lands, the scene changes, or the camera moves.

## Palette

| Role | Hex | Notes |
|---|---|---|
| Light background | `#FFF8F3` | warm cream paper, never pure white |
| Dark background | `#060505` / black | radial vignette glow behind the subject |
| Accent / keyword | `#E71F28` | the ONLY accent colour |
| Text on light | `#151211` | near-black |
| Text on dark | `#FFFFFF` | |
| Neutral props | `#8E8E8E`–`#CDC7C0` | grey cards, the grey ribbon |
| Tint wash | `#FBD5CC` | left behind by a red ripple |

Hard cuts between LIGHT and DARK scenes are the main energy device (they act like flash cuts).
Aim for runs of at most 2–3 same-tone scenes.

## Typography

- Neo-grotesk sans (Helvetica / SF / Plex-like), tight leading (lines almost touch).
- Two tiers per caption block: **setup words** medium ~84 px; **keyword** bold, 1.6–2.2× bigger,
  red. One keyword (or phrase) per block. Occasional huge white punch line (`xl`).
- Poster-like staggered lines (each line indented a little more).
- On dark scenes the red gets an outer glow/bloom and white text a soft white glow. On light
  scenes, flat colour, no stroke.
- Text often overlaps the object (over it, inside it, beside it).

### Word reveal
Each word on its spoken syllable: opacity 0→1, blur ~16–26 px → 0, scale 1.2–1.35 → 1, 5–9
frames, ease-out. Words stay and build the sentence; the block leaves with the cut (or a quick
fade when a long scene swaps caption blocks). The red keyword is washed-out pink while blurred,
then snaps to full red.

## Visual assets

ONE literal hero object per clause: glossy 3D renders, 3D emoji, halftone B&W cut-outs, real UI
screenshots, brand-neutral icons, taped photos, full-frame photos for place scenes. Recurring
decor gives the "designed" feel: faint grid, a barcode, a tiny "HD" micro-label, a thick grey
curved ribbon sweeping through the frame, masking tape and push-pins (scrapbook), depth of field
(huge blurred copies of objects in the foreground corners), soft vignette on dark scenes.

## Camera

Every scene moves: slow push-ins (to 105–115 %), rotational entries (object enters rotated
20–45° and small, then settles), overshoot pops, blur→sharp focus pulls, micro-drift, and the
odd rotate-through exit.

## Transitions

Mostly hard cuts on clause boundaries. Specials, each used once or twice: light↔dark cut,
2–4-frame empty beat before a key line, accent-colour ripple that tints the background, black
iris wipe, rotate + zoom-through, a prop that fills the frame into the cut.

## Sound

Clear, close voice; cuts and word reveals locked to syllables. Either no music (SFX only) or a
low bed ducked under the voice. SFX: soft tap per word, whoosh on moves, pop on icons, heavy hit
on slams and punch frames, small foley that matches the objects on screen.
