---
name: "ae-builder"
description: "Use to turn an animation (code, MP4, storyboard or HTML/canvas) into an After Effects ExtendScript that rebuilds it as a clean, hand-editable project: rigs, keyframes fitted to match the source easing exactly, slider-driven expressions a non-coder can steer, and a delivery zip that already contains the fonts and assets. Also use when a user reports an error from running a rebuild script, or says the rebuilt easing doesn't match the original."
---

# AE Rebuilder

Goal: write one `.jsx` script that rebuilds an existing animation inside After Effects as a project a human motion designer can open cold and understand in five minutes, and that **moves exactly like the source**.

Two north stars, both mandatory:
1. *An intermediate motion designer who is not a coder opens this project. Can they find things, understand the rig, retime it, and change every behaviour from keyframes and named controls, without reading code?*
2. *Played side by side with the source MP4, does every move hit the same frames with the same curve?* Measured, not eyeballed (section 7).

The second one was missed badly on a real job (pops 70% off, see `references/postmortem_coh_rebuild.md`). Read that file once before your first build; it is the reason most rules below exist.

---

## 0. Before writing anything

**Persist first.** The sandbox can reset mid-project and wipe `/home/claude`, and network access can disappear. From the first minute, keep the generator source, exported assets and fonts inside the persistent outputs folder (e.g. `/mnt/user-data/outputs/<project>_ae/`), and fetch fonts now, not at hand-off (section 13).

Ask in one round (AskUserQuestion, up to 4 questions), skipping anything already known from the conversation:
1. **Aspect ratio + resolution** of the main comps.
2. **Frame rate** (default: match the source).
3. **AE version** (default AE 2023+, JavaScript expression engine; the script still feature-detects).
4. **Footage**: should the script ask for the A-roll/source file when it runs (default), or leave placeholders.

Do NOT ask the user for fonts or assets: the deliverable includes them (section 13). Only ask if a font is commercial and can't be bundled, and say so at the start.

Comp size rules:
- MAIN and every SCENE comp use exactly the chosen resolution, fps and pixel aspect 1.0.
- Only convenience precomps (`PRE_...`) may differ, with the reason in the comp comment (a wide background that spins, a character that runs off-screen).
- If the source is 16:9 and they ask for 9:16, re-lay out; never just scale.

---

## 1. Read the source properly

- **Timing comes from the source itself.** With the generating code, read the exact function, start time and length of every move, per channel. With only an MP4, extract frames and track each element's channels (position, scale, rotation, opacity) into sampled curves.
- Build a **beat sheet**: per element, per channel: `start, length, from, to, curve` where `curve` is the actual function (e.g. `1 - e^(-5u) cos(8u)`) or a sampled channel. "easeOut" is not a curve; the formula is.
- Tag each row's **kind**: `move` (it decides to move), `reaction` (it moves because something else did: write the cause), `repeat` (same move on many elements with an offset), `loop` (endless/procedural).
- List every **clip** (what is clipped, to what shape, what the clip shape moves with).
- Note **motion blur** in the source (sub-frames blended, shutter), because AE must match it (section 7.5).
- VO beats become comp markers. If you have the audio, measure the word onsets (loudness envelope, syllable bursts); never guess them.

---

## 2. Project structure

```
<Project>/
  00_MAIN          MAIN_<ProjectName>
  01_SCENES        S1_<ShortDescription>, S2_..., (one comp per scene/beat)
  02_RIGS          RIG_<CharacterName>
  03_PRECOMPS      PRE_<Thing>
  04_SOLIDS
  05_REFERENCE     source MP4 / A-roll (guide layers), imported assets
```
- MAIN = scene comps end to end, plus a disabled `DIALOGUE_MARKERS` null (one marker per spoken beat) and the audio as a layer.
- Each scene comp holds only its scene, with its own camera null. Shared characters live in one rig/precomp, placed with `startTime` offsets.
- `comp.comment` on every comp: what it is, which VO line, where it starts in MAIN.
- Naming: `CTRL_` controls, `CAM_` cameras, `RIG_`/`BONE_` rig internals, `MATTE_` mattes, `FX_` effects layers, `GUIDE_` guides, `GRP_` group nulls, descriptive art names. `_L`/`_R` from the character's view.
- Labels: Red (1) controls, Purple (10) expression-driven, Aqua (3) mattes, Yellow (2) guides, Sandstone (15) art.

---

## 3. Shape layer rules

- **One shape per shape layer by default.** Several shapes share a layer only if they never animate independently, never need their own matte, are one visual unit, and their stacking is correct.
- Split into separate layers when the part animates, needs a matte, its own effect/blend/motion blur, or sits between other things.
- **Contents order: the first item is drawn in front.** Use `grp()` from the library (it moves each new group to the top), so code order = paint order.
- **Build one group completely before creating the next.** Adding a group invalidates handles to its siblings ("Object is invalid").
- Anchor points at natural pivots (shoulder, base of a bubble, bottom-centre of a character, the tip of a cursor).

---

## 4. Clipping: masks, track mattes, preserve transparency

| Need | Use |
|---|---|
| Clip one layer to a simple shape | Layer mask |
| Simple wipe / line draw | Linear/Radial Wipe or Trim Paths, keyed |
| Clip to another layer's shape, or the clip animates on its own | Track matte (alpha) |
| Many layers to the same shape | AE 2023+: one shared matte; older: precomp and matte once |
| Details painted inside a base shape (grain, stripes) | Small `PRE_` comp with only base + details, details with Preserve Transparency (T), or alpha-matte to the base |
| Cut a hole | Alpha Inverted |
| A person in front of graphics (no plugin) | Ship a matte sequence (luma), and say Roto Brush gives a cleaner edge |

Matte rules: same comp as the target; parent the matte to what the clip should follow and say so in its comment; dedicated `MATTE_` layers have video off; matte filled at 100%; matte in/out covers the target; same 2D/3D; no matte chains; apply mattes in a final pass after stacking is final (`finishComp` does this). Run `checkMattes()` and report anything it finds.

---

## 5. Characters

- Simple moves (pop, slide, fade, bob, fall and land): no rig; animate the layer or a parent null.
- Complex moves (walks, reaching limbs, jumps, gestures): IK rig in `RIG_<n>`, animate controllers only (`CTRL_<n>_Master`, `CTRL_Body`, `CTRL_Head`, hand/foot controllers), with Flip/IK/Idle controls on the master. Two-bone IK: bones drawn pointing down, lengths measured by the script, upper and lower bone rotation expressions driven by the hand/foot controller and a Flip checkbox. Verify reach with `probe()`.
- Lock and shy bones and art; controllers stay red and unlocked. Never shy a matte.
- A user's own character art (SVG/logo) is used as provided: convert to shape paths, keep shape and colour, add style treatments as separate layers (extrusion, grain), never redraw it.

---

## 6. Keyframes or expression?

Ask in order:
1. **Does it decide to move, or react?** `move` = keys. `reaction` = expression that reads its cause.
2. **If the cause is retimed, how many keys must be moved by hand?** None: keys. Some: expression.
3. **Same move on many layers?** Key one leader (fitted curve), followers copy it with a delay.
4. **Endless/procedural?** Expression, scaled and switched by controls.
5. **One-off move whose curve is the creative choice?** Keys. Always.

**The timing curve always lives in keyframes**, even for reactions: a reaction system is driven by a keyed slider (e.g. `Progress (%)` on `CTRL_Burst_X`) whose keys carry the ease, and the expression maps it linearly. The designer then changes the feel in the graph editor, like any other animation. Hidden easing maths inside an expression is not allowed (section 8).

---

## 7. Keyframes that move exactly like the source

Read `references/easing_translation.md` once; it has the measured failure, the maths and the preset table.

### 7.1 The rule
Every move's keys must match the source curve within **2% of the move at every frame and 4 sub-frames per frame**, and within **1 frame** of timing. Verified by `scripts/verify_curves.py`. A guessed ease (speed 3x, influence 33) is not acceptable unless the fitter produced it.

### 7.2 The traps that caused a 70% error
- A spring's "duration" is its settling window: it crosses the target at ~20% of it and spends the rest overshooting. **Never** put keys at the start and end of a spring's nominal duration.
- **Never** fake overshoot with a generic bounce/inertia expression on top of keys. Overshoot = real keys at the peak and the dip, so it's visible and draggable.
- **Never** guess speeds and influences.
- **Never** skip motion blur when the source has it.

### 7.3 How (generator side, Python)
```python
from ease_fit import fit_move, fit_samples          # scripts/ease_fit.py
spring = lambda u: 1 - math.exp(-5*u) * math.cos(8*u)
keys, err = fit_move(spring, t0=6.04, dur=0.70, fps=25)   # frame-aware: keys on whole frames,
assert err <= 0.02                                         # turning points become keys, influences searched
FITS["band_1_pop"] = keys                                  # [[t, fraction, speed, inflIn, inflOut], ...]
```
- One `fit_move` per move per distinct curve. Channels of one entrance (scale, y, rotation) each get their own fit but share start/end frames.
- Blended or odd channels (camera punch x drift, squash chains, anything not a textbook ease, tracked MP4 data): sample the channel from the code and use `fit_samples(times, values)`.
- In-out expo may stay at 2 keys (89.5/89.5, 3.4%) because it reads better in the graph editor; everything else must pass 2%.

### 7.4 Apply (script side)
`applyFit(layer, "scale", FITS.band_1_pop, [0, 0], [100, 100])` sets values, bezier, speeds (scaled by the move size per dimension, magnitude for spatial) and influences; hold-only properties automatically get hold keys. Positions that animate are separated (`sep(L)`) so X and Y each get a clean graph.

### 7.5 Motion blur
If the source blends sub-frames (most code renders with motion blur do), call `matchMotionBlur(comp)` (shutter angle = source shutter, phase = -angle/2, 16 samples) on every comp and `blur(layer)` on every moving layer. Without it AE looks harsher than the MP4 even with perfect keys.

### 7.6 Verify (mandatory before delivery)
```
DUMP_KEYS=keys.json node scripts/ae_mock_dryrun.js Build.jsx
python3 scripts/verify_curves.py keys.json checks.json      # exit 1 = do not deliver
```
`checks.json` lists at least one move per distinct curve, every gravity/impact move, every move under 0.3 s, and every reaction driver. Report the worst error in the hand-off.

---

## 8. Expressions a non-coder can drive

The user may understand only basic expressions. They must be able to change **everything an expression does** from Effect Controls and keyframes, without reading code.

### 8.1 Rules
- **Every behaviour is a named control.** Amounts, distances, delays, speeds, directions, sizes, spin, drift, on/off, seeds: each a slider/checkbox/point/angle/layer control with a plain name and unit (`Distance (%)`, `Stagger (frames)`, `Drift Speed`, `Float (px)`). If you can describe something the expression does in a sentence, that sentence needs a control.
- **No hidden easing.** No `Math.pow(1 - p, 3)`, `1 - Math.exp(-5 * p) * Math.cos(8 * p)`, `ease()`/`linear()` over time, or any other curve applied to progress inside code. The curve lives in keyframes on a driver slider; the expression reads it linearly. (`p` may overshoot past 1 because the driver keys overshoot; that's how a fitted spring reaches the particles.)
- **Nothing moves on its own without a control.** Any expression using `time` with sin/cos/wiggle must read its amount and speed from controls, with 0 = off.
- **Header on every expression:** line 1 = `// WHAT it does. Controls: CTRL_X > A, B, C. This layer: D.` The designer reads only this line.
- **One home per system:** `CTRL_<System>` null at the top of the comp, red label. Per-layer controls only for values that differ per layer (`Order`, a particle's home position).
- **Defaults reproduce the source.** The driver keys are the fitted source curve; sliders default to the source amounts.
- Build on `value` so the property stays keyable; fully driven layers are labelled purple and say so.
- Same behaviour on many layers = identical expression text; differences come from controls.
- Reference controls by name, layers via Layer controls, never by building names from strings.
- **Escape hatch**, in every README: "Want plain keys instead? Select the property > Animation > Keyframe Assistant > Convert Expression to Keyframes."

### 8.2 Systems library (in `assets/ae_build_lib.jsx`)
| System | Driver (keys = the ease) | Controls | Per layer |
|---|---|---|---|
| `makeBurst` + `addToBurst` (impact particles, confetti) | `Progress (%)` on `CTRL_Burst_<n>`, fitted from the source | Origin, Distance (%), Size (%), Spin (deg), Stagger (frames), Drift (px), Drift Speed | Order; home position = where the particle ends up |
| `staggerExpr` (cascades) | The Leader's own fitted keys | Leader, Delay (frames) | Order |
| `floatExpr` (idle bob) | none (loop) | Float (px), Float Speed | |
| Letter cascades | `Drop In (%)` slider keyed with a fitted curve, Text Animator + Expression Selector mapping it per letter (linear, no spring maths) | Letter Delay (frames); start pose on the animator | |
| Wipes | Mask Expansion keys (`maskExpansion()` helper, matchName `ADBE Mask Offset`) | Ring Thickness (%) | |

The mock dry-run flags hidden easing, uncontrolled time-based motion and missing headers. Treat those flags as errors.

---

## 9. Cameras and parallax

- One camera rig per scene comp: a `CAM_` null at the focus (anchor = position) with keyed Scale/Position from fitted curves; world layers parent to it. Drift = an expression with a `Cam Drift (px)` control, 0 = off. No camera shake unless the source has it; if it does, a `Shake Amount` control.
- Parallax layers follow the camera through linked nulls with a `Parallax (%)` control.
- Big world plates as precomps get Collapse Transformations.

---

## 10. Other AE craft rules

- Motion blur matched to the source (7.5).
- Glows as separate layers; soft radial glows with Gradient Ramp or feathered masks.
- Text is real text layers in the real fonts (bundled, section 13). Lay out with `sourceRectAtTime` so the script measures the real font, never hard-coded widths.
- Grain/texture from code renders: export the textures as PNGs from the same code and lock them to their shapes (matte or T switch) so grain never boils.
- Trim layer in/out points to visibility. Mattes trimmed with their targets.
- Do not reproduce third-party logos or copyrighted characters; a user's own assets are fine.

---

## 11. Script engineering

### 11.1 Shape of the deliverable script
One self-contained `.jsx` = `assets/ae_build_lib.jsx` (pasted in) + `CURVES`/`FITS` data + project data + build functions. Generated by a Python/Node generator that also runs the fits. Keep the generator in the persistent outputs folder.

### 11.2 ExtendScript is ES3
No `let/const`, arrow functions, template strings, `forEach/map/filter/reduce`, `Array.isArray`, `Object.keys`, `JSON`, `Array.prototype.indexOf`, trailing commas. **No reserved word as a property or key**: `char int class default final short long byte float double goto native package public private protected static super enum export import interface synchronized throws transient volatile`. (`COL.char` once stopped a build on line 19.)

### 11.3 AE runtime facts (details: `references/ae_runtime_facts.md`)
- `property(name)` returns **null** for unknown names: always use `prop()`. Mask Expansion is `"ADBE Mask Offset"`.
- Adding/moving a child in an indexed group kills sibling handles: finish one group before the next, re-fetch after `moveTo`.
- Hold-only properties (checkbox, dropdown, layer control, source text): check `isInterpolationTypeValid` (`applyFit` does).
- Ease array lengths vary (Scale 2 vs 3): `setEaseSafe`.
- `setParentWithJump` doesn't compensate: parent to nulls with anchor = position.
- Key times: `fr()` with epsilon; never two keys in a frame.

### 11.4 Build order per comp
1. Per layer: create, name, parent, add controls, build contents (one group at a time), set transforms, set keys (`applyFit`).
2. `finishComp(c)`: controls/cameras/guides to the top, mattes, layer-control values, expressions last (reading `expressionError`), matte check.
3. Every comp built inside `safe(name, fn)`; MAIN built from whatever exists.
4. `report(title, total)`: "Built N of M comps", ERRORS first, notes counted, full log written to the Desktop.

### 11.5 Testing gate (all mandatory before the first hand-off)
1. `node scripts/ae_mock_dryrun.js Build.jsx` = NO ISSUES. The mock is strict: ES3 lint, null on unknown matchNames, stale sibling handles, hold-only properties, ease counts, key collisions, expression compile + references, hidden easing, uncontrolled motion, headers.
2. Stress modes, each must still build every comp: `SCALE2=1` (AE wants 2 Scale eases), `ELSEWHERE=1` (script run away from its files: must prompt), `BREAK="<matchName>"` (adding that property throws, e.g. `BREAK="ADBE Mask Atom"`: the other comps and MAIN must still build and the error must be listed first).
3. Curve verification (7.6).
4. Start new projects from `assets/smoke_test.jsx` as the pattern; it passes all of the above.

The mock is not After Effects. Say "verified in a strict mock, not yet run in AE" in the hand-off.

### 11.6 When the user reports an AE error
1. Read the line number and message (ask for the summary screenshot or the Desktop log if not given).
2. Find the exact cause on that line. Check the whole script for the same pattern.
3. **Add the rule to the mock.** Run the old script: the mock must reproduce the user's summary numbers (comps built, layers, keys, expressions). If it doesn't, the mock is still wrong.
4. Fix, re-run the gate, add a row to `references/ae_runtime_facts.md`.
5. Tell the user plainly what broke and why, then give the new zip.

---

## 12. Make it obvious for a first-time human

- `GUIDE_READ_ME` guide layer in MAIN and every comp with expressions or mattes: structure, what each CTRL does, label legend, one line per expression system ("Particles: change their ease on CTRL_Burst_Impact > Progress (%) keys in the graph editor; how far = Distance (%)"), matte map, marker formats, the convert-to-keys escape hatch.
- Each README has a **"How to change..."** list in plain words: "...how far the particles fly: CTRL_Burst_X > Distance (%)", "...when the title lands: drag the two Drop In (%) keys on CTRL_Type".
- Controllers are the only unlocked red layers in a rig; mattes aqua and never shy.
- Markers name the beats ("LAND", "click", VO words).
- Prefer a slightly less clever structure a person can follow.

---

## 13. Delivery package and hand-off

### 13.1 The zip (everything the script needs; the user never has to ask)
```
<project>_ae/
  <Project>_Rebuild.jsx      the single build script
  README.txt                 how to run, font install, what to send if something fails
  assets/                    textures, images, SVG-derived data, exported PNGs
  fonts/                     every font file the text layers use + licence files
  matte_*/                   matte sequences (people cut-outs etc.), if any
```
- **Fonts**: run `python3 scripts/fetch_fonts.py <outdir>/fonts "Family:Style,Style" ...` at project start. It downloads open-licence fonts (Google Fonts / Fontsource) with licences, rejects fake files from blocked networks, prints PostScript names (use exactly those in the script; prefer static instances over variable fonts). Commercial fonts are never bundled: tell the user at the start with the download link.
- If fonts can't be fetched (no network), say so **at the start of the project**, give the direct links, and offer to bundle them once network is enabled. Never discover it at hand-off.
- The script calls `checkFonts([...], root)` before building: lists missing fonts, opens the bundled `fonts` folder, and keeps building.
- The script finds its folder with `findProjectFolder("assets/<marker>")` and asks for it if needed.

### 13.2 Hand-off message (plain, short)
- How to run: new project, unzip, File > Scripts > Run Script File, pick the footage when asked. Install fonts from `fonts/` first if the script says so.
- What success looks like: "Built N of N comps. No errors." And what to send if not: the summary screenshot or the Desktop log.
- Comp/folder map; which controllers to grab.
- Keys vs expressions, and for each expression system the one place to tune it (including where its ease lives).
- Clips: mattes vs masks vs T switch.
- Easing fidelity: "every move fitted to the original, worst error X% of a move".
- Known gaps (approximations, anything not verified in real AE) and a confidence rating.

---

## Bundled resources

- `assets/ae_build_lib.jsx`: the helper library (safe properties, handle-safe shapes, `applyFit`/`applyCurve`, hold-key handling, controllable systems, fonts, assets, mattes, `finishComp`, `safe`, `report`). Paste into every build script.
- `assets/curves.jsx`: normalised fitted presets (`CURVES`), for quick previews; real moves use `FITS` from `fit_move`.
- `assets/smoke_test.jsx`: a minimal build using every helper; passes the full gate. Template for new projects.
- `scripts/ease_fit.py`: `fit_move` (frame-aware, per move), `fit_samples` (any sampled channel), `fit_keys`, presets table.
- `scripts/ae_mock_dryrun.js`: strict AE mock + ES3 lint + usability lint + `DUMP_KEYS` for curve checks.
- `scripts/verify_curves.py`: compares written keys against the source curves; exit 1 above 2%.
- `scripts/fetch_fonts.py`: bundles open-licence fonts with licences and PostScript names.
- `references/easing_translation.md`, `references/ae_runtime_facts.md`, `references/postmortem_coh_rebuild.md`.
