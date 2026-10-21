---
name: offer-ad
description: "A 10-20 s offer / sale ad built to convert: the deal in the first second, what you get, a big price card (old price struck, new price), urgency (countdown, stock, deadline) and a pulsing CTA button. Bold blocks of colour, stamps and bursts, fast punch-ins. Works on a selling clip or without footage. Use for promotions, discounts, Black Friday, \"price ad\", \"offer\", e-commerce products."
---

# offer-ad

The deal is the hook. Say it immediately, make it look valuable, give a reason to act now.
Build it as one HyperFrames composition.

## Structure (15 s; scale for 10-20 s)

| Beat | Time | Content |
|---|---|---|
| Deal hook | 0-2 s | The offer as the first frame: "-40%", "2 for 1", "Free delivery", in a burst or stamp shape. |
| What you get | 2-8 s | The product(s): 2-3 benefit chips or product cards ("Pure cotton", "Sizes S-XXL"). With a speaker, the chips appear on their words. |
| Price card | 8-11 s | Old price struck through, new price huge, currency correct (DT, EUR, $...). |
| Urgency | 11-13 s | A real reason: deadline date, countdown, "Only 20 left", "This weekend". Only what the user gave; never invent scarcity. |
| CTA | last 2 s | Button card ("Order now", "Shop the link", "DM to order") pulsing, plus logo/handle if given. |

## Look

- Strong colour blocks: brand kit colours if given (first = the deal colour). Otherwise a
  high-contrast pair: red #E5322D or orange #FF5A1F with off-white, or yellow #FFD60A with black.
- Deal shapes: starburst (12-16 points), rotated stamp with a rough edge, ribbon banner.
- Price: new price 200-260 px, heaviest weight; old price 80 px, 60% opacity, struck by a line
  that draws across (0.3 s).
- Captions (with footage): bold, 2-3 words, white with a dark box; keyword (price, product) in the
  deal colour. Safe zone: avoid the top 250 px and bottom 320 px.

## Motion

- Deal hook: stamp slams in (scale 2.2 -> 1, rotate -14deg -> -8deg, 0.22 s) with a 10 px shake
  and a flash.
- Chips: pop in with back.out(1.8), 0.08 s stagger, on the words.
- Price: old price in, line strikes, new price counts down from the old value (0.5 s) and lands
  with a bounce.
- Punch-ins on the speaker (1.0 -> 1.15) on the deal and the price lines.
- CTA: button scales in, then pulses (1 -> 1.05, 0.5 s yoyo) with a tap dot.

## Sound

Hit + cash/coin sound on the deal, pops on chips, a "ding" on the new price, a ticking under the
countdown, a final hit on the CTA.

## Check

The offer is visible in the first second; the price is correct and in the right currency; urgency
is only what the user said; one CTA; text inside the safe zone.
