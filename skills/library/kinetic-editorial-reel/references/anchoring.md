# Anchoring — measuring assets so motion lands exactly

`prep_assets.py` gives size, alpha bbox and alpha-weighted centre for every image — enough to
place most heroes. Semantic points need real measurement: a clock's pivot, a rubber stamp's
contact face, a pin's needle tip, a phone screen's 4 corners, a badge spot on an icon, the empty
area of a document where a mark goes, the neck point of a headless figure. Eyeballed values
produce visible misses (a prop landing beside its target); measured anchors fix that.

## Delegate to a subagent (in parallel with SFX generation)

Spawn a general-purpose subagent in the background with a prompt shaped like this — list only
the assets and anchors THIS storyboard needs:

```
Measure precise pixel anchor points on PNG images and write them to JSON. Do NOT modify images
or HTML. Tools: python3 (Pillow, numpy, scipy). View images with the Read tool — make zoomed
crops with grid overlays + labels to verify every measurement visually; don't guess.
Image dir: <project>/assets/img/
Scratch dir: <scratchpad>/anchors/
Output: <project>/assets/anchors.json — {"<file>": {"size":[w,h], "bbox":[...], <named anchors>, "notes":"..."}}
All coordinates in ORIGINAL image pixels.
Measure:
1. <file> — <anchor name>: <what it is and what it's used for>
   e.g. clock.png — dial centre + radius: fit a circle to the tick marks; hands rotate around it
   e.g. stamp.png — contact-face centre + width: the prop must land on a target point
   e.g. phone.png — 4 screen-glass corners TL,TR,BR,BL as if upright, via edge-line
        intersections; used for a perspective UI overlay
...
Before finishing, render verification sheets with every anchor drawn on its image, look at them,
and report the anchors + any uncertainty.
```

## Using anchors in layout (image px → composition px)

For an `<img>` of display size `D` (square source of size `S`, placed at `left, top`):
`k = D / S`; image point → `(left + x·k, top + y·k)`.

To land point P of a prop on target T when the prop is rotated `θ` about its box centre C:
```
off  = (P − C_img) · k                                        # offset from box centre, unrotated
off' = (off.x·cosθ − off.y·sinθ, off.x·sinθ + off.y·cosθ)     # CSS rotation (y down), θ in radians
box_centre = T − off'
left = box_centre.x − D/2 ;  top = box_centre.y − D/2
```
If the TARGET sits inside a rotated/scaled parent, transform the target point the same way
first. Put small attached parts (a pin on a card) INSIDE the parent so they inherit its motion.

Screen quads: scale the 4 corners by the displayed image scale, then `quadMatrix()`
(composition-kit §6); give the overlay a `border-radius` ≈ the screen's corner radius.
