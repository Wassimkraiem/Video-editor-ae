# Postmortem: the COH "Claude Opus 5.5 auto-edit" rebuild

A 23 s reel (8 scenes, 403 layers, 478 expressions) was rebuilt as an AE project. It took five rounds of the user
running the script and sending screenshots before it built. Then the user found the easing wrong, the particles
uncontrollable, and the fonts missing. Each problem, why it happened, and what prevents it now.

| # | What the user saw | Root cause | Prevention now |
|---|---|---|---|
| 1 | "Illegal use of reserved word" on line 19 | `char` used as an object key. ES3 forbids it; the Node dry-run (modern JS) accepted it. | ES3 reserved-word lint in the mock; reserved list in SKILL section 11. |
| 2 | Assets "missing", no prompt | Assets resolved only next to `$.fileName`; no check, no fallback. Missing files were notes, not errors. | `findProjectFolder()` verifies a marker file and asks for the folder; missing files are listed. |
| 3 | No MAIN comp, "ran successfully" | The real crash message was line 26 of a list truncated to 25 lines (missing-asset notes came first). One crash also stopped every later comp. | Errors first, notes counted, full log on the Desktop, every comp in `safe()`, MAIN builds with what exists. |
| 4 | "Object is invalid" (line 54) in 6 scenes | Two shape groups created, then the first drawn into: AE invalidates sibling handles after `addProperty`/`moveTo`. Mock didn't emulate it. | Build one group fully before the next; mock emulates stale handles. |
| 5 | MAIN: "null is not an object" (line 196) | `"ADBE Mask Expansion"` isn't a matchName (it's `"ADBE Mask Offset"`); AE returns null silently. Mock auto-created any name. | `prop()` throws on null with the name; mock whitelists real matchNames; verified table. |
| 6 | "Invalid interpolation type" in S1 | A checkbox was given bezier keys; checkboxes are hold-only. | `isInterpolationTypeValid` check; mock rejects bezier on hold-only properties. |
| 7 | Easing "bad and wrong" vs the MP4 | Springs mapped as "2 keys over the nominal duration + generic bounce": pops arrived 5x late, 70% error. No layer motion blur. Eases were guessed, never verified against the source. | Fitted keys per move (`fit_move`), overshoot as real keys, `verify_curves.py` gate (fails above 2%), motion blur matched. |
| 8 | Particle easing impossible to change | The burst's curve was buried in the expression (`1 - Math.pow(1 - p, 3)`, a spring in `Math.exp`/`Math.cos`) and driven by a linear slider. Bobbing had hard-coded amounts. | Curves only in keys on a driver slider (graph editor); expressions linear; every behaviour a named control; mock flags hidden easing and uncontrolled time-based motion. |
| 9 | Had to ask for the fonts | Fonts downloaded early were lost when the sandbox reset; network was then blocked; fonts were never part of the deliverable. | Fonts fetched at project start into the persistent outputs folder, shipped in `fonts/` with licences; script checks and opens that folder. If impossible, the user hears it up front. |
| 10 | (caught in review) labels offset, nodes hiding their centre, keys colliding | `setParentWithJump` to shape layers; Contents draw first item in front; float rounding when snapping. | Null parents with anchor = position; `grp()` paint order; `fr()` with epsilon and the fitter's 1-frame gap. |

## Process lessons

- "The mock passes" meant nothing while the mock was more forgiving than AE. Every AE error the user reports becomes
  a mock rule; the fix is done only when the mock reproduces the user's exact numbers on the old script and passes the new one.
- The user is the expensive test runner. Each round trip cost them a run, a screenshot and a message. Front-load:
  strict mock, stress modes (`SCALE2`, `ELSEWHERE`, `BREAK`), curve verification, before the first hand-off.
- Ask "would a non-coder be able to change this?" for every expression before writing it.
