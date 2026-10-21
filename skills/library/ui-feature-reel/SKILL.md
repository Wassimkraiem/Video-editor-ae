---
name: ui-feature-reel
description: "A voiceover-free product reel in the modern SaaS launch style: dark, clean recreated UI, short on-screen lines instead of narration, music-driven pacing, cursor taps, glass panels with soft 3D tilt and gradient glow, each feature shown at work. 20-60 s. Use for app or software feature launches, changelogs, \"product reel\", \"show the app\", \"SaaS promo\", or when there is no footage."
---

# ui-feature-reel

The product is the hero and the interface tells the story. No narrator needed: short text lines
and music carry it. Build it as one HyperFrames composition, no footage required.

## Structure

1. **Intro (0-3 s):** product name or the promise in one line ("Plan your week in seconds"),
   on a dark gradient, the first UI panel already sliding in behind it.
2. **Features at work (most of the video):** 2-4 features. Each gets 4-8 s:
   a one-line label (what it does, verb first) -> the UI panel animating the action (typing,
   a list sorting, a toggle switching, a chart drawing, a card being dragged) -> the result
   highlighted (glow ring, check, number counting up).
3. **Use cases (optional, fast):** 3-5 quick cards showing who uses it or what for, 1 s each.
4. **Outro (last 3 s):** logo or name, one line ("Available today"), CTA if given.

With a script or transcript, follow its order; each sentence about a feature becomes one feature
block. With only the user's ideas, write lines of 2-6 words.

## Recreated UI (draw it in HTML/CSS, never a screenshot unless the user attached one)

- Panels: 880-960 px wide, background #15161A to #1C1D22, 1 px border rgba(255,255,255,.08),
  radius 28-36 px, inner padding 40 px, subtle top highlight.
- Content: rows, chips, toggles, avatars (coloured circles with initials), progress bars, small
  charts. Real-sounding labels from the user's product, never lorem ipsum.
- Cursor: a white arrow with soft shadow that glides (power2.inOut, 0.5-0.8 s) and taps
  (scale 0.85 + ripple ring) on the element that changes.
- Depth: tilt the panel slightly in 3D (rotateX 8-12deg, rotateY -8 to 8deg, perspective 1600 px)
  and ease it flat when the action happens. Gradient glow behind panels in the accent colour,
  60-90 px blur, 25-40% opacity.

## Look

- Dark mode: background #08080B with a large soft radial gradient in the accent colour.
- Brand kit colours if given (first = accent). Otherwise accent electric blue #4F7CFF or violet
  #8B5CF6, plus white and greys.
- Type: Inter or the brand font; labels 64-80 px semibold, UI text 28-36 px.
- Lots of empty space; one thing moving at a time.

## Motion

- Panels enter with y +60 -> 0, opacity, slight scale 0.96 -> 1, 0.6 s expo.out.
- Feature to feature: the current panel slides up and fades (0.4 s) while the next rises.
- Text lines: fade + rise 24 px, 0.4 s; never more than one line on screen.
- Numbers count up; checkmarks draw (stroke-dashoffset); lists re-order with FLIP-like moves.
- Cut on the music: every block change on a strong beat (about every 2-4 s).

## Sound

A clean electronic or lo-fi bed; soft UI clicks on taps, a subtle whoosh between features, a
gentle chime on results. No voice unless the user has footage with speech.

## Check

Promise in the first 3 s; each feature shown doing something (not just named); max one line of
text at a time; UI labels about the user's real product; ends on the name and one CTA.
