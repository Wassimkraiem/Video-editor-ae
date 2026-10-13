# Wassim style: what the edit is made of

**Wassim's defaults on top of the references:**
- A **blue palette**: cool paper #eef2f8, navy panel #0d2b66 → #050f2e, electric-blue keyword boxes
  #1f5bff with a blue glow, and blue highlight outlines.
- **Very soft caption sounds**: per-word tick at 0.025 and keyword sound at ×0.4.

Below are the original reference notes. Wherever they say green or maroon, the blue palette replaces it;
`"palette": "classic"` brings the originals back.


This guide was built from four reels. Three are by Raed Ouerfelli (@ouerfelli_raed), Tunisian Darija tech
reels ("Claude 1 year free for startups", "Reverse engineer anything", "I have ADHD skill"). One is by
Devin Jatho (@devinjatho, "Instagram story algorithm"). All four are 1080x1920 and 40–51 s long.

The blend: **the motion system, scenes, colours and cards come from Ouerfelli; the type comes from Devin**
(heavy uppercase Montserrat Black / Cairo Black, with a neon glow when it sits on footage).

## 1. Three scenes (Ouerfelli's backbone)
Something changes every 1–3 s, and roughly every 3–5 s the whole layout switches between:
- **full**: the footage fills the frame (his room is naturally shallow-focus). It is used for the hook and for
  personal lines ("imagine you're an expert…").
- **paper**: a cream page (#f1ece3) with a soft vignette. The footage **shrinks into a rounded card**
  (r≈46 px, 80 % wide) across the bottom ~40 % of the frame, and **his head pops out above the card's
  top edge**: the cut-out speaker is drawn over the card and only clipped by the card below its top.
  The room inside the card is softly blurred. The top 40 % holds a headline plus a screenshot, folder
  or icon card. It is used for explanations and proof.
- **green**: a deep brand-green panel (#0f4536 → #072a21 radial) **wipes in from the right** while
  the page drifts left. The footage is gone, and the panel carries glass cards, a terminal, a perks wall
  or an icon arc. It is used for tools, numbers and lists.
Transitions are **expo.inOut, ~0.7 s**, smooth and never a hard cut. The camera barely moves; there are
no whips and no shakes. A rare slow push (1.06–1.08) lands on a strong line.

## 2. Captions: frosted pill, words fill in
- One **frosted light-glass pill** at ~69 % of frame height in every scene (y≈1330). It is white-ish,
  translucent, has a 1.5 px white border, an inner top highlight and a soft shadow, and **a sheen sweeps
  across** it when it appears.
- **One short phrase per pill** (2–4 words). The pill is sized for the full phrase and **the words fill in
  one by one on their spoken onsets**, each with a quick blur-in that slides in from the reading direction.
- Text is dark green (#17443a). Here it uses Devin's heavy font (Cairo Black for Arabic, Montserrat Black
  uppercase for Latin) at ~54 px.
- **Keyword = maroon box** (#7c1528) that **wipes in** behind the word while its text turns white, with a
  soft maroon glow (the Devin touch). Use it on ~1 pill in 4: product names, numbers, the punch word.
- He writes Darija in Arabic script and keeps tech words in Latin ("الـ AI", "skill", "feature").

## 3. Headlines (top of frame)
- They sit above the head (y≈150–330). Every word **blurs in on its spoken onset**, building the line as
  he talks.
- Paper: dark-green text. Green: cream text. Footage (hook): white Devin type with a white glow, and
  the keyword in a **neon colour glow** (Devin) or a maroon box.
- The hook is two stacked lines with big type (~110 px): a Latin line plus an Arabic line, and a slow
  1.06 → 1 settle.
- Key phrases get the maroon box with a left→right (or right→left for RTL) wipe.

## 4. Card vocabulary
- **Screenshot / browser window**: a light glass frame with traffic-light dots and the URL, and a dark
  page inside. It drops in from above with a blur (expo.out). Key lines get a **red outline box drawn
  around them**, and a **maroon label chip** pops under the bottom-left corner ("REA", "#1 Trending").
- **Terminal** (Claude Code-style): the prompt types in letter by letter, then the response lines fade up.
- **Glass stat card**: a big number **counting up** ($20,585 → $45,000), with a tiny grey caption under it.
- **Chips**: small glass pills ("AI agent", "feature") popping in one by one with back.out.
- **Tag**: a tiny maroon pill with an icon next to the face ("i-have-adhd", "1 YEAR FREE").
- **People grid**: rows of round person icons that pop in. A share turns maroon ("most people…").
- **Icon arc**: glass app tiles sweeping along a big arc. One gets a red outline when named.
- **List card**: a glass card whose rows tick in with check circles.
- (In the refs but not templated: a folder with photos sliding out, a perks wall of app cards scrolling.
  Build these in `edit/extra.html` when the script needs them.)

## 5. Sound
Soft and airy: a short whoosh on scene changes, pops on chips, tags and labels, typing on the terminal,
a soft whoosh + pop on keyword words, and an optional very quiet tick per word. The voice stays on top.

## 6. Structure
Hook on full footage (big two-line title + tag) → paper explanation with proof card → back to footage for
a personal line → green for tools / numbers → paper → … → final line + payoff visual. No logo sting.
