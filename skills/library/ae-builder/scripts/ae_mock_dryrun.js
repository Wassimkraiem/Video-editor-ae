// ae_mock_dryrun.js - run an After Effects build script (.jsx) in Node against a STRICT mock of AE.
//
//   node ae_mock_dryrun.js path/to/Build.jsx            normal run
//   SCALE2=1 node ae_mock_dryrun.js Build.jsx           AE wants 2 eases on Scale (2D layer quirk)
//   ELSEWHERE=1 node ae_mock_dryrun.js Build.jsx        script run from a folder without its assets (asset prompt path)
//   BREAK="ADBE Mask Atom" node ae_mock_dryrun.js Build.jsx   make adding that matchName throw (BREAK=1 = Drop Shadow): proves one failing comp can't stop the rest and the error is reported first
//
// It reproduces the After Effects behaviours that broke real builds (see references/ae_runtime_facts.md):
//   - ExtendScript is ES3: reserved words as names (char, int, class, default...), trailing commas, ES5+ methods
//   - property("Name") returns NULL for a name AE doesn't have (no error) -> strict per-group whitelists
//   - adding or moving a child in an indexed group (shape Contents, Effects, Masks, text animators) kills
//     handles to that group's OTHER children ("Object is invalid")
//   - hold-only properties (checkbox, dropdown) reject bezier interpolation
//   - setTemporalEaseAtKey throws on the wrong number of eases
//   - two keys on the same frame, NaN values, bad influences
//   - expressions that don't compile or point at layers/effects that don't exist
//   - expressions that animate over time with no control for the designer (non-coders can't steer them)
// When a user reports a NEW After Effects error: add the rule here first, reproduce their exact
// summary numbers, then fix the script. A mock that passes something AE rejects is a bug in the mock.
const fs = require('fs'), path = require('path'), vm = require('vm');
// `--set NAME=VALUE` does the same as the env vars above, for shells (like the studio's
// agent sandbox) that only allow one plain command: node ae_mock_dryrun.js Build.jsx --set DUMP_KEYS=keys.json
const ARGS = process.argv.slice(2);
for (let i = 0; i < ARGS.length; i++) if (ARGS[i] === '--set' && ARGS[i + 1] && ARGS[i + 1].includes('=')) { const [k, ...v] = ARGS[i + 1].split('='); process.env[k] = v.join('='); ARGS.splice(i, 2); i--; }
const JSX = path.resolve(ARGS[0] || 'Build.jsx');
const ISSUES = [], STATS = { comps: 0, layers: 0, keys: 0, exprs: 0, mattes: 0, lctrl: 0 };
const issue = m => ISSUES.push(m);

const PVT = { OneD: 'OneD', TwoD: 'TwoD', ThreeD: 'ThreeD', TwoD_SPATIAL: 'TwoD_SPATIAL', ThreeD_SPATIAL: 'ThreeD_SPATIAL', COLOR: 'COLOR', SHAPE: 'SHAPE', TEXT_DOCUMENT: 'TEXT_DOCUMENT', NO_VALUE: 'NO_VALUE', MARKER: 'MARKER', LAYER_INDEX: 'LAYER_INDEX', CUSTOM_VALUE: 'CUSTOM_VALUE' };
function typeFor(m, parent) {
  const map = { 'ADBE Position': 'TwoD_SPATIAL', 'ADBE Anchor Point': 'TwoD_SPATIAL', 'ADBE Position_0': 'OneD', 'ADBE Position_1': 'OneD', 'ADBE Scale': 'ThreeD', 'ADBE Rotate Z': 'OneD', 'ADBE Opacity': 'OneD',
    'ADBE Mask Expansion': 'OneD', 'ADBE Mask Shape': 'SHAPE', 'ADBE Vector Shape': 'SHAPE', 'ADBE Vector Rect Size': 'TwoD', 'ADBE Vector Rect Position': 'TwoD_SPATIAL', 'ADBE Vector Rect Roundness': 'OneD',
    'ADBE Vector Ellipse Size': 'TwoD', 'ADBE Vector Ellipse Position': 'TwoD_SPATIAL', 'ADBE Vector Fill Color': 'COLOR', 'ADBE Vector Stroke Color': 'COLOR', 'ADBE Vector Fill Opacity': 'OneD', 'ADBE Vector Stroke Width': 'OneD',
    'ADBE Vector Stroke Opacity': 'OneD', 'ADBE Vector Trim Start': 'OneD', 'ADBE Vector Trim End': 'OneD', 'ADBE Vector Trim Offset': 'OneD', 'ADBE Text Document': 'TEXT_DOCUMENT', 'ADBE Text Expressible Amount': 'ThreeD',
    'ADBE Text Position 3D': 'ThreeD_SPATIAL', 'ADBE Text Scale 3D': 'ThreeD', 'ADBE Text Opacity': 'OneD', 'ADBE Text Rotation': 'OneD', 'ADBE Vector Position': 'TwoD_SPATIAL', 'ADBE Vector Rotation': 'OneD',
    'ADBE Vector Fill Rule': 'OneD', 'ADBE Vector Stroke Line Cap': 'OneD', 'ADBE Vector Stroke Line Join': 'OneD', 'ADBE Vector Stroke Dash 1': 'OneD', 'ADBE Vector Stroke Gap 1': 'OneD', 'ADBE Marker': 'MARKER' };
  if (map[m]) return map[m];
  if (parent && parent.isEffect) { const em = parent.matchName; if (em === 'ADBE Point Control') return 'TwoD_SPATIAL'; if (em === 'ADBE Layer Control') return 'LAYER_INDEX'; if (em === 'ADBE Drop Shadow') return m === 1 ? 'COLOR' : 'OneD'; return 'OneD'; }
  return 'NO_VALUE';
}
let REALM = a => a;
function defVal(t) { const v = { OneD: 0, TwoD: [0, 0], ThreeD: [100, 100, 100], TwoD_SPATIAL: [0, 0], ThreeD_SPATIAL: [0, 0, 0], COLOR: [1, 1, 1, 1], LAYER_INDEX: 0 }[t]; return Array.isArray(v) ? REALM(v) : v; }
function hasNaN(v) { if (Array.isArray(v)) return v.some(hasNaN); if (typeof v === 'number') return !isFinite(v); return false; }
function easeDims(t) { if (t === 'TwoD_SPATIAL' || t === 'ThreeD_SPATIAL') return 1; if (t === 'ThreeD') return 3; if (t === 'TwoD') return 2; return 1; }

const INDEXED = new Set(['ADBE Root Vectors Group', 'ADBE Vectors Group', 'ADBE Effect Parade', 'ADBE Mask Parade', 'ADBE Text Animators', 'ADBE Text Selectors', 'ADBE Text Animator Properties']);
function handle(p) {   // a reference that dies if its parent indexed group changes after it was taken
  const par = p.parentProperty; if (!par || !INDEXED.has(par.matchName)) return p;
  const gen = par.gen || 0;
  return new Proxy(p, { get(t, k) { if (k === '__raw') return t; if ((par.gen || 0) !== gen) { STALE++; throw new Error('Object is invalid (stale handle to ' + t.name + ')'); } const v = t[k]; return typeof v === 'function' ? v.bind(t) : v; },
    set(t, k, v) { if ((par.gen || 0) !== gen) { STALE++; throw new Error('Object is invalid (stale handle to ' + t.name + ')'); } t[k] = v; return true; } });
}
const KNOWN = {
  'ADBE Mask Atom': ['ADBE Mask Shape', 'ADBE Mask Feather', 'ADBE Mask Opacity', 'ADBE Mask Offset'],
  'ADBE Transform Group': ['ADBE Anchor Point', 'ADBE Position', 'ADBE Position_0', 'ADBE Position_1', 'ADBE Position_2', 'ADBE Scale', 'ADBE Orientation', 'ADBE Rotate X', 'ADBE Rotate Y', 'ADBE Rotate Z', 'ADBE Opacity'],
  'ADBE Vector Shape - Rect': ['ADBE Vector Shape Direction', 'ADBE Vector Rect Size', 'ADBE Vector Rect Position', 'ADBE Vector Rect Roundness'],
  'ADBE Vector Shape - Ellipse': ['ADBE Vector Shape Direction', 'ADBE Vector Ellipse Size', 'ADBE Vector Ellipse Position'],
  'ADBE Vector Shape - Group': ['ADBE Vector Shape Direction', 'ADBE Vector Shape'],
  'ADBE Vector Graphic - Fill': ['ADBE Vector Blend Mode', 'ADBE Vector Composite Order', 'ADBE Vector Fill Rule', 'ADBE Vector Fill Color', 'ADBE Vector Fill Opacity'],
  'ADBE Vector Graphic - Stroke': ['ADBE Vector Blend Mode', 'ADBE Vector Composite Order', 'ADBE Vector Stroke Color', 'ADBE Vector Stroke Opacity', 'ADBE Vector Stroke Width', 'ADBE Vector Stroke Line Cap', 'ADBE Vector Stroke Line Join', 'ADBE Vector Stroke Miter Limit', 'ADBE Vector Stroke Dashes', 'ADBE Vector Stroke Taper', 'ADBE Vector Stroke Wave'],
  'ADBE Vector Filter - Trim': ['ADBE Vector Trim Start', 'ADBE Vector Trim End', 'ADBE Vector Trim Offset', 'ADBE Vector Trim Type'],
  'ADBE Vector Group': ['ADBE Vector Blend Mode', 'ADBE Vectors Group', 'ADBE Vector Transform Group'],
  'ADBE Vector Transform Group': ['ADBE Vector Anchor', 'ADBE Vector Position', 'ADBE Vector Scale', 'ADBE Vector Skew', 'ADBE Vector Skew Axis', 'ADBE Vector Rotation', 'ADBE Vector Group Opacity'],
  'ADBE Text Animator': ['ADBE Text Selectors', 'ADBE Text Animator Properties'],
  'ADBE Text Expressible Selector': ['ADBE Text Selector Mode', 'ADBE Text Expressible Amount', 'ADBE Text Range Type2'],
  'ADBE Text Properties': ['ADBE Text Document', 'ADBE Text Path Options', 'ADBE Text More Options', 'ADBE Text Animators'],
};
const ROOTS = ['ADBE Transform Group', 'ADBE Effect Parade', 'ADBE Root Vectors Group', 'ADBE Mask Parade', 'ADBE Text Properties', 'ADBE Marker', 'ADBE Time Remapping', 'ADBE Audio Group'];
let BADNAME = 0;
class Prop {
  constructor(m, parent, layer) { this.matchName = m; this.name = m; this.parentProperty = parent; this.layer = layer; this.children = []; this.keys = []; this._expr = ''; this.expressionError = ''; this.dimensionsSeparated = false;
    this.isEffect = parent && parent.matchName === 'ADBE Effect Parade'; this._type = null; }
  get propertyValueType() { if (!this._type) this._type = typeFor(this.matchName, this.parentProperty); return this._type; }
  get value() { if (this._value === undefined) this._value = defVal(this.propertyValueType); if (this.propertyValueType === 'TEXT_DOCUMENT' && !this._value) this._value = new TextDocument(''); return this._value; }
  set value(v) { this._value = v; }
  property(k) {
    if (typeof k === 'number') { while (this.children.length < k) { const p = new Prop(this.children.length + 1, this, this.layer); this.children.push(p); } return handle(this.children[k - 1]); }
    let c = this.children.find(p => p.name === k || p.matchName === k);
    if (!c) {
      const allowed = KNOWN[this.matchName] || (this.matchName === 'root' ? ROOTS : null);
      if (allowed && allowed.indexOf(k) < 0) { BADNAME++; issue(`unknown property "${k}" asked from ${this.matchName} on ${this.layer ? this.layer.containingComp.name + ' > ' + this.layer.name : '?'}`); return null; }
      if (INDEXED.has(this.matchName)) return null;   // named child that does not exist -> null, as in AE
      c = new Prop(k, this, this.layer); this.children.push(c);
    }
    return handle(c);
  }
  addProperty(m) { if (INDEXED.has(this.matchName)) this.gen = (this.gen || 0) + 1; if (process.env.BREAK && m === (process.env.BREAK === '1' ? 'ADBE Drop Shadow' : process.env.BREAK)) throw new Error('simulated AE error adding ' + m); const p = new Prop(m, this, this.layer); this.children.push(p); return handle(p); }
  get numProperties() { return this.children.length; }
  moveTo(i) { const par = this.parentProperty; if (INDEXED.has(par.matchName)) par.gen = (par.gen || 0) + 1; const a = par.children; a.splice(a.indexOf(this), 1); a.splice(i - 1, 0, this); }
  setValue(v) { if (hasNaN(v)) issue(`NaN value on ${this.where()}`); this._value = v; }
  setValueAtTime(t, v) { if (!isFinite(t)) issue(`bad key time on ${this.where()}`); if (hasNaN(v)) issue(`NaN key value on ${this.where()} at ${t}`);
    if (this.keys.some(k => Math.abs(k.t - t) < 1e-6)) issue(`two keys on the same frame (${t.toFixed(2)}s) on ${this.where()}`);
    this.keys.push({ t, v }); this.keys.sort((a, b) => a.t - b.t); this._value = v; STATS.keys++; }
  nearestKeyIndex(t) { let best = 0, d = 1e9; this.keys.forEach((k, i) => { if (Math.abs(k.t - t) < d) { d = Math.abs(k.t - t); best = i; } }); return best + 1; }
  get holdOnly() { const p = this.parentProperty; return !!(p && p.isEffect && (p.matchName === 'ADBE Checkbox Control' || p.matchName === 'ADBE Dropdown Control')); }
  isInterpolationTypeValid(t) { return this.holdOnly ? t === 2 : true; }
  setInterpolationTypeAtKey(k, a, b) { if (this.holdOnly && (a !== 2 || (b !== undefined && b !== 2))) throw new Error('After Effects error: Invalid interpolation type for this property.'); }
  setTemporalEaseAtKey(k, inE, outE) { this.eases = this.eases || {}; this.eases[k] = [inE.map(e => [e.speed, e.influence]), outE.map(e => [e.speed, e.influence])]; if (this.holdOnly) throw new Error('no eases on hold-only property'); let d = easeDims(this.propertyValueType); if (process.env.SCALE2 && this.matchName === 'ADBE Scale') d = 2;
    if (inE.length !== d || outE.length !== d) { EASE_THROWS++; throw new Error('wrong number of eases'); }
    inE.concat(outE).forEach(e => { if (!isFinite(e.speed) || !(e.influence >= 0.1 && e.influence <= 100)) issue(`bad ease ${JSON.stringify(e)} on ${this.where()}`); }); }
  set expression(t) { this._expr = t; STATS.exprs++; }
  get expression() { return this._expr; }
  where() { let n = [], p = this; while (p && p.parentProperty) { n.unshift(p.name); p = p.parentProperty; } return `${this.layer ? this.layer.containingComp.name + ' > ' + this.layer.name : '?'} > ${n.join('/')}`; }
}
class TextDocument { constructor(t) { this.text = t; } resetCharStyle() { } resetParagraphStyle() { } }
class Layer {
  constructor(comp, kind, src, text) { this.containingComp = comp; this.kind = kind; this.source = src; this.root = new Prop('root', null, this); this.name = kind; this.enabled = true; this.label = 0; this.parent = null; this._matte = null;
    this.startTime = 0; this.inPoint = 0; this.outPoint = comp.duration; this.text = text || ''; this.guideLayer = false; this.locked = false; this.preserveTransparency = false; this.threeDLayer = false; STATS.layers++;
    if (kind === 'text') this.root.property('ADBE Text Properties').property('ADBE Text Document')._value = new TextDocument(text); }
  property(k) { return this.root.property(k); }
  get index() { return this.containingComp._layers.indexOf(this) + 1; }
  set startTime(t) { this._st = t; if (this.source && this.source.sequence) { this.inPoint = t; this.outPoint = t + this.source.duration; } }
  get startTime() { return this._st; }
  setParentWithJump(p) { if (p.containingComp !== this.containingComp) issue(`parent in another comp: ${this.name}`); this.parent = p; }
  moveToBeginning() { const a = this.containingComp._layers; a.splice(a.indexOf(this), 1); a.unshift(this); }
  moveBefore(o) { const a = this.containingComp._layers; a.splice(a.indexOf(this), 1); a.splice(a.indexOf(o), 0, this); }
  sourceRectAtTime() { const d = this.kind === 'text' ? this.property('ADBE Text Properties').property('ADBE Text Document').value : null, s = d && d.fontSize ? d.fontSize : 20, w = (d && d.text ? d.text.length : 5) * s * 0.62;
    return { left: d && d.justification === 'L' ? 0 : -w / 2, top: -s * 0.72, width: w, height: s * 0.72 }; }
  setTrackMatte(m, type) { this._matte = m; this._mtype = type; }
  get hasTrackMatte() { return !!this._matte; }
  get trackMatteLayer() { return this._matte; }
  remove() { const a = this.containingComp._layers; a.splice(a.indexOf(this), 1); STATS.layers--; }
}
class Comp {
  constructor(name, w, h, pa, dur, fps) { this.name = name; this.width = w; this.height = h; this.duration = dur; this.frameRate = fps; this._layers = []; this.id = Math.random(); STATS.comps++; COMPS.push(this);
    if (!(w > 0 && h > 0 && dur > 0)) issue(`bad comp settings ${name}`); const me = this;
    this.layers = { add: (item) => { const L = new Layer(me, 'av', item); L.name = item && item.name || 'item'; me._layers.unshift(L); if (item && item.sequence) { L.inPoint = 0; L.outPoint = item.duration; } return L; },
      addNull: () => { const L = new Layer(me, 'null'); me._layers.unshift(L); return L; }, addShape: () => { const L = new Layer(me, 'shape'); me._layers.unshift(L); return L; },
      addText: (t) => { const L = new Layer(me, 'text', null, t); me._layers.unshift(L); return L; }, addSolid: (c, n) => { const L = new Layer(me, 'solid', { name: n, duration: 23 }); me._layers.unshift(L); return L; } }; }
  get numLayers() { return this._layers.length; }
  layer(i) { return this._layers[i - 1]; }
  openInViewer() { } remove() { COMPS.splice(COMPS.indexOf(this), 1); STATS.comps--; }
}
const COMPS = []; let EASE_THROWS = 0, STALE = 0;
function File(p) { if (!(this instanceof File)) return new File(p); this.fsName = p; this.exists = fs.existsSync(p); this.path = path.dirname(p); }
Object.defineProperty(File.prototype, 'parent', { get() { return new File(path.dirname(this.fsName)); } });
File.prototype.open = function () { this._buf = ''; return true; }; File.prototype.write = function (t) { this._buf += t; LOGFILE = this._buf; }; File.prototype.close = function () { };
function Folder(p) { if (!(this instanceof Folder)) return new Folder(p); this.fsName = p; this.exists = fs.existsSync(p); }
Folder.desktop = new Folder('/tmp'); Folder.prototype.execute = function () { return true; }; let PROMPTED = 0, LOGFILE = '';
Folder.selectDialog = () => { PROMPTED++; return new Folder(__dirname); };
File.openDialog = () => new File(process.env.FOOTAGE || JSX);   // any existing file stands in for the picked footage
function ImportOptions(f) { this.file = f; this.sequence = false; }
let ALERT = '';
const sandbox = {
  app: { version: '24.6.0', beginUndoGroup() { }, endUndoGroup() { }, newProject() { },
    project: { items: { addComp: (...a) => new Comp(...a), addFolder: n => ({ name: n }),
      }, importFile: io => { if (!io.file.exists) issue('import of missing file ' + io.file.fsName); return { name: path.basename(io.file.fsName), sequence: io.sequence, duration: io.sequence ? 68 / 25 : 22.38, mainSource: {} }; } } },
  File, Folder, ImportOptions, $: { fileName: process.env.ELSEWHERE ? '/tmp/elsewhere/COH_AE_Rebuild.jsx' : JSX }, alert: m => { ALERT = m; },
  Shape: function () { }, KeyframeEase: function (s, i) { this.speed = s; this.influence = i; }, MarkerValue: function (c) { this.comment = c; },
  PropertyValueType: PVT, KeyframeInterpolationType: { BEZIER: 1, HOLD: 2, LINEAR: 3 }, TrackMatteType: { ALPHA: 'A', ALPHA_INVERTED: 'AI', LUMA: 'L', LUMA_INVERTED: 'LI' },
  ParagraphJustification: { CENTER_JUSTIFY: 'C', LEFT_JUSTIFY: 'L' }
};
sandbox.app.project.importFile = sandbox.app.project.items.importFile || sandbox.app.project.importFile;
sandbox.app.project.importFile = io => { if (!io.file.exists) issue('import of missing file ' + io.file.fsName); return { name: path.basename(io.file.fsName), sequence: io.sequence, duration: io.sequence ? 68 / 25 : 22.38, mainSource: {} }; };
// ES3 guard: ExtendScript has no let/const/arrow/forEach/map/JSON
const src = fs.readFileSync(JSX, 'utf8');
const code = src.replace(/"(?:[^"\\]|\\.)*"/g, '""').replace(/\/\/[^\n]*/g, '');
[[/\blet\s/, 'let'], [/\bconst\s/, 'const'], [/=>/, 'arrow function'], [/\.forEach\(/, 'forEach'], [/\.map\(/, 'map'], [/\bJSON\./, 'JSON'], [/`/, 'template string']].forEach(([re, n]) => { if (re.test(code)) issue('not ES3: ' + n); });
const ctx = vm.createContext(sandbox);
REALM = vm.runInContext('(function (a) { return Array.prototype.slice.call(a); })', ctx);

// ExtendScript (ES3) extras: reserved words as names, trailing commas, ES5+ methods
const RES = 'abstract boolean byte char class const debugger default delete do double enum export extends final float goto implements import in instanceof int interface long native package private protected public short static super synchronized throws transient volatile with'.split(' ');
RES.forEach(w => { if (new RegExp('\\.\\s*' + w + '\\b').test(code) || new RegExp('[{,]\\s*' + w + '\\s*:').test(code)) issue('ES3 reserved word used as a name: ' + w); });
if (/,\s*[}\]]/.test(code)) issue('trailing comma (syntax error in ExtendScript)');
[[/\bArray\.isArray\b/, 'Array.isArray'], [/\bObject\.keys\b/, 'Object.keys'], [/\.trim\(\)/, 'String.trim'], [/\.bind\(/, 'bind'], [/\.filter\(/, 'filter'], [/\.reduce\(/, 'reduce'], [/\.some\(/, 'some'], [/\.every\(/, 'every']].forEach(([re, n]) => { if (re.test(code)) issue('ES5+ method not in ExtendScript: ' + n); });
// arrays have no indexOf in ExtendScript: flag indexOf on anything that is not obviously a string (.name / string literal)
(code.match(/[\w\])]+\.indexOf\(/g) || []).forEach(m => { if (!/name\.indexOf\($/.test(m)) issue('check indexOf use (arrays lack it in ExtendScript): ' + m); });

vm.runInContext(src, ctx, { filename: 'COH_AE_Rebuild.jsx' });

// ---- post checks
function walk(p, f) { f(p); p.children.forEach(c => walk(c, f)); }
COMPS.forEach(c => {
  const names = new Set(c._layers.map(l => l.name));
  const dup = c._layers.map(l => l.name).filter((n, i, a) => a.indexOf(n) !== i && /^(CTRL_|CAM_|MATTE_|Card_|Band_|Tile_|Slider_|Clip_|GRP_)/.test(n));
  if (dup.length) issue(`${c.name}: duplicate layer names ${[...new Set(dup)].join(', ')}`);
  c._layers.forEach(L => {
    if (L._matte) { STATS.mattes++; const M = L._matte; if (M.containingComp !== c) issue(`${c.name} > ${L.name}: matte in another comp`); if (/^MATTE_/.test(M.name) && M.enabled) issue(`${M.name} renders`);
      if (M.inPoint > L.inPoint + 1e-3 || M.outPoint < L.outPoint - 1e-3) issue(`${c.name}: ${M.name} shorter than ${L.name}`); }
    const fxp = L.root.children.find(p => p.matchName === 'ADBE Effect Parade');
    const fxNames = fxp ? fxp.children.map(e => e.name) : [];
    if (fxp) fxp.children.filter(e => e.matchName === 'ADBE Layer Control').forEach(e => { STATS.lctrl++; const v = e.property(1)._value; if (!v || !c._layers[v - 1]) issue(`${c.name} > ${L.name}: layer control '${e.name}' not set`); });
    walk(L.root, p => {
      const t = p._expr; if (!t) return;
      try { new Function('value', 'time', t); } catch (e) { issue(`${p.where()}: expression does not compile: ${e.message}`); }
      const vars = {}; let m; const rv = /var\s+(\w+)\s*=\s*thisComp\.layer\("([^"]+)"\)/g; while ((m = rv.exec(t))) vars[m[1]] = m[2];
      const rl = /thisComp\.layer\("([^"]+)"\)/g; while ((m = rl.exec(t))) if (!names.has(m[1])) issue(`${p.where()}: refers to missing layer "${m[1]}"`);
      const re1 = /thisComp\.layer\("([^"]+)"\)\.effect\("([^"]+)"\)/g; while ((m = re1.exec(t))) { const Lr = c._layers.find(l => l.name === m[1]); if (Lr && !hasFx(Lr, m[2])) issue(`${p.where()}: layer "${m[1]}" has no effect "${m[2]}"`); }
      const re2 = /(\w+)\.effect\("([^"]+)"\)/g; while ((m = re2.exec(t))) { if (vars[m[1]]) { const Lr = c._layers.find(l => l.name === vars[m[1]]); if (Lr && !hasFx(Lr, m[2])) issue(`${p.where()}: layer "${vars[m[1]]}" has no effect "${m[2]}"`); } }
      const re3 = /(^|[^.\w])effect\("([^"]+)"\)/g; while ((m = re3.exec(t))) if (!fxNames.includes(m[2])) issue(`${p.where()}: own effect "${m[2]}" missing`);
      // usability for non-coders: anything that moves on its own must be steerable from controls
      const body = t.replace(/\/\/[^\n]*/g, '');
      if (/\btime\b/.test(body) && /Math\.(exp|pow|sin|cos)|\bease\(|\blinear\(|wiggle\(/.test(body) && !/effect\(/.test(body))
        issue(`${p.where()}: moves over time with NO controls - expose amount/speed/timing as sliders (or use keys)`);
      // hidden easing: a 0..1 progress run through pow/exp/cos inside the code = an ease the designer can't see or edit
      if (/Math\.(pow|exp)\(\s*-?\s*\(?\s*1?\s*-?\s*\d*\s*\*?\s*\b(p|u|prog|progress)\b/.test(body) || /Math\.pow\(\s*1\s*-\s*(p|u|prog|progress)\b/.test(body))
        issue(`${p.where()}: hidden easing curve inside the expression - put the curve in KEYFRAMES on the driver slider (graph editor), keep the expression linear`);
      if (!/^\s*\/\/ /.test(t)) issue(`${p.where()}: expression must start with a plain-English '// WHAT it does. Controls: ...' line`);
    });
  });
});
function hasFx(L, n) { const fxp = L.root.children.find(p => p.matchName === 'ADBE Effect Parade'); return fxp && fxp.children.some(e => e.name === n); }
if (process.env.DUMP_KEYS) { const out = {}; COMPS.forEach(c => c._layers.forEach(L => walk(L.root, p => { if (p.keys && p.keys.length > 1) out[c.name + ' > ' + L.name + ' > ' + p.name] = { keys: p.keys, eases: p.eases || {} }; }))); fs.writeFileSync(process.env.DUMP_KEYS, JSON.stringify(out)); }
console.log('ALERT FROM SCRIPT:\n' + ALERT + '\n'); console.log('asset-folder prompts:', PROMPTED, ' ease retries:', EASE_THROWS, ' stale handles:', STALE);
console.log('DRY-RUN STATS', JSON.stringify(STATS));
const uniq = [...new Set(ISSUES)].filter(m => !/nm\.indexOf\($/.test(m));
console.log(uniq.length ? 'ISSUES (' + uniq.length + '):\n - ' + uniq.slice(0, 80).join('\n - ') : 'NO ISSUES');
process.exitCode = uniq.length ? 1 : 0;
