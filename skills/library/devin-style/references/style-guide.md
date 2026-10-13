# Devin-style: what the edit is made of

Analysed from four Devin Jatho reels (@devinjatho: "Stop using hooks", "Fix these 5 settings",
"Lighting / background / camera", "Instagram story algorithm"), 23–56 s each, 1080x1920, 30 fps.
Spoken pace is about 185 wpm, and something on screen changes every 0.3–0.8 s.

## 1. The set (why the background swap matters)
- **Dark, moody, expensive-looking room**: a night penthouse with a floor-to-ceiling window,
  out-of-focus city lights and hills, warm LED shelf strips, and a dark desk across the bottom
  ~20 % of the frame. Other reels use a warm lounge (fairy-light bokeh, fireplace).
- Everything behind him is **out of focus** (shallow depth of field). He is the only sharp object.
- **Studio key light** on the face, falling off to one side. Shadows are slightly cool and
  highlights slightly warm. Contrast is high but the blacks stay soft.
- Heavy **vignette**, plus a near-black **desk/foreground gradient** at the bottom.
- One reel says it outright: green screen + "professional lighting" + a $6000 camera is what
  makes people watch. `prep_subject.py` + `studio_plate.py` recreate this from any clip.

## 2. Captions (the core of the look)
- **1–4 short words per card**, usually 2. Cards are **hard-swapped** on the spoken word: no
  fades and no word-by-word reveal inside a card. There is only a 2-frame scale pop (1.08 → 1).
- **Uppercase heavy geometric sans** (Montserrat Black is the free stand-in), ~84 px at 1080 w,
  tight line height, 1–2 lines stacked and centred.
- **Placement: chest height** (~52–57 % of frame height) over his body, never over the face.
  The opening hook is bigger (~104 px).
- White text with a **soft white glow** plus a dark drop shadow, so it reads on anything.
- **One keyword line per card in a saturated colour with a strong same-colour glow**:
  - red: stop / never / mistakes / money / "MY $6000"
  - green: easy / works / growth / "DISGUSTINGLY EASY"
  - yellow: quality / "LUXURIOUS", "PROFESSIONAL", "HOW GOOD"
  - blue: info / tech / rules
  - purple/pink: Instagram / brand
  Use colour on only ~1 card in 4–6. A colour used everywhere stops meaning anything.
- **The keyword's colour floods the wall behind him** (red/green backlight wash) while the card
  is up. This is the signature move (`autoFlash`).
- Variant: **pixel/arcade font** in bright green for "game" topics (RULES, CHEATCODES, 1ST/4TH/32ND).

## 3. Camera
- **Jump-cut punch-ins**: instant reframes between ~1.0 and ~1.25 every sentence or two, often
  alternating wide and close. No slow Ken Burns on dialogue.
- **Zoom-blur whips** into b-roll and back (motion blur, 3–5 frames).
- **Background blur + darken** whenever a UI card is on screen. He stays faintly visible behind it.

## 4. Graphics vocabulary (pick what the script needs)
- **Dark glass cards** (Notion/iOS-style panel, rounded 30–40 px) for lists and "the template".
- **Settings toggles**: an iOS row list, the active row outlined in glowing blue, switches flipping
  green, and a **blue tap dot** standing in for the finger.
- **Phone mockups / example posts**: rounded video cards with a title and a "◉ 1.2M" view count,
  shown left and right of him (picture-in-picture) or full centre.
- **Data visuals**: retention graph dropping in red, follower pyramids, rankings (1ST/4TH/32ND),
  neon glows. Build these per project when the script calls for them.
- **Montage wall**: a grid of many clips, tinted red, for "everyone's heard these".
- **CTA**: comment box with avatar, the keyword typed letter by letter, and a purple send button
  ("Comment CODE…"). An Instagram notification drops in ("Here's your template"), or
  "SAVE THIS FOR LATER" + bookmark icon.

## 5. Sound
Short whooshes on whips and b-roll, pops on cards, clicks on taps, keyboard typing on the
comment CTA, a notification ding, and a soft bass hit on the coloured keyword cards. The voice is
always on top; music, if any, is a quiet bed.

## 6. Structure
Hook (big coloured claim, 0–2 s) → context with proof b-roll → the steps/rules (each one gets a
visual) → payoff line → CTA (comment keyword / save). No intro, no logo sting. It ends on the CTA.
