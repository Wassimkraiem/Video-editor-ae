---
name: wassim-style
description: Wassim's house style for vertical talking-head reels (tech / AI explainers, often Tunisian Darija with Latin tech words). Cool blue look with smooth expo scene switches between full footage, a light blue-grey "paper" page where the footage shrinks into a rounded card with the speaker's head popping out above it, and a navy panel that wipes in for UI moments. Includes frosted-glass caption pills that fill in word by word with an electric-blue keyword box, headlines that blur in word by word in heavy uppercase Montserrat Black / Cairo Black (blue neon glow on footage), browser/screenshot windows with drawn highlight boxes and label chips, terminals that type, glass stat cards that count up, chips, tags, people grids and icon arcs, and very soft sound effects. Built and rendered with HyperFrames. Motion comes from Raed Ouerfelli's reels and type from Devin Jatho's. Use whenever the user says "wassim style", "my style", "edit it like the protect-your-job video", "ouerfelli style", "head pops out of the card", or hands over a talking-head clip for an explainer reel in this look, even if they don't name the skill.
---

# Wassim style

Turns a raw talking-head clip into a tech-explainer reel in **Wassim's house style**. It is a blend: the
animation and scene system come from Raed Ouerfelli, the heavy uppercase type comes from Devin Jatho, and
on top of that sit Wassim's own choices, a **blue palette** and **very soft caption sounds**. Read
`references/style-guide.md` once; every rule here comes from it.

Pipeline: **cut-out (background) → transcript → phrases + keywords → edit plan (scenes + beats) → build →
sfx → lint → snapshot → render**. Scripts are in `scripts/`. They need ffmpeg, Python with
numpy/scipy/faster-whisper, and `npx hyperframes`. Load `/hyperframes-core` once per session before
hand-editing composition HTML.

> **npx tip:** right after a hyperframes release, the newest tarball can 404 on npm for a while. If
> `npx hyperframes …` fails with E404, pin the previous version (`npx hyperframes@<prev> …`).
> `prep_cutout.py` already does this automatically.

## 1. Intake
If the user said "do everything / no questions", skip this and choose defaults. Otherwise ask one
AskUserQuestion round, only for what's unknown:
- the clip path
- the caption language (Darija in Arabic script with Latin tech words is the default for Tunisian speakers)
- screenshots, logos or links to show (the `shot` beats take images)
- whether to keep the default blue palette or use brand colours (add a preset to `PALETTES` in the template)

## 2. Project + cut-out (start first, it's slow)
```bash
npx hyperframes init videos/<slug> --non-interactive --example=blank      # or copy hyperframes.json/meta.json/package.json
cd videos/<slug>
python <skill>/scripts/prep_cutout.py "<clip.mp4>"      # run in the background: ~7 min per 40 s on CPU
```
This conforms the clip to `assets/source.mp4` (1080x1920/30), writes `assets/voice.wav`, cuts the speaker out to
`assets/subject.webm` and measures the head into `edit/subject.json`. Without a cut-out, everything still works,
but paper mode shows a plain card with no head pop-out.

## 3. Transcript → fix the words
```bash
python <skill>/scripts/transcribe.py assets/voice.wav --lang ar --prompt "<a Darija sentence with the topic's words>"
```
**Darija:** with no prompt, Whisper "translates" into formal Arabic (MSA). A Darija prompt (for example
`"باش نفسرلك كيفاش تحمي خدمتك من الـ AI. برشا، توا، كيفاش، خاطر، تنجم، متاعك."`) makes it write the
dialect. Then fix the words in `edit/words.json` (change `"t"` only and keep the times):
- Write tech words in Latin.
- Join the article to a Latin word as one token: `"الـ AI"`, `"الـ Productivity"`.
- Fix mishearings (e.g. `البيئة` → `الباهية`).

Show the user the uncertain spots.

## 4. Pills + keywords
Write `edit/phrases.txt` with one pill per line: the transcript words in order, grouped as natural
2–4-word phrases. Never end a line on من / في / باش / اللي / و. Then write `edit/keys.json` (≈1 pill in 4
gets a keyword: product names, numbers, the punch word) and run:
```bash
python <skill>/scripts/chunk_captions.py          # prints the pill table; [brackets] = blue keyword box
```
Keys are case-insensitive substrings: `{"impossible": "maroon", "الشركات": "maroon"}`. `"maroon"` means the
palette's keyword colour (electric blue by default); `cyan`, `blue`, `green` and `gold` are fixed alternatives.

## 5. Edit plan → `edit/beats.json`
Walk the transcript and switch scene every 3–5 s, following meaning:
- **full** for the hook and personal lines
- **paper** for explanations
- **green** (the navy panel; the mode keeps its historical name) for tools, numbers and lists

Each scene gets one main visual and usually a headline. Post a short table (time · words · scene · visual)
and then build. Time word-level things (`s`, `hotAt`, `lineTimes`, `items[].t`, `hl[].t`) to the
`edit/words.json` onsets.

| beat | fields | notes |
|---|---|---|
| `scene` | `t, mode: full\|paper\|green, dur (0.7)` | expo.inOut. Green wipes from the right and exits to the left |
| `hook` | `t, dur, top?, lines:[{size?, words:[{t, s, k?, glow?}]}]` | big title on footage. `glow: blue` (default choice; red/green/yellow/purple also exist) = neon word, `k: maroon` = keyword box. Lines auto-fit 1000 px |
| `title` | same as hook (default size 66, top 200) | headline. Colour follows the scene (navy on paper, light on the panel, white+glow on footage) |
| `tag` | `t, dur, text, icon?, x, y` | small blue pill beside the face (x≈680–720, y≈560–660 on full) |
| `chips` | `t, dur, items:[{t, text, x, y}]` | glass pills that pop in on their own times |
| `shot` | `t, dur, top?, url, img?` or `lines:[str or {text,h,color,html}], lineTimes?, hl:[{t,line,x?,w?}], label?, labelAt?` | browser window. Use `img` for real screenshots. `hl` draws a glowing blue box around a line |
| `terminal` | `t, dur, top?, prompt, lines[], lineTimes?` | prompt types, then the lines fade up |
| `stat` | `t, dur, top?, from, to, prefix?, suffix?, dec?, count?, sub?` | count-up glass card |
| `people` | `t, dur, top?, rows, cols, share, hotAt` | person grid; `share` turns blue at `hotAt` |
| `icons` | `t, dur, top?, items:[icon names], hot?, hotAt?` | arc of glass tiles; icons: spark bolt brain chart check shield robot gear briefcase building rocket clock warning user (or an SVG path) |
| `list` | `t, dur, top?, title?, items:[{t, text}]` | glass card, rows tick in |
| `push` | `t, to (1.07), dur, hold, back` | slow zoom on footage (full mode only) |

Any beat can take `"theme": "paper"|"green"|"video"` to override the colour it gets automatically,
and `"captions": false` to hide the pills while it plays.

**Layout:**
- **Paper**: the head top sits at 40 % (y≈770), so cards go between y 200 and 740.
- **Green**: content can be centred (y 300–1000).
- **Pills** stay at y≈1330 everywhere. Move them with `edit/style.json` `{"capY": {"paper": 1360}}`.

Other style keys:
- `"palette"`: `"blue"` is the default (cool paper, navy panel, electric-blue keyword boxes and
  highlights). `"classic"` gives Ouerfelli's original cream/green/maroon. In beats, use `"glow": "blue"` on
  footage titles to match the blue palette.
- `"startMode": "paper"`
- `"popout": false`
- `"paper": {"scale": 0.74, "headTop": 0.4, "card": [1180, 100, 36, 100], "radius": 46, "blur": 7, "headX": 0.5, "headRx": 300, "headRy": 330}`

The head ellipse (`headX/headRx/headRy`) limits which parts of the cut-out may leave the card. Shrink it if
stray background bits show above the card.

## 6. Build + sound
```bash
python <skill>/scripts/build_comp.py [--music assets/music.mp3 --music-volume 0.1]
echo {"duration": <dur>, "word_ticks": true} > edit/sfx.json     # defaults: tick_gain 0.025, keyword_gain 0.4
python <skill>/scripts/build_sfx.py
```
Caption sounds must stay subtle: louder per-word ticks and keyword hits were "annoying". The defaults are
already quiet; never raise them unless asked, and set `"word_ticks": false` if they still stand out.
`build_comp.py` regenerates `index.html` every time, so edit `edit/*`, not the HTML. Bespoke visuals (a folder
with photos, a perks wall) go in `edit/extra.html`. They are animated from a small inline script that reads
`window.__timelines.main` after it is registered.

## 7. Check → preview → render
```bash
npx hyperframes lint                                 # 0 errors (the onUpdate counter warning is expected)
npx hyperframes snapshot --no-end --describe false --at <hook, each scene midpoint, each keyword>
```
Look at the contact sheet:
- The hook fits.
- Nothing sits on the face.
- In paper mode, no stray cut-out blobs show above the card.
- Highlight boxes wrap their line.
- Pills never cover a card.

Then `npx hyperframes preview --background`, or render if the user said to do everything:
`npx hyperframes render -q delivery -o renders/<slug>.mp4`. Check the duration and that the audio is present.

## Known limits
- Head pop-out quality depends on the cut-out. Busy backgrounds can leave blobs (the head ellipse hides
  most of them), and fast hand motion can flicker at the edges.
- Whisper's Darija is approximate. Always proofread mixed Darija/French/English words.
- Screenshots in `shot` are mocked from text lines unless real images are supplied (`img`).
