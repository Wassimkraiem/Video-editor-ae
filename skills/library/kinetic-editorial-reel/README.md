# kinetic-editorial-reel

A [Claude Code](https://claude.com/claude-code) skill that turns a topic, script or voiceover into a
vertical (9:16) **kinetic editorial reel**. Every spoken word appears on screen as it's said, with
one red keyword per line and a literal hero object for each phrase. Scenes alternate between warm
cream paper and black glow, with slam hits, camera pushes and sound effects. It's built with
[HyperFrames](https://hyperframes.heygen.com) and Three.js.

## What the skill does

1. **Intake:** asks for the topic or message, the voiceover and transcript, the edit speed
   (calm / standard / rapid), the assets and the sound (SFX only, or with music).
2. **Storyboard:** writes a frame-by-frame plan, with an image-generation prompt list if assets
   are missing. You approve it before anything is built.
3. **Preparation:** subagents handle two jobs in parallel:
   - Generate an offline sound-effect pack (`scripts/make_sfx.py`).
   - Measure anchor points on your images so props land exactly where they should.
   - Meanwhile the main session prepares assets, word timings and fonts:
     - **Assets:** transparent PNGs are used as-is. Normal images get plain backgrounds removed
       (`scripts/prep_assets.py`).
     - **Word timings:** estimated from the voice's loudness envelope, with no speech-to-text
       model (`scripts/word_timing.py`).
4. **Build:** one HyperFrames composition with word-by-word captions, a GSAP timeline and
   Three.js layers where 3D helps. Sound effects are placed automatically (`scripts/place_sfx.py`).
5. **Verify and preview:** lint, snapshots, `hyperframes check`, then the Studio preview. It
   renders only when you say so.

## Requirements

- Claude Code
- The HyperFrames skills: `npx hyperframes skills update general-video`
- Node.js (for `npx hyperframes`), `ffmpeg`, and Python 3 with `numpy`, `scipy`, `Pillow`:
  `pip install numpy scipy pillow`

## Install

Clone into a skills folder:

```bash
# for one project only
git clone https://github.com/ouerf-man/kinetic-editorial-reel .claude/skills/kinetic-editorial-reel
# or for all your projects
git clone https://github.com/ouerf-man/kinetic-editorial-reel ~/.claude/skills/kinetic-editorial-reel
```

Then ask Claude Code something like:

> Make a kinetic reel from my voiceover `voice.wav` about why small businesses still run on
> WhatsApp. Here's the transcript: …

## Scripts

| Script | What it does |
|---|---|
| `scripts/word_timing.py` | Finds speech segments and splits words from the loudness envelope. You can pin corrected words. |
| `scripts/prep_assets.py` | Keeps transparent PNGs, removes plain backgrounds from opaque images, flags photos, and writes a report plus a contact sheet. |
| `scripts/make_sfx.py` | Deterministic offline SFX pack: taps, thuds, paper, pen, pin, phone buzz, clock, bell, booms, ripple, plus converted whooshes and pops. |
| `scripts/place_sfx.py` | Writes the `<audio>` cue block into `index.html`, allocates tracks, and adds a tap per caption word. |
| `scripts/textures.py` | Coarse halftone, ink-grunge mask, and splitting multi-object sheets. |
| `scripts/contact_sheet.py` | Tiles snapshot frames into one review sheet. |

## Credits

Some sounds (whooshes, pop, ping, notification, click, key press, bass impact) are converted at
run time from the sound library bundled with HyperFrames' `media-use` skill, which is under the
Pixabay Content License. No audio files are included in this repository. Every other sound is
synthesized by `make_sfx.py`.
