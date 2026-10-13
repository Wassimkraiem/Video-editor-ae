# Glass edit — design system

Everything here was settled with a real client over several feedback rounds on a
Tunisian clothing ad (Kachabiti, cashmere kachabia). Each rule says *why*, so you can
bend it sensibly for a new brand. A complete working build is in
`references/example/` (index.html, graphics.html, kinetic.html).

## Contents
1. Canvas & layers
2. Tokens (colour, type)
3. Liquid glass
4. Placement — where things may sit
5. Element catalogue (with markup)
6. Motion vocabulary
7. Zooms
8. Sound design
9. Captions
10. Fonts on Windows

---

## 1. Canvas & layers

9:16 1080×1920, footage full-bleed and **untouched** (no grade, no crop, no reframing
beyond the punch-in zooms). `index.html` stacks, bottom → top:

| layer | element | notes |
|---|---|---|
| video | `#video-wrap > video#bg-video` | `data-has-audio="true"` — the speech stays on the video |
| graphics | sub-comp `compositions/graphics.html` (full duration) | glass pop-ups, keyword cards, logo |
| kinetic text | sub-comp `compositions/kinetic.html` (only its window) | word-by-word text + drawn icons, **no background** |
| captions | sub-comp `compositions/captions.html`, `data-track-kind="captions"` | gap-only |
| sfx | `<audio id="sfx" src="assets/sfx.wav">` | `data-volume` ≈ 0.55 |

Insert hosts as full single-line elements — Studio rewrites `index.html` onto one line per
element and stamps `data-hf-id`s, so multi-line string replacements silently miss. Always
grep for the host after inserting it.

## 2. Tokens

```css
--gold: #b08d4f;      /* icons, rules */
--gold-lt: #e9cf94;   /* gold words, numbers' units, kickers on glass */
--ink: #1b1712;
white #ffffff         /* all text on glass */
icy #d6eefb           /* "cold" words before they get struck through */
```
Type: Arabic display = Sakkal Majalla Bold (calligraphic, premium); Arabic UI/captions =
Segoe UI Bold; Latin = Inter 700 (tracked caps for kickers: 0.3–0.42em). Swap the gold for
the brand accent if the brand has one — keep it a single warm accent.

## 3. Liquid glass (every card background)

```css
.glass {
  position: absolute;
  background: linear-gradient(140deg, rgba(255,255,255,.26) 0%, rgba(255,255,255,.07) 45%, rgba(255,255,255,.14) 100%),
              rgba(24,19,14,.34);
  backdrop-filter: blur(22px) saturate(175%) brightness(.92);
  -webkit-backdrop-filter: blur(22px) saturate(175%) brightness(.92);
  border: 1.5px solid rgba(255,255,255,.42);
  border-radius: 26px;
  box-shadow: inset 0 1.5px 0 rgba(255,255,255,.7), inset 0 -1px 0 rgba(255,255,255,.18),
              inset 0 0 28px rgba(255,255,255,.1), 0 16px 40px rgba(0,0,0,.28);
  color: #fff;
  text-shadow: 0 1px 8px rgba(0,0,0,.35);
}
```
The dark tint underneath keeps white text readable whether the card sits on dark robes or a
white wall. Hero/"premium" chip: same recipe, tint .5, gold rim `rgba(233,207,148,.75)`, plus
a sheen bar (`linear-gradient(100deg, transparent, rgba(255,240,200,.45), transparent)`)
swept across once with `x` (-200 → 900). `backdrop-filter` renders correctly in HyperFrames
renders (verified).

**Never** put a full-screen panel/background over the footage — the client's rule: viewers must
see the product the whole time.

## 4. Placement

* **The middle band (y ≈ 800–1130) is home** for pop-ups *and* captions — it's where the eye
  already is. Captions and cards share it because they never overlap in time (see §9).
* **Faces are sacred.** Check every element at its hold time on the contact sheet / snapshots.
  When a shot has kids or people lower in frame, push the element down onto the garments
  just *below* the faces (e.g. kinetic text at y ≈ 1060–1380 in a family shot).
* **Logo end card goes at the top** (y ≈ 90) — mid-frame it covered a child's face.
* Two side-by-side cards (price) use x 38–308 and 772–1042 so the speaker between them stays
  visible. Single cards centre with `left:0; right:0; margin:0 auto; width:fit-content`.
* Shorts/Reels UI eats the bottom ~350 px and right ~120 px — keep text out of there.

## 5. Element catalogue

| element | when | size | content |
|---|---|---|---|
| intro title card | while the product name is spoken | 700×214 glass | Latin tracked kicker (brand · material) + Arabic display title 104px + gold rule |
| chip | short feature words ("دافية", "تحمي من البرد") | h76, 36px text, 32px gold icon | icon + 1–3 words; two may sit side by side |
| hero chip | the premium claim ("HAUT DE GAMME") | 740×120 dark-gold glass | small kicker + 50px tracked Latin, sheen sweep |
| **big keyword card** | the 2–3 claims the client cares most about (durability, no pilling, premium fabric) | h236, Arabic display 150px, 84px icon | word 1 white, word 2 gold, gold underline sweep, slow breathing scale |
| price card(s) | when prices are spoken | 270×236 glass | label, count-up number 100px + "DT" in gold, small note; pack card may show crossed old total + saving badge (**confirm with the client — it's derived, not said**) |
| order checklist | "send us a message with…" | 270×330 glass | chat icon header + rows that tick on each spoken item |
| delivery card | "delivered to your door" | 290×170 glass | truck icon + 2 lines |
| kinetic text | a lifestyle run of phrases (family / camping / nature / no cold) | Arabic 86px, Latin 54px tracked, 98px for the payoff word, 64px stroked icons | **no background**, soft text-shadow; one beat per phrase |
| logo end card | the sign-off | 480×168 pill at the top | white logo PNG + tracked Latin brand name |

Icons are inline SVG line icons (24-unit viewBox, round caps, gold stroke): sun, snowflake,
hourglass, check, family, tent, tree, chat, truck, gem. Kinetic-scene icons use
`pathLength="1"` + `stroke-dasharray:1` so they draw themselves (dashoffset 1 → 0).

Only state what is **said or true**. A "100% CACHEMIRE" kicker was removed because the audio
never said 100%. Derived numbers (3×79 = 237, "−38 DT") must be flagged to the user.

## 6. Motion vocabulary (smooth — no bounce)

The client read overshoot (`back.out`) and wobbles as "shaking". Use only:

* **enter**: `opacity 0→1, y ±18–24 → 0, scale .92→1, blur(6px)→0`, 0.5–0.6 s `power2.out`
* **exit**: `opacity →0, y −14, blur(6px)`, 0.28–0.3 s `power2.in`
* **word rise** (keyword + kinetic): mask line (`overflow:hidden`), `yPercent 110→0, blur 8→0`,
  0.45–0.55 s `power3.out`, fired on that word's spoken onset
* **letters** (Latin kinetic words): per-char spans, stagger 0.035, `y 40→0, blur 6→0`
* **hold**: slow breathing `scale 1→1.04 sine.inOut` across the hold
* **count-up** for prices: tween an object `{v}` with `onUpdate` writing `textContent`
* **gold strike / underline**: `scaleX 0→1`, 0.35–0.6 s `power2.inOut`
* Never animate `letterSpacing` (lint error: stutters) — use scale/blur instead.
* Every `fromTo` after the first on the same target needs `immediateRender:false`.

## 7. Zooms (punch-ins)

On the 3–4 most important lines only. Slow, small, GPU-composited:

```js
const push = (from, to, at, dur, first) =>
  tl.fromTo("#video-wrap", { scale: from }, { scale: to, duration: dur, ease: "sine.inOut",
            force3D: true, immediateRender: !!first }, at);
push(1, 1.06, 3.0, 1.8, true); push(1.06, 1, 4.9, 1.4);   // in, then release
```
`#video-wrap { transform-origin: 50% 42%; will-change: transform; backface-visibility: hidden; }`
Scale 1.06–1.07, 1.5–2.4 s each way. Start the push *on* the line (on the shot cut if the line
starts there). Fast punches (0.3 s, 1.15+, `power4`) and two-step punches looked like shaking.
Verify on the render with `scripts/verify_zoom.py` — the Studio preview can stutter on its own.

## 8. Sound design

All soft, always under the voices (`build_sfx.py` level guide). Pattern:
pop on every card entrance · soft whoosh-short on every exit · whoosh-short + sparkle on the
gold word of keyword cards · sparkle on the premium chip · click-soft on checklist rows ·
whoosh-short per kinetic beat + sparkle on Latin words · pop + whoosh on a strike-through ·
whoosh 0.22 at each zoom start · chime on the logo · faint tick on each visible caption.
No impacts/booms. Keep the user's `data-volume` if they changed it in Studio.

## 9. Captions

* Small (46px Segoe UI Bold Arabic, 40px Latin), white at 72% → word turns gold on its onset,
  settles to white; keywords grow 1.18 and stay gold. Soft rise + blur in on the voice onset,
  soft exit.
* Centred in the middle band (`top: 918px`).
* **Gap-only**: a caption never shows while an animation displays those words (or any card is
  up). Mark those groups `"hidden"` in `edit/captions.json`.
* Synced to the *real* voice onset (`build_captions.py` snaps Whisper times), and never starts
  just before a shot cut.

## 10. Fonts on Windows

The renderer only auto-supplies a short list (Inter, IBM Plex Mono, JetBrains Mono, Montserrat,
Open Sans, EB Garamond, Playfair, Noto Sans JP…). Arabic needs a local file: copy
`C:/Windows/Fonts/segoeuib.ttf` and `majallab.ttf` into `fonts/` and declare `@font-face`
**inside each sub-composition's `<template>`**. Inter: copy
`~/.claude/skills/talking-head-recut/assets/fonts/Inter-700-latin.woff2`.
