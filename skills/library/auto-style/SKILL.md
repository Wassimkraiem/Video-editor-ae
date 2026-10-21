---
name: auto-style
description: "Let Claude design the look: read the script, decide what kind of video it is and what mood it needs, then build captions, motion graphics, transitions and sound in a look made for it, using the user's brand kit (colours, fonts, logo) when one is given. Use when the user picks Auto style, says \"you choose the style\", \"match the script\", or gives only a palette or brand."
---

# auto-style

There is no fixed look. You are the art director: the words decide the design, the brand kit
decides the colours and fonts. Build it as one HyperFrames composition (the engine notes say how).

## 1. Read the script first

Before designing anything, answer these from the transcript (or script) and the user's ideas:

- **What is it?** Product/app promo, tutorial/explainer, founder story, offer/sale ad,
  testimonial, news/hot take, motivational, event or launch announcement.
- **Who is it for, and what should they do at the end?** (buy, download, comment a keyword,
  follow, book). That decides the end card.
- **Energy:** calm and premium, confident and clear, or loud and punchy. Take it from the words
  and their pace (many short words per second = punchy).
- **The 3-6 moments that matter:** the hook (first 2 s), the problem, each benefit or step,
  numbers/prices/names, the call to action. Only these get big graphics; everything else gets
  clean captions.

## 2. Pick one visual language and stay in it

| Video | Visual language |
|---|---|
| App / SaaS / tech | Clean UI: glass or solid cards, phone/browser frames drawn with CSS, icons, counters, check-lists ticking in, cursor taps. Sans-serif, generous spacing. |
| Offer / sale / ad | Bold: big price and % cards, stamp/burst shapes, strong colour blocks, fast punch-ins, a clear CTA button. |
| Explainer / tutorial | Editorial: numbered steps, a keyword per line highlighted, arrows and underlines that draw on, a progress bar. |
| Premium / fashion / food | Minimal luxury: thin serif headlines, lots of empty space, slow fades and slides, fine lines, no stickers. |
| Story / founder / testimonial | Documentary: lower-third name card, quote cards, warm grade, gentle zooms, captions do most of the work. |
| Hot take / news | Kinetic type: words slam in one by one, high contrast, quick cuts, a headline banner. |

Mixing languages looks cheap. One language, used consistently, looks designed.

## 3. Colour and type

- **With a brand kit:** use its colours exactly; the first is the accent (keywords, buttons,
  highlights), the others for cards and backgrounds. Add only neutrals (near-black, off-white,
  greys) and tints. Use its fonts; load them from Google Fonts.
- **Without one:** derive a palette from the subject (a bank: deep navy + one bright accent;
  food: warm cream + tomato red; tech: black + electric blue/violet; wellness: sage + sand).
  Max one accent colour plus neutrals. Fonts: one display face for headlines and keywords
  (e.g. Montserrat/Inter Black/Archivo/Playfair Display for premium), one text face for captions.
- Arabic or Darija text: use Cairo, Tajawal or Noto Sans Arabic so the letters join properly.

## 4. Captions (always, unless the user says no)

- Short lines: 2-5 words, hard-switched on word onsets, never two lines fighting a graphic.
- One keyword per line in the accent colour (a number, a product name, the benefit).
- Lower third of the frame for talking heads (stay clear of the face and the bottom 12%
  platform UI); centred for no-footage videos.
- While a big graphic is up, either hide the captions or move them so nothing overlaps.

## 5. Motion

- Every graphic starts on the word it illustrates and leaves before the next idea.
- Entrances 0.3-0.5 s with ease-out (power3/expo), exits faster than entrances.
- Punch-in zooms (1.0 -> 1.08-1.15) only on the important lines; at most one every 4-6 s.
- Transitions between sections: one kind only (a wipe, a whip blur or a simple cut).
- Respect the user's intensity: MINIMAL means captions plus 3-4 graphics in the whole video.

## 6. Structure that sells

1. **Hook (0-2 s):** the boldest claim or question as a big headline; something moves in the
   first frame.
2. **Problem or context:** one card or a reaction zoom.
3. **Benefits / steps:** one graphic per point, numbered when it's a list.
4. **Proof:** a number, a rating, a logo row or a quote, if the script has one.
5. **Call to action:** an end card for the last 2-3 s with the action and, if given, the logo.

## 7. Before you answer

Check: one visual language; colours only from the kit or your derived palette; captions
readable and not covered; every graphic timed to its word; an end card with the CTA. In your
notes, tell the user in one sentence which look you chose and why.
