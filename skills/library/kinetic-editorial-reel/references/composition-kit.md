# Composition kit — HyperFrames + Three.js building blocks

Self-contained patterns for building the reel. Copy, then adapt to the storyboard.

## Contents
1. Architecture
2. Head: GSAP, Three.js importmap, fonts
3. Tokens + scene scaffolding CSS + decor
4. Captions (word-by-word, LTR or RTL)
5. Timeline helpers + motion vocabulary
6. Perspective mapping (UI onto a photographed screen)
7. Three.js layers (falling sheets, glowing grid floor)
8. Audio: voice + SFX markers
9. Gotchas

---

## 1. Architecture

One `index.html`; one `<section class="scene … clip">` per storyboard frame on track 1; ONE
paused GSAP timeline in **global (voice) time**; Three.js canvases inside the scenes that need
3D. Why a single file: captions, SFX taps and Three.js all key off the same global word times,
and a Three.js module script inside a sub-composition `<template>` is fragile. Lint then warns
`nested_structure_needs_subcomposition`, `timeline_track_too_dense`,
`composition_file_too_large` — warnings, accepted by design. (If the user will edit heavily in
Studio, splitting scenes into `compositions/*.html` is the alternative; word times then become
scene-local.)

Keep two tables in the script — `SC` (scene starts) and `END` (scene ends) — and reference them
from every scene tween, so retiming a scene = its section's `data-start/data-duration` + these.

```html
<div id="root" data-composition-id="main" data-start="0" data-width="1080" data-height="1920" data-duration="20">
  <section id="s1" class="scene light clip" data-start="0" data-duration="1.2" data-track-index="1">
    <div class="grid"></div><div class="paper"></div>
    <div id="s1-shake" class="shake"><div id="s1-cam" class="cam"> <!-- hero --> </div></div>
    <div class="cap" …> <!-- caption --> </div>
  </section>
  …
  <audio id="vo" src="assets/audio/voice.wav" data-start="0" data-duration="19.2" data-track-index="10" data-volume="1"></audio>
  <!-- sfx:start -->
  <!-- sfx:end -->
</div>
```

## 2. Head

```html
<meta name="viewport" content="width=1080, height=1920" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script type="importmap">{ "imports": { "three": "https://cdn.jsdelivr.net/npm/three@0.181.2/build/three.module.js" } }</script>
```
Fonts: embed with `@font-face` pointing at local woff2 files (lint requires an in-file
@font-face). A clean neo-grotesk matches the style: IBM Plex Sans (Latin) / IBM Plex Sans Arabic
(Arabic) from fontsource, weights 500 + 700:
`https://cdn.jsdelivr.net/npm/@fontsource/<family>@5/files/<family>-<subset>-<weight>-normal.woff2`
→ `assets/fonts/`, one `@font-face` per subset with a `unicode-range`. Or use a family bundled
with HyperFrames (see `/hyperframes-creative` typography). Never letter-space cursive scripts
(it breaks joining).

## 3. Tokens + scaffolding + decor

```css
:root { --cream:#fff8f3; --black:#060505; --ink:#151211; --red:#e71f28; --ribbon:#cdc7c0; --pink:#fbd5cc; }
* { margin:0; padding:0; box-sizing:border-box; }
html, body { width:1080px; height:1920px; overflow:hidden; background:var(--black); }
#root { position:relative; width:100%; height:100%; overflow:hidden; font-family:"Brand Sans",sans-serif; }
.scene { position:absolute; inset:0; overflow:hidden; }
.light { background:var(--cream); color:var(--ink); }  .dark { background:var(--black); color:#fff; }
.shake, .cam, .layer { position:absolute; inset:0; }     .cam { transform-origin:50% 50%; }
.abs { position:absolute; display:block; }
canvas.three { position:absolute; inset:0; width:1080px; height:1920px; display:block; }

.grid { position:absolute; inset:0; pointer-events:none;
  background-image: linear-gradient(rgba(21,18,17,.12) 2px, transparent 2px),
                    linear-gradient(90deg, rgba(21,18,17,.12) 2px, transparent 2px);
  background-size:96px 96px; background-position:12px 20px;
  -webkit-mask-image: radial-gradient(ellipse 72% 52% at 50% 56%, #000 25%, transparent 78%);
          mask-image: radial-gradient(ellipse 72% 52% at 50% 56%, #000 25%, transparent 78%); }
.paper { position:absolute; inset:0; pointer-events:none; background:url("assets/img/paper_texture.png") center/cover;
  mix-blend-mode:multiply; opacity:.22; }          /* optional texture image */
.vignette { position:absolute; inset:0; pointer-events:none;
  background: radial-gradient(ellipse 80% 62% at 50% 50%, transparent 38%, rgba(0,0,0,.8) 100%); }
.barcode { position:absolute; top:150px; left:80px; width:230px; height:72px; }
.hd { position:absolute; left:80px; bottom:150px; display:flex; align-items:center; gap:14px;
  font-size:22px; font-weight:500; color:rgba(21,18,17,.72); direction:ltr; letter-spacing:.06em; }
.hd b { border:2px solid currentColor; border-radius:6px; padding:0 8px; font-weight:700; font-size:20px; }
svg.ribbon { position:absolute; inset:0; width:1080px; height:1920px; overflow:visible; }
svg.ribbon path { fill:none; stroke:var(--ribbon); stroke-width:150; stroke-linecap:round; }
```
Nest `section > .shake > .cam > content` when a scene needs both a camera push (scale on `.cam`)
and an impact shake (x/y on `.shake`) — separate elements so the tweens never fight.
Ribbon: `<svg class="ribbon" viewBox="0 0 1080 1920"><path id="sX-rib" pathLength="1" d="M 1320 -120 C 760 260, 160 640, 470 1080 S 980 1660, 560 2100"/></svg>`.
Barcode (static, seeded):
```js
document.querySelectorAll("svg.barcode").forEach((svg, n) => {
  const r = prng(11 + n); let x = 0, out = "";
  while (x < 226) { const w = 1 + Math.floor(r() * 4); if (r() > .35) out += `<rect x="${x}" y="0" width="${w}" height="72" fill="#151211"/>`; x += w + 1 + Math.floor(r() * 2); }
  svg.innerHTML = out;
});
function prng(seed) { return function () { seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
```

## 4. Captions

```html
<div class="cap" data-layout-allow-overlap data-layout-allow-occlusion style="top: 330px">
  <span data-layout-allow-overlap data-layout-allow-occlusion class="ln">
    <span data-layout-allow-overlap data-layout-allow-occlusion class="w" data-t="1.26">You've</span>
    <span data-layout-allow-overlap data-layout-allow-occlusion class="w" data-t="1.48">got the</span></span>
  <span data-layout-allow-overlap data-layout-allow-occlusion class="ln i1">
    <span data-layout-allow-overlap data-layout-allow-occlusion class="w k" data-t="1.87">ideas</span></span>
</div>
```
```css
.cap { position:absolute; left:80px; right:80px; z-index:30; direction:ltr; text-align:left; line-height:1.04; }
.cap.center { text-align:center; }
.ln { display:block; white-space:nowrap; }   .ln.i1 { padding-left:70px; }   .ln.i2 { padding-left:150px; }
.w { display:inline-block; font-weight:500; font-size:84px; margin-right:.2em; transform-origin:50% 60%; will-change:transform,filter,opacity; }
.w.k  { font-weight:700; font-size:170px; color:var(--red); line-height:1.1; }
.w.xl { font-weight:700; font-size:186px; }
.w.slam { font-weight:700; font-size:184px; color:var(--red); line-height:1.1;
  -webkit-mask-image:url("assets/img/ink_grunge.png"); mask-image:url("assets/img/ink_grunge.png");
  -webkit-mask-size:460px; mask-size:460px; }
.dark .w { color:#fff; text-shadow:0 0 22px rgba(255,255,255,.28); }
.dark .w.k, .dark .w.slam { color:var(--red); text-shadow:0 0 26px rgba(231,31,40,.85), 0 0 90px rgba(231,31,40,.5); }
.blk { position:absolute; left:0; right:0; top:0; }
```
- `data-t` = GLOBAL voice time the word starts (from `word_timing.py`). Keep them literal in the
  HTML — the user corrects timing by editing these numbers.
- `w` setup word · `w k` keyword (one per block, red) · `w xl` huge white punch word ·
  `w slam` slam keyword (ink mask from `textures.py grunge`, no blur-in).
- Right-to-left scripts: `.cap { direction:rtl; text-align:right }`, indents become
  `padding-right`, spacing `margin-left`.
- The `data-layout-allow-*` attributes are REQUIRED: tight leading makes glyph boxes overlap and
  `hyperframes check` otherwise fails with `content_overlap` (the overlap is the style).
- Several caption blocks in one long scene: wrap each in `<div class="blk" id="sX-b1" …>` at the
  same spot and `blockOut()` the previous one when the next starts.
- Safe area for Reels/TikTok: captions between y≈200 and y≈1300; nothing vital in the bottom 350px.

## 5. Timeline helpers + motion vocabulary

```js
const tl = gsap.timeline({ paused: true });
const SC  = { s1: 0, s2: 1.15 /* … */ };
const END = { s1: 1.15, s2: 2.4 /* … */ };
const push = (sel, s, e, from, to, origin) =>
  tl.fromTo(sel, { scale: from, transformOrigin: origin || "50% 50%" }, { scale: to, duration: e - s, ease: "none" }, s);
function shake(sel, t, a = 12) {
  tl.fromTo(sel, { x: 0, y: 0 }, { keyframes: [ { x: -a, y: a*.5, duration: .03 }, { x: a*.8, y: -a*.4, duration: .03 },
    { x: -a*.45, y: a*.25, duration: .03 }, { x: 0, y: 0, duration: .05 } ], ease: "none", immediateRender: false }, t);
}
document.querySelectorAll(".w[data-t]").forEach((el, i) => {
  const t = parseFloat(el.dataset.t);
  if (el.classList.contains("slam")) {          // lands ON the syllable
    const rot = [-5, 4, -3][i % 3];
    tl.fromTo(el, { opacity: 0, scale: 2.3, rotation: rot - 8 }, { opacity: 1, scale: 1, rotation: rot, duration: .13, ease: "power4.in" }, t - .13);
  } else if (el.classList.contains("k")) {      // keyword blur-in
    tl.fromTo(el, { opacity: 0, scale: 1.35, filter: "blur(26px)", y: 16 }, { opacity: 1, scale: 1, filter: "blur(0px)", y: 0, duration: .3, ease: "expo.out" }, t - .04);
  } else {                                      // setup word blur-in
    tl.fromTo(el, { opacity: 0, scale: 1.2, filter: "blur(16px)", y: 12 }, { opacity: 1, scale: 1, filter: "blur(0px)", y: 0, duration: .2, ease: "expo.out" }, t - .03);
  }
});
function blockOut(sel, t) { tl.fromTo(sel, { opacity: 1 }, { opacity: 0, duration: .06, ease: "none", immediateRender: false }, t - .06); }
function ribbon(sel, t, d) { tl.fromTo(sel, { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: d, ease: "power2.out" }, t); }
// … scene tweens …
window.__timelines["main"] = tl;   // LAST line of the build
```
Speed presets scale these: rapid ≈ durations ×0.8; calm ≈ ×1.3 with softer eases.

Motion vocabulary (1–2 per scene, vary across scenes):
- **Rotational entry**: hero from `{scale:.64, rotation:-22, x:-90, y:170, filter:"blur(10px)"}` to
  settled over ~1.1 s `power2.inOut` — smooth. (`expo.out` reads as a snap; avoid it on openers.)
- **Spring pop**: `{scale:0}` → 1, `back.out(2.2)`, .45 s (icons, badges, emoji).
- **Push-in**: `.cam` scale 1 → 1.05–1.12 over the whole scene, `ease:"none"`.
- **Focus pull**: `filter: blur(22px)` → 0 + scale 1.12 → 1 over .45 s (photos, screenshots).
- **Prop drop / stamp**: prop from `y:-1500` → 0 in .16 s `power4.in`; the mark it leaves appears
  (opacity set) on the impact frame + `shake()`; prop lifts `power2.in` .16 s. Land the prop's
  contact point on the mark's centre using anchors (anchoring.md).
- **Ripple**: bordered accent circle scale 0 → 14 from a badge, then tint the background.
- **Cover wipe**: a black circle (iris) or a giant prop scaling past the frame edges into the
  cut. Keep it hidden (`opacity:0` in CSS + `tl.set(sel,{opacity:1}, start)`) until it starts,
  and make sure it FULLY covers by the scene's last frame (render samples at 30 fps).
- **Rotate-through exit**: `.cam` rotation 0→14, scale 1→1.28 in the last .2 s.
- **Count-up**: proxy `{v:0}` → `{v:N}`, `onUpdate` writes `textContent` (seek-safe).
- **Dial hands**: SVG `<g>` hands rotated with `svgOrigin: "cx cy"` = the measured pivot.
- **One-word punch frame**: dark scene, word at 260–330 px red glow, `push` 1→1.08, `shake` on the
  word, impact SFX.

## 6. Perspective mapping (UI onto a photographed screen)

```js
function quadMatrix(w, h, q) {                       // map a w×h box onto quad [TL,TR,BR,BL]
  const src = [[0, 0], [w, 0], [w, h], [0, h]], A = [], B = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [u, v] = q[i];
    A.push([x, y, 1, 0, 0, 0, -x * u, -y * u]); B.push(u);
    A.push([0, 0, 0, x, y, 1, -x * v, -y * v]); B.push(v);
  }
  for (let c = 0; c < 8; c++) {
    let p = c; for (let r = c + 1; r < 8; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    [A[c], A[p]] = [A[p], A[c]]; [B[c], B[p]] = [B[p], B[c]];
    for (let r = 0; r < 8; r++) if (r !== c) { const f = A[r][c] / A[c][c]; for (let k = c; k < 8; k++) A[r][k] -= f * A[c][k]; B[r] -= f * B[c]; }
  }
  const H = B.map((b, i) => b / A[i][i]);
  return `matrix3d(${H[0]},${H[3]},0,${H[6]},${H[1]},${H[4]},0,${H[7]},0,0,1,0,${H[2]},${H[5]},0,1)`;
}
// corners in image px × display scale, relative to the wrapper that holds the photo:
screenEl.style.transform = quadMatrix(540, 1170, QUAD);   // CSS: transform-origin: 0 0
```
Build the lock screen / notifications / app UI as normal HTML inside that box: it inherits the
photo's perspective and any camera push on the wrapper.

## 7. Three.js layers

```js
import * as THREE from "three";
const W = 1080, H = 1920;
function makeRenderer(id) {
  const r = new THREE.WebGLRenderer({ canvas: document.getElementById(id), alpha: true, antialias: true });
  r.setPixelRatio(1); r.setSize(W, H, false); r.setClearColor(0x000000, 0); return r;
}
const loader = new THREE.TextureLoader();           // DefaultLoadingManager → runtime waits for it
const texA = loader.load("assets/img/sheet_a.png"); texA.colorSpace = THREE.SRGBColorSpace;

// falling / fluttering sheets (paper, bills, cards, leaves)
function sheetLayer(canvasId, count, seed, zMin, zMax, size, start) {
  const renderer = makeRenderer(canvasId), scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(35, W / H, 0.1, 100); cam.position.set(0, 0, 10);
  scene.add(new THREE.AmbientLight(0xffffff, 1.9));
  const dl = new THREE.DirectionalLight(0xffffff, 1.4); dl.position.set(-3, 5, 8); scene.add(dl);
  const r = prng(seed), items = [];
  for (let i = 0; i < count; i++) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(size, size),
      new THREE.MeshLambertMaterial({ map: texA, transparent: true, alphaTest: .02, side: THREE.DoubleSide }));
    const z = zMin + r() * (zMax - zMin), halfH = Math.tan(17.5 * Math.PI / 180) * (10 - z), halfW = halfH * W / H;
    items.push({ m, z, x0: (r()*2-1)*halfW*.95, y0: halfH + size*.6 + r()*halfH*2.2, v: halfH*(1.1 + r()*.9),
      fx: .25 + r()*.35, w1: 3 + r()*3, w2: 2 + r()*3, p1: r()*6.28, p2: r()*6.28, rz: (r()*2-1)*.8, spin: (r()*2-1)*1.6 });
    scene.add(m);
  }
  return (t) => { const lt = t - start;
    for (const p of items) {
      p.m.position.set(p.x0 + Math.sin(lt*p.w1 + p.p1)*p.fx, p.y0 - p.v*(lt + .55), p.z);
      p.m.rotation.set(Math.sin(lt*p.w2 + p.p2)*.75, lt*p.spin, p.rz + Math.sin(lt*p.w1 + p.p2)*.5);
    }
    renderer.render(scene, cam); };
}
const back  = sheetLayer("s3-back", 11, 21, -3, 1.5, 1.35, 2.4);
const front = sheetLayer("s3-front", 3, 77, 4.2, 5.4, 1.5, 2.4);   // canvas has CSS filter: blur(14px) = depth of field

// glowing perspective grid floor under a hero on black
const fr = makeRenderer("s8-floor"), fScene = new THREE.Scene();
fScene.fog = new THREE.Fog(0x060505, 6, 30);
const fCam = new THREE.PerspectiveCamera(50, W / H, 0.1, 100);
const grid = new THREE.GridHelper(80, 80, 0xe71f28, 0x6a5a58); grid.position.y = -3.2; fScene.add(grid);
const floor = (t) => { const lt = t - 12.25; fCam.position.set(0, .6, 12 - lt*2.2); fCam.lookAt(0, -1.4, -10 - lt*2.2); fr.render(fScene, fCam); };

function renderAt(time) {
  if (time >= 2.3 && time <= 3.9) { back(time); front(time); }
  if (time >= 12.15 && time <= 14.1) floor(time);
}
window.addEventListener("hf-seek", (e) => renderAt(e.detail.time));
THREE.DefaultLoadingManager.onLoad = () => renderAt(window.__hfThreeTime || 0);
renderAt(window.__hfThreeTime || 0);
```
Other fits for this style: seeded confetti / particle bursts, a slowly orbiting extruded logo or
word, a data swarm. Don't add 3D for its own sake. Everything must be a pure function of `time`
(seeded PRNG, no clocks, no requestAnimationFrame loop).

## 8. Audio

Voice on track 10; the SFX block between `<!-- sfx:start -->` and `<!-- sfx:end -->`, written by
`scripts/place_sfx.py` (auto-allocates tracks 11+, adds per-word taps with `--taps`). Every
`<audio>` needs an `id`, or the mixer silently drops it.

## 9. Gotchas

- **Studio rewrites the file**: once opened in Studio, every element gets `data-hf-id="…"` and
  boolean attributes are normalised (`data-layout-allow-overlap=""`). Later scripted edits must
  match around that — anchor on `data-t="…">word`, `data-start="…" data-duration="…"`, ids or JS
  lines, and use regexes with `[^>]*` instead of exact tag strings.
- `hyperframes check` layout errors on captions → the allow-overlap/occlusion attrs (§4).
- Contrast check on an ink mark over a photo (multiply blend) can fail → use a deeper ink
  (~#6a0d11) for marks that sit on photographs.
- Snapshots quantize to 30 fps frames: an impact at 17.66 s may look mid-air at `--at 17.66`;
  check ±1 frame before "fixing" anything.
- `fromTo` renders its FROM state immediately — a prop "waiting" off-screen must be fully off
  (top + y + height < 0) or it peeks in at the frame edge before its move.
- Mixed-direction text (RTL words + Latin numbers/dates): set `direction` explicitly on the
  container and wrap the Latin run in `<span style="direction:ltr;unicode-bidi:isolate">`.
- Keep SFX low under the voice: notification/ping ≈ .08, ticking beds ≈ .1 — .3 already reads loud.
