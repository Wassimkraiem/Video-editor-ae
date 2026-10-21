"use client";

import { useEffect, useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import type { RunEvent } from "../lib/agent-events";
import { mediaUrl, type Asset, type BrandKit, type Run, type Skill } from "../lib/api-client";
import { AgentPanel, stylesFrom, type Intensity, type StartOptions, type VideoKind } from "./AgentPanel";
import { ResourcePicker, isResource } from "./ResourcePicker";
import { StylePreview } from "./StylePreview";
import { Badge, Button, Card, Empty, Input, Spinner, Textarea, formatDuration } from "./ui";
import { AlertIcon, CheckIcon, ChevronIcon, FilmIcon, LayersIcon, SparkIcon, UploadIcon } from "./icons";
import { TranscriptEditor } from "./TranscriptEditor";

export type Step = 1 | 2 | 3 | 4;

const KINDS: { id: VideoKind; title: string; hint: string; icon: ReactNode }[] = [
  { id: "people", title: "Talking head / ad", hint: "You (or someone) on camera: talking, selling, advertising. One or more clips, cut and edited for you.", icon: <FilmIcon width={22} height={22} /> },
  { id: "motion", title: "Motion graphics", hint: "No footage: a fully designed video from your script or idea.", icon: <SparkIcon width={22} height={22} /> },
  { id: "product", title: "Product launch", hint: "No footage: launch or promo video for a product, app or feature.", icon: <LayersIcon width={22} height={22} /> },
];

// Which styles fit which kind of video; anything unlisted shows everywhere.
const STYLE_KIND: Record<string, VideoKind[]> = {
  "auto-style": ["people", "motion", "product"],
  // Marketing formats (docs/marketing-video-playbook.md).
  "performance-ad": ["people", "motion", "product"],
  "ui-feature-reel": ["product", "motion"],
  "three-step-promo": ["product", "motion"],
  "kinetic-type-recap": ["motion", "product", "people"],
  "teaser-countdown": ["product", "motion"],
  "offer-ad": ["people", "product"],
  "testimonial-proof": ["people"],
  "listicle-explainer": ["people", "motion"],
  "wassim-style": ["people"],
  "devin-style": ["people"],
  "talking-head-glass-edit": ["people"],
  "talking-head-recut": ["people"],
  "kinetic-editorial-reel": ["motion"],
  "general-video": ["motion", "product"],
  "product-launch-motion": ["product"],
  "product-launch-video": ["product"],
};

// What a style can be picked for: its captions, its motion and graphics, or both (the default).
const STYLE_ROLE: Record<string, "captions" | "motion"> = {
  "perfect-caption": "captions",
  "kinetic-editorial-reel": "motion",
  "product-launch-motion": "motion",
  "product-launch-video": "motion",
  "general-video": "motion",
};
const canDoCaptions = (name: string) => STYLE_ROLE[name] !== "motion" && name !== "auto-style";
const canDoMotion = (name: string) => STYLE_ROLE[name] !== "captions";

const EMPTY_BRAND: BrandKit = { colors: [], fonts: [], notes: "" };

/** The brand kit, remembered per project in this browser. */
function useBrandKit(projectId?: string) {
  const key = `brand-kit:${projectId ?? "none"}`;
  const [brand, setBrand] = useState<BrandKit>(EMPTY_BRAND);
  useEffect(() => {
    try { const saved = window.localStorage.getItem(key); setBrand(saved ? { ...EMPTY_BRAND, ...JSON.parse(saved) } : EMPTY_BRAND); } catch { setBrand(EMPTY_BRAND); }
  }, [key]);
  const update = (next: BrandKit) => {
    setBrand(next);
    try { window.localStorage.setItem(key, JSON.stringify(next)); } catch { /* private mode: keep it for this session */ }
  };
  return [brand, update] as const;
}

function BrandKitFields({ brand, onChange }: { brand: BrandKit; onChange: (brand: BrandKit) => void }) {
  const fonts = [brand.fonts[0] ?? "", brand.fonts[1] ?? ""];
  const setFont = (index: number, value: string) => {
    const next = [...fonts];
    next[index] = value;
    onChange({ ...brand, fonts: next.filter((font, position) => font.trim() || position < next.length - 1).map((font) => font.trim()).filter(Boolean) });
  };
  return (
    <div className="space-y-2 rounded-xl border border-line p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-300">Brand kit <span className="font-normal text-slate-500">(optional, overrides the style's colours and fonts)</span></span>
        {(brand.colors.length > 0 || brand.fonts.length > 0 || brand.notes) && <button className="text-[11px] text-slate-500 hover:text-white" onClick={() => onChange(EMPTY_BRAND)}>Clear</button>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {brand.colors.map((color, index) => (
          <span key={index} className="group relative">
            <input type="color" aria-label={`Colour ${index + 1}`} value={color} onChange={(event) => onChange({ ...brand, colors: brand.colors.map((item, position) => (position === index ? event.target.value.toUpperCase() : item)) })} className="h-8 w-8 cursor-pointer rounded-md border border-line bg-transparent" />
            <button aria-label="Remove colour" onClick={() => onChange({ ...brand, colors: brand.colors.filter((_, position) => position !== index) })} className="absolute -right-1.5 -top-1.5 hidden h-4 w-4 items-center justify-center rounded-full bg-black text-[10px] text-white group-hover:flex">×</button>
          </span>
        ))}
        {brand.colors.length < 6 && <button onClick={() => onChange({ ...brand, colors: [...brand.colors, brand.colors.length ? "#FFFFFF" : "#3B82F6"] })} className="h-8 rounded-md border border-dashed border-line px-2 text-[11px] text-slate-400 hover:border-accent/50 hover:text-white">+ colour</button>}
        <span className="text-[10px] text-slate-500">{brand.colors.length ? "first = accent" : "none: the style's palette"}</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        <Input className="h-8 text-xs" placeholder="Headline font (e.g. Montserrat)" value={fonts[0]} onChange={(event) => setFont(0, event.target.value)} />
        <Input className="h-8 text-xs" placeholder="Text font (e.g. Inter)" value={fonts[1]} onChange={(event) => setFont(1, event.target.value)} />
      </div>
      <Input className="h-8 text-xs" placeholder="Brand notes (e.g. premium, no emojis, logo bottom-right)" value={brand.notes} onChange={(event) => onChange({ ...brand, notes: event.target.value })} />
    </div>
  );
}

const INTENSITIES: { id: Intensity; title: string; hint: string }[] = [
  { id: "minimal", title: "Minimal", hint: "Clean captions, few graphics" },
  { id: "balanced", title: "Balanced", hint: "The style as designed" },
  { id: "bold", title: "Bold", hint: "Full effects" },
];

function prettyName(name: string) {
  return name.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function stylesFor(kind: VideoKind, skills: Skill[]) {
  return stylesFrom(skills).filter((style) => {
    const kinds = STYLE_KIND[style.name] ?? (style.scope === "user" ? ["people"] : null);
    return !kinds || kinds.includes(kind);
  });
}

function Stepper({ steps, current, reachable, onGo }: { steps: { step: Step; title: string; hint: string }[]; current: Step; reachable: (step: Step) => boolean; onGo: (step: Step) => void }) {
  return (
    <ol className="flex items-center gap-2">
      {steps.map((item, index) => {
        const done = item.step < current;
        const active = item.step === current;
        return (
          <li key={item.step} className="flex flex-1 items-center gap-2">
            <button disabled={!reachable(item.step)} onClick={() => onGo(item.step)} className={`flex min-w-0 flex-1 items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${active ? "border-accent/60 bg-accent/15" : "border-line bg-white/[0.02] hover:bg-white/[0.05]"}`}>
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${active ? "bg-accent text-white shadow-glow" : done ? "bg-emerald-500/20 text-emerald-300" : "bg-white/[0.06] text-slate-400"}`}>{done ? <CheckIcon width={14} height={14} /> : index + 1}</span>
              <span className="min-w-0">
                <span className={`block text-sm font-medium ${active ? "text-white" : "text-slate-300"}`}>{item.title}</span>
                <span className="block truncate text-[11px] text-slate-500">{item.hint}</span>
              </span>
            </button>
            {index < steps.length - 1 && <span className="hidden h-px w-4 shrink-0 bg-line xl:block" />}
          </li>
        );
      })}
    </ol>
  );
}

function transcriptLabel(clip: Asset) {
  return clip.transcript_reviewed ? "approved" : clip.transcript_status === "ready" ? "to check" : clip.transcript_status ?? "processing";
}

/** Step 1: what kind of video, and for people videos the clips in order. */
function StartStep({ kind, onKind, clips, selected, onSelected, onUpload, onContinue }: {
  kind: VideoKind;
  onKind: (kind: VideoKind) => void;
  clips: Asset[];
  selected: string[];
  onSelected: (ids: string[]) => void;
  onUpload: (files: File[]) => Promise<Asset[]>;
  onContinue: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const toggle = (id: string) => onSelected(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  const move = (id: string, by: number) => {
    const next = [...selected];
    const from = next.indexOf(id);
    const to = from + by;
    if (from < 0 || to < 0 || to >= next.length) return;
    [next[from], next[to]] = [next[to], next[from]];
    onSelected(next);
  };

  async function upload(files: File[]) {
    if (!files.length) return;
    setUploading(true);
    setError("");
    try {
      const added = await onUpload(files);
      onSelected([...selected, ...added.map((asset) => asset.id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  }

  const ordered = selected.map((id) => clips.find((clip) => clip.id === id)).filter((clip): clip is Asset => Boolean(clip));

  return (
    <div className="space-y-6">
      <div className="grid gap-3 md:grid-cols-3">
        {KINDS.map((item) => (
          <button key={item.id} onClick={() => onKind(item.id)} className={`flex items-start gap-3 rounded-2xl border p-4 text-left transition ${kind === item.id ? "border-accent/60 bg-accent/10 shadow-glow" : "border-line bg-white/[0.02] hover:border-accent/40"}`}>
            <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${kind === item.id ? "bg-accent text-white" : "bg-white/[0.06] text-slate-300"}`}>{item.icon}</span>
            <span>
              <span className="block text-sm font-semibold text-white">{item.title}</span>
              <span className="mt-1 block text-xs leading-relaxed text-slate-400">{item.hint}</span>
            </span>
          </button>
        ))}
      </div>

      {kind === "people" ? (
        <>
          <button
            type="button"
            onClick={() => input.current?.click()}
            onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
            className={`flex w-full flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-6 py-10 text-center transition ${dragging ? "border-accent bg-accent/10" : "border-slate-600/50 bg-white/[0.02] hover:border-accent/60 hover:bg-accent/[0.04]"}`}
          >
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent/15 text-accent-soft">{uploading ? <Spinner /> : <UploadIcon width={24} height={24} />}</span>
            <span className="text-base font-semibold text-white">{uploading ? "Uploading…" : "Drop one or more clips here"}</span>
            <span className="text-sm text-slate-400">Each clip is transcribed right after the upload. Several clips are cut and joined in the order you set below.</span>
          </button>
          <input ref={input} className="hidden" type="file" accept="video/*" multiple onChange={(event) => { void upload(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
          {error && <p className="text-sm text-red-300">{error}</p>}

          {ordered.length > 0 && (
            <Card title={`In this video (${ordered.length}), in order`}>
              <ol className="divide-y divide-line">
                {ordered.map((clip, index) => (
                  <li key={clip.id} className="flex items-center gap-3 px-4 py-2.5">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-semibold text-white">{index + 1}</span>
                    <span className="h-12 w-8 shrink-0 overflow-hidden rounded bg-black">{clip.thumbnail_url && <img src={mediaUrl(clip.thumbnail_url)} alt="" className="h-full w-full object-cover" />}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-slate-200">{clip.filename}</span>
                      <span className="block text-[11px] text-slate-500">{formatDuration(clip.probe?.duration_ms)} · transcript {transcriptLabel(clip)}</span>
                    </span>
                    <button aria-label="Move up" disabled={index === 0} onClick={() => move(clip.id, -1)} className="rounded-md p-1.5 text-slate-400 hover:bg-white/[0.06] hover:text-white disabled:opacity-30"><ChevronIcon width={14} height={14} className="-rotate-90" /></button>
                    <button aria-label="Move down" disabled={index === ordered.length - 1} onClick={() => move(clip.id, 1)} className="rounded-md p-1.5 text-slate-400 hover:bg-white/[0.06] hover:text-white disabled:opacity-30"><ChevronIcon width={14} height={14} className="rotate-90" /></button>
                    <button onClick={() => toggle(clip.id)} className="rounded-md px-2 py-1 text-[11px] text-slate-400 hover:bg-white/[0.06] hover:text-white">Remove</button>
                  </li>
                ))}
              </ol>
            </Card>
          )}

          {clips.some((clip) => !selected.includes(clip.id)) && (
            <div>
              <p className="mb-3 text-sm font-medium text-slate-300">Add clips you already uploaded</p>
              <div className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
                {clips.filter((clip) => !selected.includes(clip.id)).map((clip) => (
                  <button key={clip.id} onClick={() => toggle(clip.id)} className="group overflow-hidden rounded-xl border border-line bg-black/30 text-left transition hover:border-accent/50">
                    <span className="relative block aspect-[9/12] bg-black">
                      {clip.thumbnail_url ? <img src={mediaUrl(clip.thumbnail_url)} alt="" className="h-full w-full object-cover transition group-hover:scale-[1.03]" /> : <span className="flex h-full items-center justify-center text-slate-600"><FilmIcon /></span>}
                    </span>
                    <span className="block p-2">
                      <span className="block truncate text-xs font-medium text-slate-200">{clip.filename}</span>
                      <span className="block text-[11px] text-slate-500">{formatDuration(clip.probe?.duration_ms)} · {transcriptLabel(clip)}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="rounded-2xl border border-line bg-white/[0.02] px-4 py-3 text-sm text-slate-400">No footage needed. Next you pick a style and write the brief or paste the script; images, logos, a voice-over or music can be attached there.</p>
      )}

      <div className="flex justify-end">
        <Button onClick={onContinue} disabled={kind === "people" && ordered.length === 0}>Continue</Button>
      </div>
    </div>
  );
}

/** Step 2: every selected clip's transcript, fixed (or replaced by the script) and approved. */
function TranscriptStep({ clips, focus, onFocus, assets, onChanged, onDone }: { clips: Asset[]; focus?: string; onFocus: (id: string) => void; assets: Asset[]; onChanged: () => void; onDone: () => void }) {
  const current = clips.find((clip) => clip.id === focus) ?? clips[0];
  function approved() {
    const next = clips.find((clip) => clip.id !== current?.id && !clip.transcript_reviewed);
    if (next) onFocus(next.id);
    else onDone();
  }
  if (!current) return null;
  return (
    <div className="space-y-4">
      {clips.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {clips.map((clip, index) => (
            <button key={clip.id} onClick={() => onFocus(clip.id)} className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs transition ${clip.id === current.id ? "border-accent/60 bg-accent/15 text-white" : "border-line text-slate-400 hover:text-white"}`}>
              <span className="font-semibold">{index + 1}</span>
              <span className="max-w-[160px] truncate">{clip.filename}</span>
              {clip.transcript_reviewed ? <CheckIcon width={12} height={12} className="text-emerald-300" /> : <span className="h-1.5 w-1.5 rounded-full bg-amber-300" />}
            </button>
          ))}
        </div>
      )}
      <TranscriptEditor key={current.id} assets={assets} assetId={current.id} onChanged={onChanged} onApproved={approved} />
    </div>
  );
}

function StyleStep({ projectId, kind, styles, clips, resources, onUploadResources, onStart, onBack }: {
  projectId?: string;
  kind: VideoKind;
  styles: Skill[];
  clips: Asset[];
  resources: Asset[];
  onUploadResources: (files: File[]) => Promise<Asset[]>;
  onStart: (brief: string, skill: string, options: StartOptions) => Promise<void>;
  onBack: () => void;
}) {
  const looks = styles.filter((style) => canDoMotion(style.name));
  // Built-in recipes (cleanup, reframe...) are tools, not caption looks.
  const captionStyles = styles.filter((style) => canDoCaptions(style.name) && style.scope !== "builtin");
  const [skill, setSkill] = useState(looks[0]?.name ?? "");
  const [captionSkill, setCaptionSkill] = useState("");
  const [brand, setBrand] = useBrandKit(projectId);
  const [brief, setBrief] = useState("");
  const [script, setScript] = useState("");
  const [intensity, setIntensity] = useState<Intensity>(kind === "people" ? "minimal" : "balanced");
  const [cut, setCut] = useState(true);
  const [attached, setAttached] = useState<string[]>([]);
  const [mode, setMode] = useState<"fast" | "agent">("fast");
  const [quick, setQuick] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const chosen = styles.find((style) => style.name === skill);
  const fast = Boolean(chosen?.fast);
  const effective = fast ? mode : "agent";
  const people = kind === "people";

  useEffect(() => { if (!looks.some((style) => style.name === skill)) setSkill(looks[0]?.name ?? ""); }, [looks, skill]);
  // A mix (or auto) runs on the generic engine: one call writes the whole video.
  const generic = Boolean(captionSkill && captionSkill !== skill) || chosen?.fast_engine !== "style";
  const auto = skill === "auto-style";

  async function start() {
    if (!people && !brief.trim() && !script.trim()) {
      setError("Describe the video or paste the script.");
      return;
    }
    setBusy(true);
    setError("");
    const look = auto ? "a look you design to fit the script" : prettyName(skill);
    const fallback = people ? `Edit ${clips.map((clip) => clip.filename).join(", ")} in ${look}.` : `Make the video in ${look}.`;
    try {
      await onStart(brief.trim() || fallback, skill, {
        mode: effective,
        assetId: clips[0]?.id,
        quick: effective === "fast" && quick,
        resources: attached,
        kind,
        intensity,
        clips: people ? clips.map((clip) => clip.id) : [],
        cut: people && cut,
        script: script.trim() || undefined,
        captionSkill: captionSkill && captionSkill !== skill ? captionSkill : null,
        brand: brand.colors.length || brand.fonts.length || brand.notes.trim() ? brand : null,
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the edit");
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
      <div>
        <p className="mb-3 text-sm font-medium text-slate-300">Look: motion & graphics</p>
        {looks.length === 0 ? (
          <Card><Empty icon={<SparkIcon />} title="No style for this type yet">Clone one in Styles from a video you like.</Empty></Card>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {looks.map((style) => {
              const selected = style.name === skill;
              const isAuto = style.name === "auto-style";
              return (
                <button key={style.id} onClick={() => setSkill(style.name)} className={`flex gap-3 rounded-2xl border p-3 text-left transition ${selected ? "border-accent/60 bg-accent/10 shadow-glow" : isAuto ? "border-dashed border-accent/40 bg-accent/[0.04] hover:border-accent/60" : "border-line bg-white/[0.02] hover:border-accent/40"}`}>
                  {!isAuto && <StylePreview skill={style} className="w-16" />}
                  <span className="flex min-w-0 flex-1 flex-col">
                  <span className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-white">{isAuto ? <span className="flex items-center gap-1.5"><SparkIcon width={14} height={14} className="text-accent-soft" /> Auto: Claude designs it</span> : prettyName(style.name)}</span>
                    {style.scope === "user" && <Badge tone="accent">cloned</Badge>}
                    <span className="ml-auto">{style.fast_engine === "style" ? <Badge tone="success">fast · tuned</Badge> : style.fast ? <Badge tone="success">fast</Badge> : <Badge>agent</Badge>}</span>
                  </span>
                  <span className="mt-2 line-clamp-4 text-xs leading-relaxed text-slate-400">{isAuto ? "No fixed style: Claude reads the script, picks the right kind of look and designs captions and graphics for it. Give it your colours and fonts in the brand kit." : style.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <Card title="Your edit" className="h-fit xl:sticky xl:top-4">
        <div className="space-y-4 p-4">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-200">Your ideas for this edit</span>
            <Textarea rows={6} placeholder={people ? "Write what you have in mind, Claude follows it:\n• the hook: show the price big at the start\n• put logo.png when I say the brand name\n• calm and premium, no emojis\n• end with 'comment LINK'" : kind === "product" ? "e.g. launch of our invoicing app: hook with the pain (late payments), 3 features with UI cards, dark look, CTA 'try it free'" : "e.g. 30s reel explaining why AI won't take your job: one idea per scene, a bold hook, end on a question"} value={brief} onChange={(event) => setBrief(event.target.value)} />
            <span className="mt-1 block text-[11px] text-slate-500">{people ? "Optional, but the more you say, the closer the first version." : "Required unless you paste a script."}</span>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-slate-400">Captions style</span>
            <select value={captionSkill} onChange={(event) => setCaptionSkill(event.target.value)} className="h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-slate-200 outline-none focus:border-accent/50">
              <option value="" className="bg-panel">{auto ? "Designed by Claude with the look" : `Same as the look (${prettyName(skill)})`}</option>
              {captionStyles.filter((style) => style.name !== skill).map((style) => <option key={style.id} value={style.name} className="bg-panel">{prettyName(style.name)}</option>)}
            </select>
          </label>

          <BrandKitFields brand={brand} onChange={setBrand} />
          {people ? (
            <div className="space-y-1.5 rounded-xl bg-black/30 p-2">
              {clips.map((clip, index) => (
                <div key={clip.id} className="flex items-center gap-2 text-xs">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/80 text-[10px] font-semibold text-white">{index + 1}</span>
                  <span className="min-w-0 flex-1 truncate text-slate-200">{clip.filename}</span>
                  <span className="flex items-center gap-1 text-[11px] text-emerald-300"><CheckIcon width={11} height={11} /> transcript</span>
                </div>
              ))}
              <label className="flex items-start gap-2 pt-1 text-[11px] text-slate-400">
                <input type="checkbox" className="mt-0.5" checked={cut} onChange={(event) => setCut(event.target.checked)} />
                <span>Let the AI cut {clips.length > 1 ? "and join the clips" : "the clip"}: drop bad takes, repeats and dead air, tighten pauses</span>
              </label>
            </div>
          ) : (
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-400">Script / on-screen text <span className="font-normal text-slate-500">(optional, used word for word)</span></span>
              <Textarea rows={5} dir="auto" placeholder="Paste the script or voice-over text…" value={script} onChange={(event) => setScript(event.target.value)} />
            </label>
          )}


          <div>
            <span className="mb-1.5 block text-xs font-medium text-slate-400">How much editing</span>
            <div className="grid grid-cols-3 gap-1 rounded-lg bg-black/30 p-0.5">
              {INTENSITIES.map((item) => (
                <button key={item.id} onClick={() => setIntensity(item.id)} className={`rounded-md px-2 py-1.5 text-left transition ${intensity === item.id ? "bg-accent text-white" : "text-slate-300 hover:bg-white/[0.06]"}`}>
                  <span className="block text-xs font-semibold">{item.title}</span>
                  <span className="block text-[10px] opacity-80">{item.hint}</span>
                </button>
              ))}
            </div>
          </div>

          <ResourcePicker resources={resources} selected={attached} onChange={setAttached} onUpload={onUploadResources} />

          <div className="grid grid-cols-2 gap-1 rounded-lg bg-black/30 p-0.5">
            {(["fast", "agent"] as const).map((item) => (
              <button key={item} disabled={item === "fast" && !fast} onClick={() => setMode(item)} className={`rounded-md px-2 py-1.5 text-left transition disabled:opacity-40 ${effective === item ? "bg-accent text-white" : "text-slate-300 hover:bg-white/[0.06]"}`}>
                <span className="block text-xs font-semibold">{item === "fast" ? "Fast edit" : "Full agent"}</span>
                <span className="block text-[10px] opacity-80">{item === "fast" ? (!generic ? "1 plan call · ~$0.10–0.30" : "1 call writes it · ~$0.30–0.80") : "free-form · ~$1–3"}</span>
              </button>
            ))}
          </div>
          {effective === "fast" && skill === "wassim-style" && people && (
            <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={quick} onChange={(event) => setQuick(event.target.checked)} /> Skip the speaker cut-out (much faster, no head pop-out)</label>
          )}
          {error && <p className="flex items-start gap-2 text-xs text-red-300"><AlertIcon className="mt-0.5 shrink-0" />{error}</p>}
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onBack}>Back</Button>
            <Button className="flex-1" onClick={() => void start()} disabled={busy || !skill}>{busy && <Spinner />}Start the edit</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

/**
 * The guided path: pick the kind of video and the clips, fix and approve
 * their transcripts, choose a style, then watch the edit and ask for changes.
 */
export function CreateFlow({ projectId, step, onStep, clipId, onClip, assets, skills, run, runs, events, agentReady, onUpload, onRefreshAssets, onStart, onReply, onCancel, onSelectRun, result, onUploadResources }: {
  projectId?: string;
  step: Step;
  onStep: (step: Step) => void;
  clipId?: string;
  onClip: (id: string) => void;
  assets: Asset[];
  skills: Skill[];
  run?: Run;
  runs: Run[];
  events: RunEvent[];
  agentReady: boolean;
  onUpload: (files: File[]) => Promise<Asset[]>;
  onUploadResources: (files: File[]) => Promise<Asset[]>;
  onRefreshAssets: () => void;
  onStart: (brief: string, skill: string | null, options: StartOptions) => Promise<void>;
  onReply: (text: string, resources?: string[]) => Promise<void>;
  onCancel: () => Promise<void>;
  onSelectRun: (run: Run) => void;
  result: ReactNode;
}) {
  const [kind, setKind] = useState<VideoKind>("people");
  const [selected, setSelected] = useState<string[]>([]);
  const clips = assets.filter((asset) => asset.kind === "video" && !isResource(asset));
  const resources = assets.filter(isResource);
  const chosen = selected.map((id) => clips.find((clip) => clip.id === id)).filter((clip): clip is Asset => Boolean(clip));
  const people = kind === "people";
  const approved = chosen.length > 0 && chosen.every((clip) => clip.transcript_reviewed);
  const styles = stylesFor(kind, skills);

  // A clip opened from the Library (or a past run) starts the flow with it.
  useEffect(() => {
    if (clipId && !selected.includes(clipId)) {
      setKind("people");
      setSelected([clipId]);
    }
    // Only react to clips picked outside this flow.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clipId]);
  useEffect(() => {
    if (step === 2 && (!people || chosen.length === 0)) onStep(people ? 1 : 3);
  }, [step, people, chosen.length, onStep]);

  const steps: { step: Step; title: string; hint: string }[] = people
    ? [
        { step: 1, title: "Type & clips", hint: "What you're making" },
        { step: 2, title: "Transcripts", hint: "Fix or paste the script" },
        { step: 3, title: "Style", hint: "Look & intensity" },
        { step: 4, title: "Edit", hint: "Result & changes" },
      ]
    : [
        { step: 1, title: "Type", hint: "What you're making" },
        { step: 3, title: "Style & script", hint: "Look, brief, text" },
        { step: 4, title: "Edit", hint: "Result & changes" },
      ];
  const reachable = (target: Step) => target === 1 || (target === 2 && people && chosen.length > 0) || (target === 3 && (!people || approved)) || (target === 4 && Boolean(run));

  function next() {
    if (!people) return onStep(3);
    const pending = chosen.find((clip) => !clip.transcript_reviewed);
    if (pending) {
      onClip(pending.id);
      onStep(2);
    } else {
      onStep(3);
    }
  }

  return (
    <div className="space-y-5">
      <Stepper steps={steps} current={step} reachable={reachable} onGo={onStep} />

      {step === 1 && <StartStep kind={kind} onKind={setKind} clips={clips} selected={selected} onSelected={setSelected} onUpload={onUpload} onContinue={next} />}

      {step === 2 && people && <TranscriptStep clips={chosen} focus={clipId} onFocus={onClip} assets={assets} onChanged={onRefreshAssets} onDone={() => onStep(3)} />}

      {step === 3 && (!people || approved ? (
        <StyleStep key={kind} projectId={projectId} kind={kind} styles={styles} clips={people ? chosen : []} resources={resources} onUploadResources={onUploadResources} onStart={async (brief, skill, options) => { await onStart(brief, skill, options); onStep(4); }} onBack={() => onStep(people ? 2 : 1)} />
      ) : (
        <Card><Empty icon={<AlertIcon />} title="Approve every transcript first">Captions use the transcripts exactly as you approve them. <button className="font-semibold text-accent-soft underline" onClick={() => onStep(2)}>Go to the transcripts</button></Empty></Card>
      ))}

      {step === 4 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
          <section className="min-w-0 space-y-4">{result}</section>
          <aside className="min-w-0 lg:sticky lg:top-4 lg:h-[calc(100vh-11rem)]">
            <AgentPanel
              projectId={projectId}
              run={run}
              events={events}
              styles={stylesFrom(skills)}
              agentReady={agentReady}
              onStart={onStart}
              onReply={onReply}
              onCancel={onCancel}
              onNewRun={() => onStep(3)}
              clips={chosen.length ? chosen : clips}
              resources={resources}
              onUploadResources={onUploadResources}
              onReviewTranscript={() => onStep(2)}
            />
          </aside>
        </div>
      )}
    </div>
  );
}
