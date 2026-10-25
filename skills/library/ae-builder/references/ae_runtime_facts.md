# After Effects + ExtendScript runtime facts

Every row here broke (or nearly broke) a real build. A Node dry-run that is more forgiving than After Effects
proves nothing, so `scripts/ae_mock_dryrun.js` emulates each of these. When a user reports a new AE error,
add the rule to the mock FIRST, reproduce their exact summary numbers, then fix the script.

## 1. ExtendScript is ES3

| Fact | What happened | Rule |
|---|---|---|
| Reserved words are illegal as property names and object keys (`char`, `int`, `class`, `default`, `final`, `short`, `long`, `byte`, `float`, `double`, `goto`, `native`, `package`, `public`, `static`, `super`, `enum`, `export`, `import`, `interface`, `synchronized`, `throws`, `transient`, `volatile`...) | `COL = { char: "#3A3D47" }` stopped the script on line 19: "Illegal use of reserved word". Node accepted it. | Never use them, not even quoted-key style. The mock lints for it. |
| No `let`, `const`, arrow functions, template strings, `forEach/map/filter/reduce/some/every`, `Array.isArray`, `Object.keys`, `JSON`, `String.trim`, `Array.prototype.indexOf` | (prevented) | Plain `for` loops and `var`. Strings have `indexOf`, arrays do not. |
| Trailing commas in object/array literals are syntax errors or add `undefined` | (prevented) | Lint. |
| `e.line` gives the real script line of the error | Used to pinpoint every failure | Always include it in the report. |

## 2. Properties and handles

| Fact | What happened | Rule |
|---|---|---|
| `property("Name")` returns **null** when the name/matchName doesn't exist. No error. | Used `"ADBE Mask Expansion"`; it returned null; the keyframe call later threw "null is not an object" on an unrelated line and MAIN failed. | Go through `prop(parent, name)` which throws a clear error naming the missing property. Use only verified matchNames (table below). |
| Adding or moving a child in an **indexed group** (shape Contents, Effects, Masks, text Animators/Selectors/Properties) invalidates handles to that group's **other** children. | Background builder created `Blob_Dark` and `Blob_Light` groups, then drew into `Blob_Dark`: "Object is invalid", 6 of 8 scenes failed. | Finish one group completely before creating the next. Never keep a handle across an `addProperty`/`moveTo` on its parent; re-fetch by name or index. |
| Shape **Contents: the first item is drawn in front.** | Nodes would hide their white centre; the hand would paint back-to-front. | `grp()` moves each new group to index 1 and re-fetches it, so code order = paint order. |
| Ease array length must match the property: 1 for spatial, 1D, colour and shape; otherwise `value.length`. 2D-layer Scale can want 2 or 3 depending on version. | Suspected crash on Scale keys. | `setEaseSafe()` tries the expected count, then 1/2/3, then logs. |
| **Hold-only properties**: Checkbox, Dropdown Menu, Layer control, Source Text. Bezier is rejected: "Invalid interpolation type for this property". | Keyed the "Auto Edit On" checkbox with a bezier ease: S1 failed. | Ask `prop.isInterpolationTypeValid(BEZIER)` first; use HOLD keys when false. |
| `setParentWithJump(p)` keeps the child's numbers and reads them in the parent's space. (`child.parent = p` compensates instead.) | Labels parented to shape layers landed offset by the parent's position. | Parent to nulls built with anchor = position (then parent space = comp space). If you must parent to a shape layer, set the child's position in the parent's space after parenting. |
| Expression Selector **Amount** returns 3 values | (prevented) | Return `[a, a, a]`. |
| Shape fill/stroke colours want `[r, g, b, a]`; text `fillColor` wants `[r, g, b]` | (prevented) | `rgba()` for shapes, `rgb()` for text. |
| Drop Shadow opacity range differs (0-255 vs %) across versions | (prevented) | `try` 255, fall back to 100. |
| Two keys snapped onto the same frame by float rounding (`13.35 - 11.81 = 1.5399999`) | 3 opacity keys collided | Snap with `Math.round(t * fps + 1e-6)`, keep keys at least one frame apart. The fitter enforces it. |

## 3. Verified matchNames

Layer: `ADBE Transform Group` > `ADBE Anchor Point`, `ADBE Position`, `ADBE Position_0/_1/_2` (separated), `ADBE Scale`, `ADBE Rotate Z`, `ADBE Opacity`.
Masks: `ADBE Mask Parade` > `ADBE Mask Atom` > `ADBE Mask Shape`, `ADBE Mask Feather`, `ADBE Mask Opacity`, **`ADBE Mask Offset` (= Mask Expansion)**. In expressions it is `mask("Name").maskExpansion`.
Shapes: `ADBE Root Vectors Group` > `ADBE Vector Group` > `ADBE Vectors Group` / `ADBE Vector Transform Group` (`ADBE Vector Position`, `ADBE Vector Rotation`, `ADBE Vector Scale`, `ADBE Vector Anchor`, `ADBE Vector Group Opacity`).
`ADBE Vector Shape - Rect` (`ADBE Vector Rect Size`, `ADBE Vector Rect Position`, `ADBE Vector Rect Roundness`), `ADBE Vector Shape - Ellipse` (`ADBE Vector Ellipse Size`, `ADBE Vector Ellipse Position`), `ADBE Vector Shape - Group` > `ADBE Vector Shape`.
`ADBE Vector Graphic - Fill` (`ADBE Vector Fill Color`, `ADBE Vector Fill Opacity`, `ADBE Vector Fill Rule` 1 = non-zero, 2 = even-odd), `ADBE Vector Graphic - Stroke` (`ADBE Vector Stroke Color`, `ADBE Vector Stroke Width`, `ADBE Vector Stroke Opacity`, `ADBE Vector Stroke Line Cap` 1 butt / 2 round / 3 square, `ADBE Vector Stroke Line Join`, `ADBE Vector Stroke Dashes` > `ADBE Vector Stroke Dash 1` / `ADBE Vector Stroke Gap 1`), `ADBE Vector Filter - Trim` (`ADBE Vector Trim Start`, `End`, `Offset`).
Text: `ADBE Text Properties` > `ADBE Text Document`, `ADBE Text Animators` > `ADBE Text Animator` > `ADBE Text Animator Properties` (`ADBE Text Position 3D`, `ADBE Text Scale 3D`, `ADBE Text Opacity`, `ADBE Text Rotation`) and `ADBE Text Selectors` > `ADBE Text Expressible Selector` > `ADBE Text Expressible Amount`.
Effects: `ADBE Slider Control`, `ADBE Checkbox Control`, `ADBE Point Control`, `ADBE Layer Control`, `ADBE Angle Control`, `ADBE Color Control`, `ADBE Dropdown Control`, `ADBE Drop Shadow`, `ADBE Gaussian Blur 2`, `ADBE Ramp`, `ADBE Glo2`, `ADBE Linear Wipe`. Marker: `ADBE Marker`.
Anything not on this list: check it exists in a real AE before relying on it, and add it to the mock's whitelist.

## 4. Build-time behaviour

- One crash used to kill everything after it. Build every comp inside `safe()`; MAIN builds with whatever exists.
- The summary used to bury the real error under 25 "missing asset" notes. Report ERRORS first, NOTES after, and write the full log to the Desktop.
- `$.fileName` is the only reliable way to find files next to the script. If the marker file isn't there, say so and `Folder.selectDialog()`. Never silently continue with missing assets.
- Text with a font the machine doesn't have silently substitutes. Check `app.fonts.getFontsByPostScriptName(name)` (AE 24+) before building and open the bundled `fonts` folder if anything is missing.
- Users re-running into an existing project get duplicate folders: tell them to run in a new project.

## 5. Sandbox facts (the environment Claude builds in)

- The sandbox can reset mid-project and wipe `/home/claude`. Network access can also disappear. Keep the generator source, assets and font files in the persistent outputs folder as soon as they exist, and fetch fonts at the start, not at hand-off.
- A blocked download often "succeeds" with a 100-byte text page saved under the font's file name. Check font magic bytes (`fetch_fonts.py` does).
