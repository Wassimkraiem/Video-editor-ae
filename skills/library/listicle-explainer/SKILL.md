---
name: listicle-explainer
description: "A numbered explainer reel: \"3 reasons\", \"5 tips\", \"4 mistakes\". A curiosity hook, then each point as a big number + a short title + one visual that illustrates it, a progress bar showing how far along we are, and a recap/CTA. Works over a talking head or fully designed. 20-60 s. Use for tips, tutorials, educational content, \"top 5\", \"reasons why\", carousels turned into video."
---

# listicle-explainer

Structure keeps people watching: they want to see number 3. Build it as one HyperFrames composition.

## Structure

1. **Hook (0-3 s):** the promise with the count ("3 AI tools that replace your designer", "Stop
   doing these 4 things"). The count is the biggest element.
2. **Points:** for each point, in order:
   - number badge big ("01", "02"...) + a 2-5 word title (1-1.5 s, on the words that introduce it);
   - one visual that illustrates it while the speaker explains (icon set, UI card, mini chart,
     comparison, logo of the tool they name, a photo the user attached);
   - optional one-line takeaway before moving on.
3. **Recap (2-3 s):** all titles as a checklist ticking in.
4. **CTA (last 2 s):** "Save this", "Follow for part 2", "Comment GUIDE", or the user's CTA.

With a transcript, detect the points from what is said ("first", "number two", "the last one");
if the speaker never counts, split by topic and still number them.

## Look

- Number badge: 180-240 px, heavy, in the accent colour (brand kit first colour), with a thin
  outline duplicate offset behind it for depth.
- Titles: 72-96 px bold, max 2 lines.
- Progress bar: a thin bar (8 px) at y 270 px across the width with N segments; the current
  segment fills during its point.
- Over footage: speaker full frame; titles and visuals in the upper half (y 300-900); captions in
  the lower third. Without footage: alternate background colours per point.

## Motion

- Point change: the number flips (rotateX 90 -> 0, 0.35 s) or the old number slides out up while
  the new one slides in from below; the progress segment starts filling.
- Visuals: pop in on the word they illustrate (scale 0.8 -> 1, back.out), leave before the next
  number.
- Recap checklist: lines stagger in 0.1 s apart, each check draws on.
- Punch-in on the speaker at each new number (1.0 -> 1.08).

## Sound

A light rhythmic bed; a "tick" or "pop" on each new number, whooshes on visuals, a satisfying
chime on the recap.

## Check

The count is in the hook and matches the points; every point has a number, a title and a visual;
the progress bar advances; recap and one CTA at the end.
