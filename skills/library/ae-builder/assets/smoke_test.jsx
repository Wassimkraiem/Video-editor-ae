// SELF-CONTAINED smoke test: ae_build_lib.jsx + CURVES + FITS (from ease_fit.fit_move) + a tiny build touching every helper.
// Run: node ../scripts/ae_mock_dryrun.js smoke_test.jsx  (must print NO ISSUES). Use it as the pattern for new build scripts.
// smoke_test.jsx = ae_build_lib.jsx + CURVES + a tiny build that touches every helper. Must pass the strict mock with NO ISSUES.
// =============================================================================
// ae_build_lib.jsx  -  helper library for After Effects rebuild scripts (ExtendScript / ES3)
//
// Paste this at the TOP of the generated build script (one self-contained .jsx is easiest for users).
// Every helper here exists because a real build broke without it. See references/ae_runtime_facts.md.
//
// ES3 RULES (ExtendScript): no let/const/arrow/template strings/forEach/map/filter/JSON/Array.indexOf,
// no trailing commas, and NEVER a reserved word as a name or property (char, int, class, default,
// final, short, long, byte, float, double, goto, native, package, public, static, super, enum...).
// =============================================================================

var FPS = 25, W = 1920, H = 1080;                 // overwritten by the build script's project settings
var HAS_NEW_MATTES = parseFloat(app.version) >= 23;
var ERRORS = [], WARN = [], DONE = [], EXPR_COUNT = 0, KEY_COUNT = 0, LAYER_COUNT = 0, MATTE_COUNT = 0;
var EXPRS = [], LCTRL = [], MATTES = [];
var OFF = 0;                                      // parent-timeline time that sits at time 0 of the comp being built

// ---------------------------------------------------------------- time: author in seconds, snapped to whole frames
function fr(t) { return Math.round(t * FPS + 1e-6) / FPS; }   // +1e-6 stops 13.35-11.81 = 1.53999 rounding the wrong way
function lt(t) { return fr(t - OFF); }

// ---------------------------------------------------------------- colours
function rgb(h) { h = h.replace("#", ""); return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255]; }
function rgba(h) { var c = rgb(h); c.push(1); return c; }      // shape fills/strokes want 4 values, text fillColor wants 3

// ---------------------------------------------------------------- safe property access
// AE returns NULL (no error) when a name/matchName doesn't exist. Always go through prop() so a wrong
// name fails loudly on the line that caused it, instead of "null is not an object" somewhere later.
function prop(parent, name) {
  var p = parent.property(name);
  if (p === null || p === undefined) throw new Error("AE has no property '" + name + "' under '" + parent.name + "'");
  return p;
}
function tr(L) { return prop(L, "ADBE Transform Group"); }
function P(L) { return prop(tr(L), "ADBE Position"); }
function PX(L) { return prop(tr(L), "ADBE Position_0"); }
function PY(L) { return prop(tr(L), "ADBE Position_1"); }
function S(L) { return prop(tr(L), "ADBE Scale"); }
function R(L) { return prop(tr(L), "ADBE Rotate Z"); }
function O(L) { return prop(tr(L), "ADBE Opacity"); }
function A(L) { return prop(tr(L), "ADBE Anchor Point"); }
function sep(L) { P(L).dimensionsSeparated = true; }
function fixv(p, v) { if (v instanceof Array && p.value instanceof Array && v.length < p.value.length) { var o = v.slice(0); while (o.length < p.value.length) o.push(p.value[o.length]); return o; } return v; }   // pad with the property's own value (Scale z = 100, Position z = 0)
function setv(p, v) { v = fixv(p, v); try { p.setValue(v); } catch (e) { if (v instanceof Array && v.length == 3) p.setValue(v.slice(0, 2)); else throw e; } }
function sv(L, v) { setv(S(L), v); }

// ---------------------------------------------------------------- comps, folders, layers
function folder(name, parent) { var f = app.project.items.addFolder(name); if (parent) f.parentFolder = parent; return f; }
function makeComp(name, dur, fold, comment, w, h) {
  var c = app.project.items.addComp(name, w || W, h || H, 1, dur, FPS);
  if (fold) c.parentFolder = fold; c.comment = comment || ""; matchMotionBlur(c); return c;
}
// Nulls get anchor = position, so children parented to them keep plain comp coordinates.
function nul(c, name, x, y, label) { var L = c.layers.addNull(); L.name = name; setv(A(L), [x, y]); setv(P(L), [x, y]); L.label = (label == null) ? 1 : label; LAYER_COUNT++; return L; }
function shp(c, name, x, y) { var L = c.layers.addShape(); L.name = name; setv(A(L), [0, 0]); setv(P(L), [x, y]); L.label = 15; LAYER_COUNT++; return L; }
// setParentWithJump does NOT compensate: the child's numbers stay as they are, now read in the parent's space.
// That's only "comp coordinates" when the parent is a null built with nul() (anchor = position). Never parent
// art to a shape layer expecting comp coordinates; set the child's position in the parent's space instead.
function parentTo(child, parent) { child.setParentWithJump(parent); }

// ---------------------------------------------------------------- shape contents (handle-safe)
// RULE 1: in shape Contents the FIRST item is drawn IN FRONT. grp() moves each new group to the top, so the
//         order you write code in = paint order (later = in front).
// RULE 2: adding or moving a group kills handles to its SIBLINGS ("Object is invalid"). Finish one group
//         completely (paths, fill, stroke, trim, transform) BEFORE calling grp() again on the same parent.
function grp(L, name, inGroup) {
  var host = inGroup ? prop(inGroup, "ADBE Vectors Group") : prop(L, "ADBE Root Vectors Group");
  var g = host.addProperty("ADBE Vector Group"); g.name = name;
  if (host.numProperties > 1) { g.moveTo(1); g = host.property(1); }
  return g;
}
function vg(g) { return prop(g, "ADBE Vectors Group"); }
function gtr(g) { return prop(g, "ADBE Vector Transform Group"); }
function rect(g, w, h, x, y, r) { var p = vg(g).addProperty("ADBE Vector Shape - Rect"); setv(prop(p, "ADBE Vector Rect Size"), [w, h]); setv(prop(p, "ADBE Vector Rect Position"), [x || 0, y || 0]); prop(p, "ADBE Vector Rect Roundness").setValue(r || 0); return p; }
function ell(g, w, h, x, y) { var p = vg(g).addProperty("ADBE Vector Shape - Ellipse"); setv(prop(p, "ADBE Vector Ellipse Size"), [w, h]); setv(prop(p, "ADBE Vector Ellipse Position"), [x || 0, y || 0]); return p; }
function pth(g, verts, closed, inT, outT, name) {
  var p = vg(g).addProperty("ADBE Vector Shape - Group"); if (name) p.name = name;
  var s = new Shape(); s.vertices = verts; s.closed = closed; if (inT) s.inTangents = inT; if (outT) s.outTangents = outT;
  prop(p, "ADBE Vector Shape").setValue(s); return p;
}
function fill(g, col, op, evenOdd) { var f = vg(g).addProperty("ADBE Vector Graphic - Fill"); prop(f, "ADBE Vector Fill Color").setValue(rgba(col)); if (op != null) prop(f, "ADBE Vector Fill Opacity").setValue(op); if (evenOdd) prop(f, "ADBE Vector Fill Rule").setValue(2); return f; }
function stroke(g, col, w, round) { var s = vg(g).addProperty("ADBE Vector Graphic - Stroke"); prop(s, "ADBE Vector Stroke Color").setValue(rgba(col)); prop(s, "ADBE Vector Stroke Width").setValue(w); if (round) { prop(s, "ADBE Vector Stroke Line Cap").setValue(2); prop(s, "ADBE Vector Stroke Line Join").setValue(2); } return s; }
function trim(g) { return vg(g).addProperty("ADBE Vector Filter - Trim"); }
function dashes(s, dash, gap) { try { prop(s, "ADBE Vector Stroke Dashes").addProperty("ADBE Vector Stroke Dash 1").setValue(dash); prop(s, "ADBE Vector Stroke Dashes").addProperty("ADBE Vector Stroke Gap 1").setValue(gap); } catch (e) { WARN.push("Dashes skipped (solid line instead)"); } }

// ---------------------------------------------------------------- masks (Mask Expansion's matchName is "ADBE Mask Offset")
function addMask(L, name, shape) { var m = prop(L, "ADBE Mask Parade").addProperty("ADBE Mask Atom"); m.name = name; prop(m, "ADBE Mask Shape").setValue(shape); return m; }
function maskExpansion(L, name) { return prop(prop(prop(L, "ADBE Mask Parade"), name), "ADBE Mask Offset"); }
function circleShape(cx, cy, r) { var k = 0.5523 * r, s = new Shape(); s.vertices = [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]]; s.inTangents = [[-k, 0], [0, -k], [k, 0], [0, k]]; s.outTangents = [[k, 0], [0, k], [-k, 0], [0, -k]]; s.closed = true; return s; }
function rrShape(x, y, w, h, r) {
  var k = 0.5523 * r, s = new Shape();
  s.vertices = [[x + r, y], [x + w - r, y], [x + w, y + r], [x + w, y + h - r], [x + w - r, y + h], [x + r, y + h], [x, y + h - r], [x, y + r]];
  s.inTangents = [[-k, 0], [0, 0], [0, -k], [0, 0], [k, 0], [0, 0], [0, k], [0, 0]];
  s.outTangents = [[0, 0], [k, 0], [0, 0], [0, k], [0, 0], [-k, 0], [0, 0], [0, -k]]; s.closed = true; return s;
}

// ---------------------------------------------------------------- fonts
var MISSING_FONTS = {};
function fontInstalled(psName) {
  try { if (app.fonts && app.fonts.getFontsByPostScriptName) return app.fonts.getFontsByPostScriptName(psName).length > 0; } catch (e) { }
  return null;   // unknown on older AE
}
function setFont(d, font) {
  if (fontInstalled(font) === false) { MISSING_FONTS[font] = 1; }
  try { d.font = font; } catch (e) { MISSING_FONTS[font] = 1; }
}
// Call once before building. Lists missing fonts, points at the bundled /fonts folder and opens it.
function checkFonts(list, root) {
  var miss = [], i;
  for (i = 0; i < list.length; i++) if (fontInstalled(list[i]) === false) miss.push(list[i]);
  if (!miss.length) return true;
  var fd = root ? Folder(root.fsName + "/fonts") : null;
  var msg = "These fonts are not installed:\n  " + miss.join("\n  ") + "\n\n";
  if (fd && fd.exists) msg += "They are in the 'fonts' folder next to this script. I'll open it: double-click each file > Install, restart After Effects, then run the script again.\n\nClick OK to keep building anyway (text will use a substitute font).";
  else msg += "Install them (see README), then run the script again.\n\nClick OK to keep building anyway.";
  alert(msg); if (fd && fd.exists) { try { fd.execute(); } catch (e2) { } }
  WARN.push("Missing fonts: " + miss.join(", "));
  return false;
}
function txt(c, name, str, font, size, col, tracking, x, y, pivot, just) {
  var L = c.layers.addText(str); L.name = name;
  var sp = prop(prop(L, "ADBE Text Properties"), "ADBE Text Document"), d = sp.value;
  if (d.resetCharStyle) d.resetCharStyle(); if (d.resetParagraphStyle) d.resetParagraphStyle();
  setFont(d, font); d.fontSize = size; d.applyFill = true; d.fillColor = rgb(col); d.applyStroke = false; d.tracking = tracking || 0;
  d.justification = just || ParagraphJustification.CENTER_JUSTIFY; sp.setValue(d);
  var r = L.sourceRectAtTime(0, false);
  setv(A(L), [r.left + r.width / 2, (pivot == "bottom") ? r.top + r.height : r.top + r.height / 2]);
  setv(P(L), [x, y]); L.label = 15; LAYER_COUNT++; return L;
}

// ---------------------------------------------------------------- assets next to the script (never fail silently)
function findProjectFolder(markerRelPath) {
  var tries = [], i;
  try { tries.push(File($.fileName).parent); } catch (e) { }
  for (i = 0; i < tries.length; i++) if (tries[i] && File(tries[i].fsName + "/" + markerRelPath).exists) return tries[i];
  alert("I can't see '" + markerRelPath + "' next to this script.\nIn the next window, pick the unzipped project folder.");
  var f = Folder.selectDialog("Pick the unzipped project folder");
  if (f && File(f.fsName + "/" + markerRelPath).exists) return f;
  ERRORS.push("Project folder not found: images and fonts will be missing.");
  return null;
}
function importAsset(root, rel, fold) {
  if (!root) return null; var f = File(root.fsName + "/" + rel);
  if (!f.exists) { WARN.push("Missing file: " + rel); return null; }
  var it = app.project.importFile(new ImportOptions(f)); if (fold) it.parentFolder = fold; return it;
}

// ---------------------------------------------------------------- expression controls + deferred wiring
function ctl(L, type, name, val) {
  var mn = { slider: "ADBE Slider Control", check: "ADBE Checkbox Control", point: "ADBE Point Control", layer: "ADBE Layer Control", angle: "ADBE Angle Control", color: "ADBE Color Control" }[type];
  var fx = prop(L, "ADBE Effect Parade").addProperty(mn); fx.name = name;
  if (type == "layer") LCTRL.push([L, name, val]); else if (val != null) fx.property(1).setValue(val);
  return fx;
}
function ctlProp(L, name) { return prop(prop(prop(L, "ADBE Effect Parade"), name), 1); }
function getter(L, which) {
  if (typeof which == "function") return which;
  return function () { if (which == "pos") return P(L); if (which == "x") return PX(L); if (which == "y") return PY(L); if (which == "scale") return S(L); if (which == "rot") return R(L); if (which == "op") return O(L); if (which == "anchor") return A(L); throw new Error("unknown channel " + which); };
}
// Expressions are applied LAST (finishComp), after every layer, control and parent exists.
// Every expression text must start with "// WHAT it does. Controls: CTRL_X > A, B".
function expr(L, which, text) { EXPRS.push({ L: L, g: getter(L, which), t: text }); }

// ---------------------------------------------------------------- keyframes that match the source curve
// CURVES (from scripts/ease_fit.py) are pasted here by the generator: { name: [[u, value, speed, inflIn, inflOut], ...] }
function canBezier(p) { try { return p.isInterpolationTypeValid(KeyframeInterpolationType.BEZIER); } catch (e) { return true; } }
function setKeySafe(p, t, v) { v = fixv(p, v); try { p.setValueAtTime(t, v); } catch (e) { if (v instanceof Array && v.length == 3) p.setValueAtTime(t, v.slice(0, 2)); else throw e; } }
function easeCount(p) { var t = p.propertyValueType; if (t == PropertyValueType.TwoD_SPATIAL || t == PropertyValueType.ThreeD_SPATIAL || t == PropertyValueType.OneD || t == PropertyValueType.COLOR || t == PropertyValueType.SHAPE) return 1; return (p.value instanceof Array) ? p.value.length : 1; }
function setEaseSafe(p, k, inE, outE) {
  try { p.setTemporalEaseAtKey(k, inE, outE); return; } catch (e) { }
  for (var n = 1; n <= 3; n++) { if (n == inE.length) continue; var a = [], b = []; for (var i = 0; i < n; i++) { a.push(inE[Math.min(i, inE.length - 1)]); b.push(outE[Math.min(i, outE.length - 1)]); } try { p.setTemporalEaseAtKey(k, a, b); return; } catch (e2) { } }
  WARN.push("Ease left default on " + p.name + " key " + k);
}
// Apply one fitted curve: the move from 'from' to 'to' starting at t0 (parent time) lasting dur seconds.
// All channels of one move (scale, y, rotation, opacity) should use the SAME t0/dur/curve so they stay in sync.
function applyCurve(L, which, t0, dur, from, to, curveName) {
  var g = getter(L, which), p = g(), C = CURVES[curveName]; if (!C) throw new Error("No curve named " + curveName);
  var spatial = (p.propertyValueType == PropertyValueType.TwoD_SPATIAL || p.propertyValueType == PropertyValueType.ThreeD_SPATIAL);
  var isArr = from instanceof Array, n = easeCount(p), keys = [], i, d;
  for (i = 0; i < C.length; i++) {
    var u = C[i][0], f = (i == 0) ? 0 : (i == C.length - 1 ? 1 : C[i][1]);
    var v = isArr ? [] : from + (to - from) * f; if (isArr) for (d = 0; d < from.length; d++) v.push(from[d] + (to[d] - from[d]) * f);
    var t = lt(t0 + u * dur); if (keys.length && t <= keys[keys.length - 1].t) continue;   // never two keys in one frame
    setKeySafe(p, t, v); keys.push({ t: t, c: C[i], last: i == C.length - 1 });
  }
  if (!canBezier(p)) { for (i = 0; i < keys.length; i++) { try { var kh = p.nearestKeyIndex(keys[i].t); p.setInterpolationTypeAtKey(kh, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD); } catch (e) { } } return; }
  for (i = 0; i < keys.length; i++) {
    var k = p.nearestKeyIndex(keys[i].t), c = keys[i].c, inE = [], outE = [], sp = keys[i].last ? 0 : c[2];
    for (d = 0; d < n; d++) {
      var delta = spatial ? lenOf(from, to) : (isArr ? (to[Math.min(d, to.length - 1)] - from[Math.min(d, from.length - 1)]) : (to - from));
      var spd = sp * delta / dur; if (spatial) spd = Math.abs(spd);
      inE.push(new KeyframeEase(spd, Math.max(0.1, Math.min(100, c[3])))); outE.push(new KeyframeEase(spd, Math.max(0.1, Math.min(100, c[4]))));
    }
    p.setInterpolationTypeAtKey(k, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
    setEaseSafe(p, k, inE, outE); KEY_COUNT++;
  }
}

// PREFERRED: apply a move fitted by the generator with ease_fit.fit_move() (frame-aware, verified against the source).
// fit = [[t (parent time, already on whole frames), fraction, speed (fraction per s), inflIn %, inflOut %], ...]
function applyFit(L, which, fit, from, to) {
  var p = getter(L, which)(), isArr = from instanceof Array, n = easeCount(p), i, d;
  var spatial = (p.propertyValueType == PropertyValueType.TwoD_SPATIAL || p.propertyValueType == PropertyValueType.ThreeD_SPATIAL);
  var times = [];
  for (i = 0; i < fit.length; i++) {
    var f = fit[i][1], v = isArr ? [] : from + (to - from) * f; if (isArr) for (d = 0; d < from.length; d++) v.push(from[d] + (to[d] - from[d]) * f);
    times.push(lt(fit[i][0])); setKeySafe(p, times[i], v);
  }
  if (!canBezier(p)) { for (i = 0; i < times.length; i++) { try { p.setInterpolationTypeAtKey(p.nearestKeyIndex(times[i]), KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD); } catch (e) { } } return; }
  for (i = 0; i < fit.length; i++) {
    var k = p.nearestKeyIndex(times[i]), inE = [], outE = [];
    for (d = 0; d < n; d++) {
      var delta = spatial ? lenOf(from, to) : (isArr ? (to[Math.min(d, to.length - 1)] - from[Math.min(d, from.length - 1)]) : (to - from));
      var spd = fit[i][2] * delta; if (spatial) spd = Math.abs(spd);
      inE.push(new KeyframeEase(spd, Math.max(0.1, Math.min(100, fit[i][3])))); outE.push(new KeyframeEase(spd, Math.max(0.1, Math.min(100, fit[i][4]))));
    }
    p.setInterpolationTypeAtKey(k, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
    setEaseSafe(p, k, inE, outE); KEY_COUNT++;
  }
}

function lenOf(a, b) { if (!(a instanceof Array)) return Math.abs(b - a); var s = 0; for (var i = 0; i < a.length; i++) s += (b[i] - a[i]) * (b[i] - a[i]); return Math.sqrt(s); }
// Hold keys (switch something on/off at a moment)
function holdKey(L, which, t, v) { var p = getter(L, which)(); setKeySafe(p, lt(t), v); var k = p.nearestKeyIndex(lt(t)); try { p.setInterpolationTypeAtKey(k, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD); } catch (e) { } KEY_COUNT++; }

// ---------------------------------------------------------------- motion blur that matches the source render
var SHUTTER_ANGLE = 180;   // source renders that blend N sub-frames over half a frame = 180 degrees
function matchMotionBlur(c) { try { c.motionBlur = true; c.shutterAngle = SHUTTER_ANGLE; c.shutterPhase = -SHUTTER_ANGLE / 2; c.motionBlurSamplesPerFrame = 16; c.motionBlurAdaptiveSampleLimit = 128; } catch (e) { } }
function blur(L) { try { L.motionBlur = true; } catch (e) { } return L; }   // switch on for every layer that moves

// ---------------------------------------------------------------- reaction systems a non-coder can steer
// IMPACT BURST: particles fly out from a point when something lands.
//  - The TIMING CURVE lives in keyframes on CTRL_Burst_<name> > "Progress (%)" (graph editor = the particles' ease).
//    The keys are made from a fitted curve, so out of the box it matches the source.
//  - Everything else is a named slider: Distance (%), Size (%), Spin (deg), Stagger (frames), Drift (px), Drift Speed.
//  - Particle expressions are LINEAR maps of Progress: no hidden easing maths.
function makeBurst(c, name, origin, t0, dur, curveName, parent, fit) {
  var ctrl = nul(c, "CTRL_Burst_" + name, origin[0], origin[1]);
  ctl(ctrl, "point", "Origin", origin); ctl(ctrl, "slider", "Progress (%)", 0);
  ctl(ctrl, "slider", "Distance (%)", 100); ctl(ctrl, "slider", "Size (%)", 100); ctl(ctrl, "slider", "Spin (deg)", 90);
  ctl(ctrl, "slider", "Stagger (frames)", 1); ctl(ctrl, "slider", "Drift (px)", 6); ctl(ctrl, "slider", "Drift Speed", 1.2);
  if (fit) applyFit(ctrl, function () { return ctlProp(ctrl, "Progress (%)"); }, fit, 0, 100);
  else applyCurve(ctrl, function () { return ctlProp(ctrl, "Progress (%)"); }, t0, dur, 0, 100, curveName);
  return ctrl;
}
function burstExprPos(ctrlName) {
  return ["// BURST: flies from Origin out to where this layer sits, then floats. Controls: " + ctrlName + " > Progress (%) keys (the ease), Distance, Stagger, Drift. This layer: Order.",
    "var c = thisComp.layer(\"" + ctrlName + "\");",
    "var delay = c.effect(\"Stagger (frames)\")(\"Slider\") * thisComp.frameDuration * effect(\"Order\")(\"Slider\");",
    "var p = c.effect(\"Progress (%)\")(\"Slider\").valueAtTime(time - delay) / 100;   // follows the keys exactly",
    "var reach = c.effect(\"Distance (%)\")(\"Slider\") / 100;",
    "var o = c.effect(\"Origin\")(\"Point\");",
    "var drift = c.effect(\"Drift (px)\")(\"Slider\") * Math.min(1, Math.max(0, p));",
    "var spd = c.effect(\"Drift Speed\")(\"Slider\");",
    "add(add(o, mul(sub(value, o), p * reach)), [Math.sin(time * spd + index) * drift, Math.cos(time * spd * 0.8 + index) * drift * 0.6]);"].join("\n");
}
function burstExprScale(ctrlName) {
  return ["// BURST SIZE: grows with Progress. Controls: " + ctrlName + " > Progress (%) keys, Size (%), Stagger. This layer: Order.",
    "var c = thisComp.layer(\"" + ctrlName + "\");",
    "var delay = c.effect(\"Stagger (frames)\")(\"Slider\") * thisComp.frameDuration * effect(\"Order\")(\"Slider\");",
    "var p = Math.max(0, c.effect(\"Progress (%)\")(\"Slider\").valueAtTime(time - delay) / 100);",
    "mul(value, p * c.effect(\"Size (%)\")(\"Slider\") / 100);"].join("\n");
}
function burstExprRot(ctrlName) {
  return ["// BURST SPIN: turns as it flies. Controls: " + ctrlName + " > Spin (deg), Progress (%) keys. This layer: Order.",
    "var c = thisComp.layer(\"" + ctrlName + "\");",
    "var delay = c.effect(\"Stagger (frames)\")(\"Slider\") * thisComp.frameDuration * effect(\"Order\")(\"Slider\");",
    "var p = c.effect(\"Progress (%)\")(\"Slider\").valueAtTime(time - delay) / 100;",
    "value + c.effect(\"Spin (deg)\")(\"Slider\") * p * (index % 2 ? 1 : -1);"].join("\n");
}
function addToBurst(L, ctrl, order) {
  ctl(L, "slider", "Order", order);
  expr(L, "pos", burstExprPos(ctrl.name)); expr(L, "scale", burstExprScale(ctrl.name)); expr(L, "rot", burstExprRot(ctrl.name)); L.label = 10; blur(L);
}
// STAGGER: key the Leader with applyCurve; followers copy it with a delay. Controls: Leader, Delay (frames); Order per layer.
function staggerExpr(ctrlName, path) {
  return ["// STAGGER: copies the Leader's move, delayed. Controls: " + ctrlName + " > Leader, Delay (frames). This layer: Order.",
    "var c = thisComp.layer(\"" + ctrlName + "\");",
    "var lead = c.effect(\"Leader\")(\"Layer\");",
    "lead." + path + ".valueAtTime(time - c.effect(\"Delay (frames)\")(\"Slider\") * thisComp.frameDuration * effect(\"Order\")(\"Slider\"));"].join("\n");
}
// FLOAT: idle bob/drift for held frames, with controls.
function floatExpr(ctrlName) {
  return ["// FLOAT: gentle idle bob so held frames stay alive. Controls: " + ctrlName + " > Float (px), Float Speed (0 = still).",
    "var c = thisComp.layer(\"" + ctrlName + "\");",
    "value + [0, Math.sin(time * c.effect(\"Float Speed\")(\"Slider\") + index) * c.effect(\"Float (px)\")(\"Slider\")];"].join("\n");
}


// LETTER CASCADE: each letter drops in after the one before. The ease lives in the keys of <ctrl> > Drop In (%)
// (apply a fitted curve to it, overshoot included); the selector maps it linearly per letter.
// pose = { pos: [x, y, 0], scale: 60, opacity: 0, rot: -3 } = how letters start. Controls on ctrl: Drop In (%), Letter Delay (frames).
function cascadeText(T, ctrl, pose) {
  function animProps() { return prop(prop(prop(prop(T, "ADBE Text Properties"), "ADBE Text Animators"), "Cascade"), "ADBE Text Animator Properties"); }
  var an = prop(prop(T, "ADBE Text Properties"), "ADBE Text Animators").addProperty("ADBE Text Animator"); an.name = "Cascade";
  if (pose.pos) animProps().addProperty("ADBE Text Position 3D").setValue(pose.pos);          // re-fetch after every add:
  if (pose.scale != null) animProps().addProperty("ADBE Text Scale 3D").setValue([pose.scale, pose.scale, 100]);   // adding kills sibling handles
  if (pose.opacity != null) animProps().addProperty("ADBE Text Opacity").setValue(pose.opacity);
  if (pose.rot) animProps().addProperty("ADBE Text Rotation").setValue(pose.rot);
  prop(prop(prop(prop(T, "ADBE Text Properties"), "ADBE Text Animators"), "Cascade"), "ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
  EXPRS.push({ L: T, g: function () { return prop(prop(prop(prop(prop(prop(T, "ADBE Text Properties"), "ADBE Text Animators"), "Cascade"), "ADBE Text Selectors"), 1), "ADBE Text Expressible Amount"); },
    t: ["// CASCADE: each letter follows the Drop In (%) keys, one after another. Controls: " + ctrl.name + " > Drop In (%) keys (the ease), Letter Delay (frames).",
        "var c = thisComp.layer(\"" + ctrl.name + "\");",
        "var d = c.effect(\"Letter Delay (frames)\")(\"Slider\") * thisComp.frameDuration;",
        "var a = 100 - c.effect(\"Drop In (%)\")(\"Slider\").valueAtTime(time - (textIndex - 1) * d);   // 100 = start pose, 0 = rest, below 0 = overshoot",
        "[a, a, a];"].join("\n") });
}

// ---------------------------------------------------------------- mattes
function setMatte(target, matte, type) {
  if (matte.containingComp.id !== target.containingComp.id) throw new Error("Matte must be in the same comp: " + matte.name);
  if (HAS_NEW_MATTES) target.setTrackMatte(matte, type); else { matte.moveBefore(target); target.trackMatteType = type; }
  if (matte.name.indexOf("MATTE_") === 0) { matte.enabled = false; matte.label = 3; }
  if (matte.inPoint > target.inPoint) matte.inPoint = target.inPoint;
  if (matte.outPoint < target.outPoint) matte.outPoint = target.outPoint;
  MATTE_COUNT++;
}
function checkMattes(comp) {
  var out = [];
  for (var i = 1; i <= comp.numLayers; i++) {
    var L = comp.layer(i); if (!L.hasTrackMatte) continue;
    var M = HAS_NEW_MATTES ? L.trackMatteLayer : (i > 1 ? comp.layer(i - 1) : null);
    if (!M) { out.push(L.name + ": matte missing"); continue; }
    if (M.name.indexOf("MATTE_") === 0 && M.enabled) out.push(M.name + ": video is on, it will show on screen");
    if (M.inPoint > L.inPoint + 0.001 || M.outPoint < L.outPoint - 0.001) out.push(M.name + ": shorter than " + L.name);
    if (M.hasTrackMatte) out.push(M.name + ": matte has its own matte, precomp instead");
  }
  return out;
}

// ---------------------------------------------------------------- finishing a comp (order matters)
function finishComp(c) {
  var tops = [], i;
  for (i = 1; i <= c.numLayers; i++) { var nm = c.layer(i).name; if (nm.indexOf("CTRL_") === 0 || nm.indexOf("CAM_") === 0 || nm.indexOf("GUIDE_") === 0) tops.push(c.layer(i)); }
  for (i = tops.length - 1; i >= 0; i--) tops[i].moveToBeginning();                      // 1 controls on top
  for (i = 0; i < MATTES.length; i++) setMatte(MATTES[i][0], MATTES[i][1], MATTES[i][2]); // 2 mattes once order is final
  for (i = 0; i < LCTRL.length; i++) ctlProp(LCTRL[i][0], LCTRL[i][1]).setValue(LCTRL[i][2].index);   // 3 layer pickers
  for (i = 0; i < EXPRS.length; i++) {                                                     // 4 expressions last
    var e = EXPRS[i], p = e.g();
    try { p.expression = e.t; EXPR_COUNT++; if (p.expressionError) ERRORS.push(c.name + " > " + e.L.name + ": " + p.expressionError); }
    catch (err) { ERRORS.push(c.name + " > " + e.L.name + ": " + err.toString()); }
  }
  var bad = checkMattes(c); for (i = 0; i < bad.length; i++) ERRORS.push(c.name + ": " + bad[i]);
  EXPRS = []; LCTRL = []; MATTES = [];
}

// ---------------------------------------------------------------- build isolation + honest report
function safe(name, fn) {
  try { var r = fn(); if (r) DONE.push(name); return r; }
  catch (e) { ERRORS.push(name + " FAILED: " + e.toString() + (e.line ? " (script line " + e.line + ")" : "")); EXPRS = []; LCTRL = []; MATTES = []; return null; }
}
function report(title, totalComps) {
  var head = title + "\nBuilt " + DONE.length + " of " + totalComps + " comps.  Layers: " + LAYER_COUNT + "   Keyframes: " + KEY_COUNT + "   Expressions: " + EXPR_COUNT + "   Mattes: " + MATTE_COUNT;
  var full = head + "\n\nERRORS (" + ERRORS.length + "):\n" + ERRORS.join("\n") + "\n\nNOTES (" + WARN.length + "):\n" + WARN.join("\n") + "\n\nBUILT:\n" + DONE.join("\n");
  var logPath = "";
  try { var lf = File(Folder.desktop.fsName + "/" + title.replace(/[^A-Za-z0-9]+/g, "_") + "_log.txt"); lf.encoding = "UTF-8"; lf.open("w"); lf.write(full); lf.close(); logPath = lf.fsName; } catch (e) { }
  var msg = head + (ERRORS.length ? "\n\nERRORS (" + ERRORS.length + "):\n" + ERRORS.slice(0, 12).join("\n") : "\n\nNo errors.");
  if (WARN.length) msg += "\n\nNotes: " + WARN.length + " (see the log)."; if (logPath) msg += "\n\nFull log: " + logPath;
  alert(msg);
}

// CURVES: generated by scripts/ease_fit.py. Each key = [u (0..1 of the move's time), value (0..1 of the move), speed (x move/duration), influence in %, influence out %].
// Overshooting curves have real keys at the peak and dip, so the overshoot is visible and editable in the graph editor.
var CURVES = {
  springElegant: [[0.0000,0.0000,5.0763,33.3,29.0],[0.3236,1.1688,-0.0109,50.5,25.5],[0.7156,0.9763,0.0000,55.5,27.5],[1.0000,1.0010,0.0496,46.0,33.3]],   // spring elegant (1-e^-5u cos 8u), 4 keys, max error 0.26%
  springSnappy: [[0.0000,0.0000,7.2336,33.3,29.5],[0.2043,1.2116,-0.0308,49.0,26.5],[0.4454,0.9610,0.0004,52.5,26.5],[0.6872,1.0072,-0.0004,52.5,28.0],[1.0000,0.9992,0.0107,71.0,33.3]],   // spring snappy (1-e^-7u cos 13u), 5 keys, max error 0.23%
  outBack: [[0.0000,0.0000,4.6760,33.3,31.3],[0.5805,1.1000,-0.0013,37.3,33.3],[1.0000,1.0000,-0.0068,33.8,33.3]],   // outBack (c1=1.70158), 3 keys, max error 0.06%
  outBackSoft: [[0.0000,0.0000,4.0792,33.3,32.5],[0.6514,1.0447,-0.0013,35.5,33.3],[1.0000,1.0000,-0.0044,34.3,33.3]],   // outBack soft (c1=1.1), 3 keys, max error 0.06%
  outCubic: [[0.0000,0.0000,2.9880,33.3,33.3],[1.0000,1.0000,0.0000,33.8,33.3]],   // easeOutCubic, 2 keys, max error 0.07%
  inOutCubic: [[0.0000,0.0000,0.0000,33.3,66.0],[1.0000,1.0000,0.0000,66.0,33.3]],   // easeInOutCubic, 2 keys, max error 0.84%
  outExpo: [[0.0000,0.0000,6.8360,33.3,15.0],[1.0000,1.0000,0.0069,65.0,33.3]],   // easeOutExpo, 2 keys, max error 0.30%
  inOutExpo: [[0.0000,0.0000,0.0070,33.3,89.5],[1.0000,1.0000,0.0070,89.5,33.3]],   // easeInOutExpo, 2 keys, max error 3.35%
  gravity: [[0.0000,0.0000,0.0040,33.3,28.8],[1.0000,1.0000,1.9960,37.8,33.3]],   // easeInQuad (gravity drop), 2 keys, max error 0.03%
  outQuad: [[0.0000,0.0000,1.9960,33.3,28.8],[1.0000,1.0000,0.0040,37.8,33.3]],   // easeOutQuad, 2 keys, max error 0.03%
  inOutSine: [[0.0000,-0.0000,0.0099,33.3,36.8],[1.0000,1.0000,0.0099,36.8,33.3]],   // easeInOutSine, 2 keys, max error 0.06%
  linear: [[0,0,1,33.3,33.3],[1,1,1,33.3,33.3]]
};

var FITS = {"pop": [[0.2, 0.0, 0.0, 33.33, 5], [0.32, 0.9627594055796147, 5.1547182029837435, 40, 40], [0.4, 1.16694623337023, 0.37755831931551853, 25, 25], [0.68, 0.9768214246231619, 0.06584241596163665, 60, 33.33], [0.88, 1.0009803715161676, 0.0, 50, 33.33]], "drop": [[0.2, 0.0, 0.0, 33.33, 33.33], [0.4, 0.27700831024930744, 2.770083102492382, 33.33, 90], [0.6, 1.0, 0.0, 30, 33.33]], "burst": [[0.56, 0.0, 0.0, 33.33, 33.33], [0.64, 0.432755680468224, 7.42600274955707, 90, 25], [0.72, 0.92914715353162, 4.550795862864332, 40, 40], [0.84, 1.1687313998895128, -0.03948837464906596, 25, 30], [1.16, 0.9764017041997883, 0.02367699404370871, 60, 30], [1.4, 1.0009803715161676, 0.0, 40, 33.33]], "card": [[1.0, 2.220446049250313e-16, 0.0, 33.33, 0.1], [1.2, 0.9557896296296295, 2.2222223472950775, 60, 33.33], [1.36, 1.09935168, -0.10750920826030352, 33.33, 33.33], [1.6, 1.0, 0.0, 33.33, 33.33]]};
(function () {
  app.beginUndoGroup("smoke");
  var root = findProjectFolder("ae_build_lib.jsx");
  checkFonts(["Unbounded-Black"], root);
  var c = safe("TEST_Comp", function () {
    var c = makeComp("TEST_Comp", 4, null, "smoke test");
    var bg = shp(c, "BG", 960, 540), g = grp(bg, "Fill"); rect(g, 1920, 1080); fill(g, "#DDE1E8");
    var cam = nul(c, "CAM_Push", 960, 540); applyCurve(cam, "scale", 0, 1.4, [107, 107], [100, 100], "outCubic");
    var pop = shp(c, "TEST_Pop", 960, 540), g1 = grp(pop, "Ring"); ell(g1, 200, 200); fill(g1, "#FF6443");
    var g2 = grp(pop, "Hole"); ell(g2, 100, 100); fill(g2, "#FFFFFF");               // second group only after the first is finished
    parentTo(pop, cam); blur(pop);
    applyFit(pop, "scale", FITS.pop, [0, 0], [100, 100]);
    sep(pop); applyFit(pop, "y", FITS.drop, -200, 540);
    var t = txt(c, "Title", "HELLO", "Unbounded-Black", 120, "#1E1E1E", -20, 960, 300);
    var ui = nul(c, "CTRL_UI", 300, 60); ctl(ui, "check", "Auto On", 0);
    applyCurve(ui, function () { return ctlProp(ui, "Auto On"); }, 1.0, 0.1, 0, 1, "linear");   // hold-only property: must become hold keys
    ctl(ui, "slider", "Float (px)", 4); ctl(ui, "slider", "Float Speed", 1.5); expr(pop, "x", "// FLOAT X: tiny sway. Controls: CTRL_UI > Float (px), Float Speed.\nvalue + Math.sin(time * thisComp.layer(\"CTRL_UI\").effect(\"Float Speed\")(\"Slider\")) * thisComp.layer(\"CTRL_UI\").effect(\"Float (px)\")(\"Slider\");");
    var b = makeBurst(c, "Impact", [960, 540], 0.58, 0.8, "springElegant", cam, FITS.burst);
    for (var i = 0; i < 6; i++) { var pL = shp(c, "Confetti_" + (i + 1), 960 + Math.cos(i) * 300, 540 + Math.sin(i) * 200), gp = grp(pL, "Dot"); ell(gp, 24, 24); fill(gp, "#FFC531"); parentTo(pL, cam); addToBurst(pL, b, i); }
    var lead = shp(c, "Card_1", 600, 800), gc = grp(lead, "Card"); rect(gc, 120, 80, 0, 0, 12); fill(gc, "#FFFFFF");
    var st = nul(c, "CTRL_Stagger_Cards", 420, 60); ctl(st, "layer", "Leader", lead); ctl(st, "slider", "Delay (frames)", 2);
    applyFit(lead, "scale", FITS.card, [0, 0], [100, 100]);
    for (i = 2; i <= 4; i++) { var f = shp(c, "Card_" + i, 600 + i * 150, 800), gf = grp(f, "Card"); rect(gf, 120, 80, 0, 0, 12); fill(gf, "#FFFFFF"); ctl(f, "slider", "Order", i - 1); expr(f, "scale", staggerExpr("CTRL_Stagger_Cards", "transform.scale")); }
    var ty = nul(c, "CTRL_Type", 600, 60); ctl(ty, "slider", "Drop In (%)", 0); ctl(ty, "slider", "Letter Delay (frames)", 1.25);
    applyFit(ty, function () { return ctlProp(ty, "Drop In (%)"); }, FITS.pop, 0, 100);
    cascadeText(t, ty, { pos: [0, -110, 0], scale: 60, opacity: 0, rot: -3 });
    var m = addMask(t, "Wipe", circleShape(960, 300, 1)); applyCurve(t, function () { return maskExpansion(t, "Wipe"); }, 0, 0.5, 0, 800, "inOutExpo");
    finishComp(c); return c;
  });
  app.endUndoGroup();
  report("SMOKE TEST", 1);
})();
