"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import { api, mediaUrl, type Asset, type Render } from "../lib/api-client";
import {
  type CaptionLine, type EditDoc, type TextLayer, FONTS, activeAt, clipLength, clipStarts, deleteClip, duration, formatTime, locate, moveClip, newId, splitAt, trimClip,
} from "../lib/manual-edit";
import { Badge, Button, Card, Input, Spinner, Textarea } from "./ui";
import { AlertIcon, CheckIcon, DownloadIcon, PlayIcon, StopIcon } from "./icons";

type Selection = { kind: "clip" | "caption" | "text"; id: string } | null;

const FORMATS = [
  { label: "Keep source", width: 0, height: 0 },
  { label: "9:16 vertical", width: 1080, height: 1920 },
  { label: "4:5 feed", width: 1080, height: 1350 },
  { label: "1:1 square", width: 1080, height: 1080 },
  { label: "16:9 landscape", width: 1920, height: 1080 },
];

const seconds = (ms: number) => Math.round(ms / 100) / 10;

/** Drag with the pointer; `onMove` gets the horizontal distance in pixels. */
function drag(event: ReactPointerEvent, onMove: (dx: number, dy: number) => void, onEnd?: () => void) {
  event.preventDefault();
  event.stopPropagation();
  const startX = event.clientX;
  const startY = event.clientY;
  const move = (next: PointerEvent) => onMove(next.clientX - startX, next.clientY - startY);
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    onEnd?.();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function hexToRgba(hex: string, opacity: number) {
  const value = parseInt(hex.slice(1), 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${opacity})`;
}

function fontStack(font: string) {
  return `"${font}", Inter, "Noto Sans Arabic", system-ui, sans-serif`;
}

function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center justify-between text-[11px] font-medium text-slate-400">{label}{hint && <span className="font-normal text-slate-500">{hint}</span>}</span>
      {children}
    </label>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-2 rounded-lg px-1 py-1 text-xs text-slate-300 hover:bg-white/[0.03]">
      {label}
      <input type="checkbox" className="h-4 w-4 accent-[#3b82f6]" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function Range({ value, min, max, step, onChange, format }: { value: number; min: number; max: number; step: number; onChange: (value: number) => void; format?: (value: number) => string }) {
  return (
    <span className="flex items-center gap-2">
      <input type="range" className="w-full accent-[#3b82f6]" value={value} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} />
      <span className="w-12 shrink-0 text-right text-[11px] tabular-nums text-slate-400">{format ? format(value) : value}</span>
    </span>
  );
}

const inputClass = "h-8 w-full rounded-md border border-line bg-black/30 px-2 text-xs text-slate-100 outline-none focus:border-accent/50";

/** CapCut-style editor for basic edits: no agent, exported with FFmpeg. */
export function ManualEditor({ projectId, editId, assets, onBack, onShowVideos }: { projectId: string; editId: string; assets: Asset[]; onBack: () => void; onShowVideos: () => void }) {
  const [doc, setDoc] = useState<EditDoc>();
  const [loadError, setLoadError] = useState("");
  const [saveState, setSaveState] = useState<"saved" | "saving" | "error">("saved");
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [selection, setSelection] = useState<Selection>(null);
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [zoom, setZoom] = useState(60);
  const [exporting, setExporting] = useState<{ render?: Render; error?: string; busy?: boolean }>({});
  const history = useRef<{ past: EditDoc[]; future: EditDoc[] }>({ past: [], future: [] });
  const docRef = useRef<EditDoc | undefined>(undefined);
  const timeRef = useRef(0);
  const playingRef = useRef(false);
  const clipIndex = useRef(0);
  const videos = useRef<Record<string, HTMLVideoElement | null>>({});
  const saved = useRef("");
  docRef.current = doc;

  const assetById = useMemo(() => new Map(assets.map((asset) => [asset.id, asset])), [assets]);
  const total = doc ? duration(doc) : 0;

  useEffect(() => {
    let stale = false;
    setDoc(undefined);
    history.current = { past: [], future: [] };
    void api.edit(projectId, editId).then((loaded) => { if (stale) return; saved.current = JSON.stringify(loaded); setDoc(loaded); }).catch((reason) => !stale && setLoadError(reason instanceof Error ? reason.message : "Could not open the edit"));
    return () => { stale = true; };
  }, [projectId, editId]);

  // Signed URLs for every source clip in the edit.
  const assetIds = useMemo(() => [...new Set(doc?.clips.map((clip) => clip.asset_id) ?? [])].join(","), [doc]);
  useEffect(() => {
    for (const id of assetIds.split(",").filter(Boolean)) {
      if (urls[id]) continue;
      void api.assetUrl(id).then(({ url }) => setUrls((current) => ({ ...current, [id]: mediaUrl(url) }))).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetIds]);

  // Autosave shortly after the last change.
  useEffect(() => {
    if (!doc) return;
    const body = JSON.stringify(doc);
    if (body === saved.current) return;
    setSaveState("saving");
    const timer = setTimeout(() => {
      void api.saveEdit(projectId, doc).then(() => { saved.current = body; setSaveState("saved"); }).catch(() => setSaveState("error"));
    }, 700);
    return () => clearTimeout(timer);
  }, [doc, projectId]);

  /** Change the edit. `record: false` is for the moves of a drag already recorded at its start. */
  const change = useCallback((next: EditDoc, record = true) => {
    const current = docRef.current;
    if (record && current) {
      history.current.past = [...history.current.past.slice(-99), current];
      history.current.future = [];
    }
    setDoc(next);
  }, []);

  const undo = useCallback(() => {
    const previous = history.current.past.pop();
    if (!previous || !docRef.current) return;
    history.current.future.push(docRef.current);
    setDoc(previous);
  }, []);
  const redo = useCallback(() => {
    const next = history.current.future.pop();
    if (!next || !docRef.current) return;
    history.current.past.push(docRef.current);
    setDoc(next);
  }, []);

  // -- playback: one <video> per source clip, switched at each cut -------------

  const showFrame = useCallback((at: number, play: boolean) => {
    const current = docRef.current;
    if (!current?.clips.length) return;
    const found = locate(current.clips, at);
    if (!found) return;
    clipIndex.current = found.index;
    for (const [id, element] of Object.entries(videos.current)) {
      if (!element) continue;
      if (id === found.clip.asset_id) {
        element.style.visibility = "visible";
        if (Math.abs(element.currentTime * 1000 - found.source) > 60) element.currentTime = found.source / 1000;
        element.volume = Math.min(found.clip.volume * current.audio.volume, 1);
        element.muted = found.clip.volume === 0 || current.audio.volume === 0;
        if (play) void element.play().catch(() => undefined);
        else element.pause();
      } else {
        element.style.visibility = "hidden";
        element.pause();
      }
    }
  }, []);

  const seek = useCallback((at: number) => {
    const clamped = Math.min(Math.max(at, 0), Math.max(duration(docRef.current ?? { clips: [] }) - 1, 0));
    timeRef.current = clamped;
    setTime(clamped);
    showFrame(clamped, playingRef.current);
  }, [showFrame]);

  const setPlay = useCallback((value: boolean) => {
    const current = docRef.current;
    if (!current) return;
    if (value && timeRef.current >= duration(current) - 50) timeRef.current = 0;
    playingRef.current = value;
    setPlaying(value);
    showFrame(timeRef.current, value);
  }, [showFrame]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const current = docRef.current;
      const clip = current?.clips[clipIndex.current];
      const element = clip && videos.current[clip.asset_id];
      if (current && clip && element) {
        const source = element.currentTime * 1000;
        const start = clipStarts(current.clips)[clipIndex.current];
        if (source >= clip.out_ms - 20 || element.ended) {
          const next = clipIndex.current + 1;
          if (next >= current.clips.length) {
            setPlay(false);
            timeRef.current = duration(current) - 1;
            setTime(timeRef.current);
            return;
          }
          timeRef.current = start + clipLength(clip);
          showFrame(timeRef.current, true);
        } else {
          timeRef.current = start + Math.max(source - clip.in_ms, 0);
        }
        setTime(timeRef.current);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, setPlay, showFrame]);

  // Show the right frame once the edit and its sources are loaded.
  useEffect(() => { if (doc && !playingRef.current) showFrame(timeRef.current, false); }, [doc, urls, showFrame]);

  // -- edit actions --------------------------------------------------------------

  const split = useCallback(() => { const current = docRef.current; if (current) change(splitAt(current, timeRef.current)); }, [change]);

  const removeSelected = useCallback(() => {
    const current = docRef.current;
    if (!current || !selection) return;
    if (selection.kind === "clip") change(deleteClip(current, selection.id));
    if (selection.kind === "caption") change({ ...current, captions: current.captions.filter((line) => line.id !== selection.id) });
    if (selection.kind === "text") change({ ...current, texts: current.texts.filter((layer) => layer.id !== selection.id) });
    setSelection(null);
  }, [change, selection]);

  const addText = useCallback(() => {
    const current = docRef.current;
    if (!current) return;
    const start = Math.min(timeRef.current, Math.max(duration(current) - 500, 0));
    const layer: TextLayer = { id: newId("t"), text: "Your text", start_ms: Math.round(start), end_ms: Math.round(Math.min(start + 3000, duration(current))), x: 0.5, y: 0.22, size: 7, font: "Inter Display", color: "#FFFFFF", background: null, bold: true };
    change({ ...current, texts: [...current.texts, layer] });
    setSelection({ kind: "text", id: layer.id });
  }, [change]);

  const addCaption = useCallback(() => {
    const current = docRef.current;
    if (!current) return;
    const start = Math.round(timeRef.current);
    const line: CaptionLine = { id: newId("l"), text: "New caption", start_ms: start, end_ms: Math.min(start + 1500, duration(current)) };
    change({ ...current, captions: [...current.captions, line].sort((a, b) => a.start_ms - b.start_ms) });
    setSelection({ kind: "caption", id: line.id });
  }, [change]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT" || target.isContentEditable)) return;
      const key = event.key.toLowerCase();
      if (key === " ") { event.preventDefault(); setPlay(!playingRef.current); }
      else if (key === "s" && !event.ctrlKey && !event.metaKey) { event.preventDefault(); split(); }
      else if (key === "delete" || key === "backspace") { event.preventDefault(); removeSelected(); }
      else if ((event.ctrlKey || event.metaKey) && key === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); }
      else if ((event.ctrlKey || event.metaKey) && key === "y") { event.preventDefault(); redo(); }
      else if (key === "arrowleft") seek(timeRef.current - (event.shiftKey ? 1000 : 100));
      else if (key === "arrowright") seek(timeRef.current + (event.shiftKey ? 1000 : 100));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPlay, split, removeSelected, undo, redo, seek]);

  async function exportVideo() {
    const current = docRef.current;
    if (!current) return;
    setExporting({ busy: true });
    try {
      await api.saveEdit(projectId, current);
      saved.current = JSON.stringify(current);
      const render = await api.exportEdit(projectId, current.id);
      setExporting({ render, busy: true });
    } catch (reason) {
      setExporting({ error: reason instanceof Error ? reason.message : "Export failed" });
    }
  }

  // Follow the export until it finishes.
  const renderId = exporting.render?.id;
  useEffect(() => {
    if (!renderId) return;
    const timer = setInterval(() => {
      void api.renders(projectId).then((items) => {
        const item = items.find((render) => render.id === renderId);
        if (!item || item.status === "queued" || item.status === "running") return;
        setExporting(item.status === "succeeded" ? { render: item } : { error: item.error ?? "Export failed" });
      }).catch(() => undefined);
    }, 1500);
    return () => clearInterval(timer);
  }, [renderId, projectId]);

  if (loadError) return <Card><p className="flex items-center gap-2 p-6 text-sm text-red-300"><AlertIcon /> {loadError}</p></Card>;
  if (!doc) return <div className="flex justify-center py-24 text-slate-500"><Spinner /></div>;

  const captionStyle = doc.caption_style;
  const visibleCaptions = captionStyle.enabled ? activeAt(doc.captions, time) : [];
  const visibleTexts = activeAt(doc.texts, time);
  const selectedClip = selection?.kind === "clip" ? doc.clips.find((clip) => clip.id === selection.id) : undefined;
  const selectedCaption = selection?.kind === "caption" ? doc.captions.find((line) => line.id === selection.id) : undefined;
  const selectedText = selection?.kind === "text" ? doc.texts.find((layer) => layer.id === selection.id) : undefined;
  const updateText = (id: string, patch: Partial<TextLayer>, record = true) => change({ ...doc, texts: doc.texts.map((layer) => (layer.id === id ? { ...layer, ...patch } : layer)) }, record);
  const updateCaption = (id: string, patch: Partial<CaptionLine>, record = true) => change({ ...doc, captions: doc.captions.map((line) => (line.id === id ? { ...line, ...patch } : line)) }, record);
  const pxPerMs = zoom / 1000;
  const timelineWidth = Math.max(total * pxPerMs, 600);
  const starts = clipStarts(doc.clips);

  /** Drag a caption or text block: move it, or resize from an edge. */
  function dragTimed(event: ReactPointerEvent, item: { id: string; start_ms: number; end_ms: number }, mode: "move" | "start" | "end", apply: (patch: { start_ms: number; end_ms: number }, record: boolean) => void) {
    let first = true;
    const length = item.end_ms - item.start_ms;
    drag(event, (dx) => {
      const delta = dx / pxPerMs;
      let start = item.start_ms;
      let end = item.end_ms;
      if (mode === "move") { start = Math.min(Math.max(item.start_ms + delta, 0), total - length); end = start + length; }
      if (mode === "start") start = Math.min(Math.max(item.start_ms + delta, 0), item.end_ms - 100);
      if (mode === "end") end = Math.max(Math.min(item.end_ms + delta, total), item.start_ms + 100);
      apply({ start_ms: Math.round(start), end_ms: Math.round(end) }, first);
      first = false;
    });
  }

  function dragClipEdge(event: ReactPointerEvent, clipId: string, edge: "in" | "out") {
    const clip = doc!.clips.find((item) => item.id === clipId);
    if (!clip) return;
    const sourceDuration = assetById.get(clip.asset_id)?.probe?.duration_ms ?? clip.out_ms;
    const base = docRef.current!;
    let first = true;
    drag(event, (dx) => {
      const edgeMs = (edge === "in" ? clip.in_ms : clip.out_ms) + dx / pxPerMs;
      change(trimClip(base, clipId, edge, edgeMs, sourceDuration), first);
      first = false;
    });
  }

  function dragTextOnCanvas(event: ReactPointerEvent<HTMLDivElement>, layer: TextLayer) {
    setSelection({ kind: "text", id: layer.id });
    const frame = event.currentTarget.parentElement?.getBoundingClientRect();
    if (!frame) return;
    let first = true;
    drag(event, (dx, dy) => {
      updateText(layer.id, { x: Math.min(Math.max(layer.x + dx / frame.width, 0), 1), y: Math.min(Math.max(layer.y + dy / frame.height, 0), 1) }, first);
      first = false;
    });
  }

  const block = "absolute top-1 bottom-1 flex items-center overflow-hidden rounded-md px-2 text-[11px] font-medium text-white ring-1 ring-inset";
  const handle = "absolute inset-y-0 w-2 cursor-ew-resize bg-white/0 hover:bg-white/30";

  return (
    <div className="space-y-4">
      {/* Top bar */}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" onClick={onBack}>← Edits</Button>
        <input aria-label="Edit name" value={doc.name} onChange={(event) => change({ ...doc, name: event.target.value }, false)} className="h-8 min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-2 text-base font-semibold text-white outline-none hover:border-line focus:border-accent/50" />
        <Badge tone="success">free · no AI credits</Badge>
        <span className="text-[11px] text-slate-500">{saveState === "saving" ? "Saving…" : saveState === "error" ? <span className="text-red-300">Not saved</span> : "Saved"}</span>
        <Button size="sm" onClick={() => void exportVideo()} disabled={exporting.busy || !doc.clips.length}>{exporting.busy ? <><Spinner /> Exporting…</> : <><DownloadIcon /> Export video</>}</Button>
      </div>
      {exporting.error && <p className="flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-200"><AlertIcon className="mt-0.5 shrink-0" /><span className="break-all">{exporting.error}</span></p>}
      {exporting.render?.status === "succeeded" && (
        <p className="flex flex-wrap items-center gap-3 rounded-lg bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
          <CheckIcon /> Exported. It's in your Videos.
          {exporting.render.output_url && <a className="font-semibold underline" href={mediaUrl(exporting.render.output_url)} target="_blank" rel="noreferrer">Watch</a>}
          {exporting.render.output_url && <a className="font-semibold underline" href={mediaUrl(exporting.render.output_url)} download>Download</a>}
          <button className="font-semibold underline" onClick={onShowVideos}>Open Videos</button>
        </p>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        {/* Player */}
        <Card className="overflow-hidden">
          <div className="flex justify-center bg-black/40 p-3">
            <div className="relative overflow-hidden bg-black" style={{ aspectRatio: `${doc.width} / ${doc.height}`, height: "min(56vh, 640px)", maxWidth: "100%", containerType: "size" } as CSSProperties} onClick={() => setSelection(null)}>
              {[...new Set(doc.clips.map((clip) => clip.asset_id))].map((id) => (
                <video key={id} ref={(element) => { videos.current[id] = element; }} src={urls[id]} preload="auto" playsInline className="absolute inset-0 h-full w-full object-contain" style={{ visibility: "hidden" }} onLoadedData={() => showFrame(timeRef.current, playingRef.current)} />
              ))}
              {visibleCaptions.map((line) => (
                <div key={line.id} className="pointer-events-none absolute inset-x-[4%] text-center" style={{ top: `${captionStyle.y * 100}%`, transform: "translateY(-50%)" }} dir="auto">
                  <span className="inline px-[0.3em] py-[0.1em] leading-snug [box-decoration-break:clone]" style={{ fontFamily: fontStack(captionStyle.font), fontSize: `${captionStyle.size}cqh`, fontWeight: captionStyle.bold ? 800 : 500, color: captionStyle.color, background: captionStyle.background ? hexToRgba(captionStyle.background, captionStyle.background_opacity) : "transparent", textShadow: captionStyle.background ? "none" : "0 0.06em 0.12em rgba(0,0,0,.8)" }}>
                    {captionStyle.uppercase ? line.text.toUpperCase() : line.text}
                  </span>
                </div>
              ))}
              {visibleTexts.map((layer) => (
                <div key={layer.id} onPointerDown={(event) => dragTextOnCanvas(event, layer)} onClick={(event) => event.stopPropagation()} className={`absolute cursor-move whitespace-pre text-center leading-tight ${selection?.id === layer.id ? "outline outline-2 outline-accent" : "hover:outline hover:outline-1 hover:outline-white/50"}`} style={{ left: `${layer.x * 100}%`, top: `${layer.y * 100}%`, transform: "translate(-50%, -50%)", fontFamily: fontStack(layer.font), fontSize: `${layer.size}cqh`, fontWeight: layer.bold ? 800 : 500, color: layer.color, background: layer.background ? hexToRgba(layer.background, 0.85) : "transparent", padding: layer.background ? "0.15em 0.35em" : 0, textShadow: layer.background ? "none" : "0 0.05em 0.15em rgba(0,0,0,.7)" }} dir="auto">
                  {layer.text}
                </div>
              ))}
              {!doc.clips.length && <p className="absolute inset-0 flex items-center justify-center text-sm text-slate-500">No clips left. Undo to bring them back.</p>}
            </div>
          </div>

          {/* Transport + tools */}
          <div className="flex flex-wrap items-center gap-1.5 border-t border-line px-3 py-2">
            <Button size="sm" onClick={() => setPlay(!playing)} aria-label={playing ? "Pause" : "Play"} className="w-9 !px-0">{playing ? <StopIcon width={12} height={12} /> : <PlayIcon width={14} height={14} />}</Button>
            <span className="w-28 text-xs tabular-nums text-slate-300">{formatTime(time)} / {formatTime(total)}</span>
            <span className="mx-1 h-5 w-px bg-line" />
            <Button size="sm" variant="secondary" onClick={split} title="Split at the playhead (S)">Split</Button>
            <Button size="sm" variant="secondary" onClick={removeSelected} disabled={!selection} title="Delete the selection (Del)">Delete</Button>
            <Button size="sm" variant="secondary" onClick={addText} title="Add a text layer at the playhead">+ Text</Button>
            <Button size="sm" variant="secondary" onClick={addCaption} title="Add a caption line at the playhead">+ Caption</Button>
            <span className="mx-1 h-5 w-px bg-line" />
            <Button size="sm" variant="ghost" onClick={undo} disabled={!history.current.past.length} title="Undo (Ctrl+Z)">Undo</Button>
            <Button size="sm" variant="ghost" onClick={redo} disabled={!history.current.future.length} title="Redo (Ctrl+Shift+Z)">Redo</Button>
            <span className="ml-auto flex items-center gap-2 text-[11px] text-slate-500">Zoom <input type="range" min={10} max={300} value={zoom} onChange={(event) => setZoom(Number(event.target.value))} className="w-24 accent-[#3b82f6]" /></span>
          </div>

          {/* Timeline */}
          <div className="scroll-quiet overflow-x-auto border-t border-line bg-black/20">
            <div className="relative select-none" style={{ width: timelineWidth + 96 }}>
              <div className="relative ml-24 h-6 cursor-pointer border-b border-line" onPointerDown={(event) => { const box = event.currentTarget.getBoundingClientRect(); seek((event.clientX - box.left) / pxPerMs); drag(event, (dx) => seek((event.clientX - box.left + dx) / pxPerMs)); }}>
                {Array.from({ length: Math.ceil(total / 1000) + 1 }, (_, second) => second).filter((second) => second % (zoom < 25 ? 5 : zoom < 50 ? 2 : 1) === 0).map((second) => (
                  <span key={second} className="absolute top-0 h-full border-l border-line pl-1 text-[10px] tabular-nums text-slate-500" style={{ left: second * 1000 * pxPerMs }}>{formatTime(second * 1000).replace(/\.0$/, "")}</span>
                ))}
              </div>
              {[
                { name: "Video", height: "h-14" },
                { name: "Captions", height: "h-9" },
                { name: "Text", height: "h-9" },
              ].map((track) => (
                <div key={track.name} className={`relative flex ${track.height} border-b border-line/60`}>
                  <span className="sticky left-0 z-10 flex w-24 shrink-0 items-center bg-panel px-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{track.name}</span>
                  <div className="relative flex-1" onPointerDown={(event) => { if (event.target === event.currentTarget) { const box = event.currentTarget.getBoundingClientRect(); seek((event.clientX - box.left) / pxPerMs); setSelection(null); } }}>
                    {track.name === "Video" && doc.clips.map((clip, index) => {
                      const asset = assetById.get(clip.asset_id);
                      const selected = selection?.id === clip.id;
                      return (
                        <div key={clip.id} onPointerDown={(event) => { event.stopPropagation(); setSelection({ kind: "clip", id: clip.id }); }} className={`${block} cursor-pointer bg-accent/40 ${selected ? "ring-2 ring-white" : "ring-accent/70"}`} style={{ left: starts[index] * pxPerMs, width: Math.max(clipLength(clip) * pxPerMs - 2, 4), backgroundImage: asset?.thumbnail_url ? `linear-gradient(rgba(15,23,42,.55), rgba(15,23,42,.55)), url(${mediaUrl(asset.thumbnail_url)})` : undefined, backgroundSize: "auto 100%" }} title={`${asset?.filename ?? "clip"} · ${formatTime(clipLength(clip))}`}>
                          <span className="truncate">{asset?.filename ?? "clip"}</span>
                          {clip.volume !== 1 && <span className="ml-1 shrink-0 text-[10px] opacity-80">{Math.round(clip.volume * 100)}%</span>}
                          <span className={`${handle} left-0`} onPointerDown={(event) => { setSelection({ kind: "clip", id: clip.id }); dragClipEdge(event, clip.id, "in"); }} />
                          <span className={`${handle} right-0`} onPointerDown={(event) => { setSelection({ kind: "clip", id: clip.id }); dragClipEdge(event, clip.id, "out"); }} />
                        </div>
                      );
                    })}
                    {track.name === "Captions" && doc.captions.map((line) => (
                      <div key={line.id} onPointerDown={(event) => { setSelection({ kind: "caption", id: line.id }); dragTimed(event, line, "move", (patch, record) => updateCaption(line.id, patch, record)); }} className={`${block} cursor-grab bg-amber-500/50 ${selection?.id === line.id ? "ring-2 ring-white" : "ring-amber-400/70"} ${captionStyle.enabled ? "" : "opacity-40"}`} style={{ left: line.start_ms * pxPerMs, width: Math.max((line.end_ms - line.start_ms) * pxPerMs - 1, 4) }} title={line.text} dir="auto">
                        <span className="truncate">{line.text}</span>
                        <span className={`${handle} left-0`} onPointerDown={(event) => { setSelection({ kind: "caption", id: line.id }); dragTimed(event, line, "start", (patch, record) => updateCaption(line.id, patch, record)); }} />
                        <span className={`${handle} right-0`} onPointerDown={(event) => { setSelection({ kind: "caption", id: line.id }); dragTimed(event, line, "end", (patch, record) => updateCaption(line.id, patch, record)); }} />
                      </div>
                    ))}
                    {track.name === "Text" && doc.texts.map((layer) => (
                      <div key={layer.id} onPointerDown={(event) => { setSelection({ kind: "text", id: layer.id }); dragTimed(event, layer, "move", (patch, record) => updateText(layer.id, patch, record)); }} className={`${block} cursor-grab bg-fuchsia-500/50 ${selection?.id === layer.id ? "ring-2 ring-white" : "ring-fuchsia-400/70"}`} style={{ left: layer.start_ms * pxPerMs, width: Math.max((layer.end_ms - layer.start_ms) * pxPerMs - 1, 4) }} title={layer.text} dir="auto">
                        <span className="truncate">{layer.text}</span>
                        <span className={`${handle} left-0`} onPointerDown={(event) => { setSelection({ kind: "text", id: layer.id }); dragTimed(event, layer, "start", (patch, record) => updateText(layer.id, patch, record)); }} />
                        <span className={`${handle} right-0`} onPointerDown={(event) => { setSelection({ kind: "text", id: layer.id }); dragTimed(event, layer, "end", (patch, record) => updateText(layer.id, patch, record)); }} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <div className="pointer-events-none absolute bottom-0 top-0 z-20 w-px bg-red-400" style={{ left: 96 + time * pxPerMs }}><span className="absolute -left-1 top-0 h-2 w-2 rounded-full bg-red-400" /></div>
            </div>
          </div>
          <p className="border-t border-line px-3 py-1.5 text-[10px] text-slate-500">Space play · S split · Del delete · Ctrl+Z undo · ←/→ step (Shift = 1 s) · drag block edges to trim, drag text in the video to move it</p>
        </Card>

        {/* Inspector */}
        <Card title={selectedClip ? "Clip" : selectedCaption ? "Caption" : selectedText ? "Text" : "Edit settings"} className="h-fit xl:sticky xl:top-4">
          <div className="space-y-4 p-4">
            {selectedClip && (() => {
              const asset = assetById.get(selectedClip.asset_id);
              const sourceDuration = asset?.probe?.duration_ms ?? selectedClip.out_ms;
              return (
                <>
                  <p className="truncate text-xs text-slate-300">{asset?.filename}</p>
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Start in clip (s)"><input type="number" step={0.1} className={inputClass} value={seconds(selectedClip.in_ms)} onChange={(event) => change(trimClip(doc, selectedClip.id, "in", Number(event.target.value) * 1000, sourceDuration))} /></Field>
                    <Field label="End in clip (s)"><input type="number" step={0.1} className={inputClass} value={seconds(selectedClip.out_ms)} onChange={(event) => change(trimClip(doc, selectedClip.id, "out", Number(event.target.value) * 1000, sourceDuration))} /></Field>
                  </div>
                  <p className="text-[11px] text-slate-500">Length {formatTime(clipLength(selectedClip))} of {formatTime(sourceDuration)}</p>
                  <Field label="Clip volume"><Range value={selectedClip.volume} min={0} max={3} step={0.05} onChange={(volume) => change({ ...doc, clips: doc.clips.map((clip) => (clip.id === selectedClip.id ? { ...clip, volume } : clip)) })} format={(value) => `${Math.round(value * 100)}%`} /></Field>
                  <div className="flex gap-2">
                    <Button size="sm" variant="secondary" onClick={() => change(moveClip(doc, selectedClip.id, -1))}>← Move</Button>
                    <Button size="sm" variant="secondary" onClick={() => change(moveClip(doc, selectedClip.id, 1))}>Move →</Button>
                    <Button size="sm" variant="danger" className="ml-auto" onClick={removeSelected} disabled={doc.clips.length <= 1}>Delete</Button>
                  </div>
                </>
              );
            })()}

            {selectedCaption && (
              <>
                <Field label="Text"><Textarea rows={3} dir="auto" value={selectedCaption.text} onChange={(event) => updateCaption(selectedCaption.id, { text: event.target.value }, false)} onFocus={() => change(doc)} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Start (s)"><input type="number" step={0.1} className={inputClass} value={seconds(selectedCaption.start_ms)} onChange={(event) => updateCaption(selectedCaption.id, { start_ms: Math.max(Math.round(Number(event.target.value) * 1000), 0) })} /></Field>
                  <Field label="End (s)"><input type="number" step={0.1} className={inputClass} value={seconds(selectedCaption.end_ms)} onChange={(event) => updateCaption(selectedCaption.id, { end_ms: Math.max(Math.round(Number(event.target.value) * 1000), selectedCaption.start_ms + 100) })} /></Field>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => seek(selectedCaption.start_ms)}>Go to</Button>
                  <Button size="sm" variant="danger" className="ml-auto" onClick={removeSelected}>Delete</Button>
                </div>
                <p className="text-[11px] text-slate-500">The caption look (font, size, position) is shared: clear the selection to change it.</p>
              </>
            )}

            {selectedText && (
              <>
                <Field label="Text"><Textarea rows={3} dir="auto" value={selectedText.text} onChange={(event) => updateText(selectedText.id, { text: event.target.value }, false)} onFocus={() => change(doc)} /></Field>
                <Field label="Font">
                  <select className={inputClass} value={selectedText.font} onChange={(event) => updateText(selectedText.id, { font: event.target.value })}>{FONTS.map((font) => <option key={font} className="bg-panel">{font}</option>)}</select>
                </Field>
                <Field label="Size"><Range value={selectedText.size} min={2} max={20} step={0.5} onChange={(size) => updateText(selectedText.id, { size })} /></Field>
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Colour"><input type="color" className="h-8 w-full cursor-pointer rounded-md border border-line bg-black/30" value={selectedText.color} onChange={(event) => updateText(selectedText.id, { color: event.target.value.toUpperCase() })} /></Field>
                  <Field label="Box">
                    <span className="flex items-center gap-2">
                      <input type="checkbox" className="accent-[#3b82f6]" checked={selectedText.background !== null} onChange={(event) => updateText(selectedText.id, { background: event.target.checked ? "#000000" : null })} />
                      {selectedText.background !== null && <input type="color" className="h-8 w-full cursor-pointer rounded-md border border-line bg-black/30" value={selectedText.background} onChange={(event) => updateText(selectedText.id, { background: event.target.value.toUpperCase() })} />}
                    </span>
                  </Field>
                </div>
                <Toggle label="Bold" checked={selectedText.bold} onChange={(bold) => updateText(selectedText.id, { bold })} />
                <div className="grid grid-cols-2 gap-2">
                  <Field label="Start (s)"><input type="number" step={0.1} className={inputClass} value={seconds(selectedText.start_ms)} onChange={(event) => updateText(selectedText.id, { start_ms: Math.max(Math.round(Number(event.target.value) * 1000), 0) })} /></Field>
                  <Field label="End (s)"><input type="number" step={0.1} className={inputClass} value={seconds(selectedText.end_ms)} onChange={(event) => updateText(selectedText.id, { end_ms: Math.max(Math.round(Number(event.target.value) * 1000), selectedText.start_ms + 100) })} /></Field>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => { const copy = { ...selectedText, id: newId("t"), y: Math.min(selectedText.y + 0.08, 1) }; change({ ...doc, texts: [...doc.texts, copy] }); setSelection({ kind: "text", id: copy.id }); }}>Duplicate</Button>
                  <Button size="sm" variant="danger" className="ml-auto" onClick={removeSelected}>Delete</Button>
                </div>
                <p className="text-[11px] text-slate-500">Drag the text in the video to place it.</p>
              </>
            )}

            {!selection && (
              <>
                <Field label="Format">
                  <select className={inputClass} value={FORMATS.findIndex((format) => format.width === doc.width && format.height === doc.height)} onChange={(event) => {
                    const format = FORMATS[Number(event.target.value)];
                    if (!format?.width) return;
                    change({ ...doc, width: format.width, height: format.height });
                  }}>
                    <option value={-1} className="bg-panel">{doc.width}×{doc.height}</option>
                    {FORMATS.slice(1).map((format, index) => <option key={format.label} value={index + 1} className="bg-panel">{format.label}</option>)}
                  </select>
                </Field>

                <div className="space-y-1 rounded-xl border border-line p-3">
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Sound</p>
                  <Field label="Master volume"><Range value={doc.audio.volume} min={0} max={3} step={0.05} onChange={(volume) => change({ ...doc, audio: { ...doc.audio, volume } })} format={(value) => `${Math.round(value * 100)}%`} /></Field>
                  <Toggle label="Even out loudness (-14 LUFS)" checked={doc.audio.normalize} onChange={(normalize) => change({ ...doc, audio: { ...doc.audio, normalize } })} />
                  <Toggle label="Remove background noise" checked={doc.audio.denoise} onChange={(denoise) => change({ ...doc, audio: { ...doc.audio, denoise } })} />
                  <Field label="Fade in"><Range value={doc.audio.fade_in_ms} min={0} max={3000} step={100} onChange={(fade_in_ms) => change({ ...doc, audio: { ...doc.audio, fade_in_ms } })} format={(value) => `${value / 1000}s`} /></Field>
                  <Field label="Fade out"><Range value={doc.audio.fade_out_ms} min={0} max={3000} step={100} onChange={(fade_out_ms) => change({ ...doc, audio: { ...doc.audio, fade_out_ms } })} format={(value) => `${value / 1000}s`} /></Field>
                  <p className="text-[10px] text-slate-500">Loudness and noise fixes are applied on export.</p>
                </div>

                <div className="space-y-2 rounded-xl border border-line p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Captions</p>
                    <input type="checkbox" aria-label="Show captions" className="h-4 w-4 accent-[#3b82f6]" checked={captionStyle.enabled} onChange={(event) => change({ ...doc, caption_style: { ...captionStyle, enabled: event.target.checked } })} />
                  </div>
                  <Field label="Font"><select className={inputClass} value={captionStyle.font} onChange={(event) => change({ ...doc, caption_style: { ...captionStyle, font: event.target.value } })}>{FONTS.map((font) => <option key={font} className="bg-panel">{font}</option>)}</select></Field>
                  <Field label="Size"><Range value={captionStyle.size} min={2} max={12} step={0.25} onChange={(size) => change({ ...doc, caption_style: { ...captionStyle, size } })} /></Field>
                  <Field label="Position"><Range value={captionStyle.y} min={0.1} max={0.92} step={0.01} onChange={(y) => change({ ...doc, caption_style: { ...captionStyle, y } })} format={(value) => `${Math.round(value * 100)}%`} /></Field>
                  <div className="grid grid-cols-2 gap-2">
                    <Field label="Colour"><input type="color" className="h-8 w-full cursor-pointer rounded-md border border-line bg-black/30" value={captionStyle.color} onChange={(event) => change({ ...doc, caption_style: { ...captionStyle, color: event.target.value.toUpperCase() } })} /></Field>
                    <Field label="Box">
                      <span className="flex items-center gap-2">
                        <input type="checkbox" className="accent-[#3b82f6]" checked={captionStyle.background !== null} onChange={(event) => change({ ...doc, caption_style: { ...captionStyle, background: event.target.checked ? "#000000" : null } })} />
                        {captionStyle.background !== null && <input type="color" className="h-8 w-full cursor-pointer rounded-md border border-line bg-black/30" value={captionStyle.background} onChange={(event) => change({ ...doc, caption_style: { ...captionStyle, background: event.target.value.toUpperCase() } })} />}
                      </span>
                    </Field>
                  </div>
                  {captionStyle.background !== null && <Field label="Box opacity"><Range value={captionStyle.background_opacity} min={0.1} max={1} step={0.05} onChange={(background_opacity) => change({ ...doc, caption_style: { ...captionStyle, background_opacity } })} format={(value) => `${Math.round(value * 100)}%`} /></Field>}
                  <Toggle label="Bold" checked={captionStyle.bold} onChange={(bold) => change({ ...doc, caption_style: { ...captionStyle, bold } })} />
                  <Toggle label="UPPERCASE" checked={captionStyle.uppercase} onChange={(uppercase) => change({ ...doc, caption_style: { ...captionStyle, uppercase } })} />
                  <Button size="sm" variant="secondary" className="w-full" onClick={() => {
                    if (doc.captions.length && !window.confirm("Rebuild every caption from the transcript? Your caption text edits are replaced.")) return;
                    void api.saveEdit(projectId, doc).then(() => api.rebuildCaptions(projectId, doc.id)).then((rebuilt) => change({ ...doc, captions: rebuilt.captions }));
                  }}>Rebuild from transcript</Button>
                  <p className="text-[10px] text-slate-500">{doc.captions.length} lines. Click one in the timeline to fix its words or timing.</p>
                </div>
              </>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}

/** The project's manual edits, and starting a new one from clips. */
export function EditorHome({ projectId, assets, onOpen }: { projectId?: string; assets: Asset[]; onOpen: (editId: string) => void }) {
  const [edits, setEdits] = useState<EditDoc[]>();
  const [picked, setPicked] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const clips = assets.filter((asset) => asset.kind === "video" && asset.role !== "resource" && asset.status === "ready");

  useEffect(() => {
    if (!projectId) return;
    setEdits(undefined);
    void api.edits(projectId).then(setEdits).catch(() => setEdits([]));
  }, [projectId]);

  async function create() {
    if (!projectId || !picked.length) return;
    setBusy(true);
    setError("");
    try {
      const firstName = clips.find((clip) => clip.id === picked[0])?.filename.replace(/\.[^.]+$/, "");
      const doc = await api.createEdit(projectId, { name: name.trim() || firstName || "Untitled edit", asset_ids: picked });
      onOpen(doc.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create the edit");
      setBusy(false);
    }
  }

  async function remove(doc: EditDoc) {
    if (!projectId || !window.confirm(`Delete "${doc.name}"? Exported videos stay in Videos.`)) return;
    await api.deleteEdit(projectId, doc.id).catch(() => undefined);
    setEdits((current) => current?.filter((item) => item.id !== doc.id));
  }

  if (!projectId) return null;
  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <section>
        <p className="mb-3 text-sm font-medium text-slate-300">Your edits</p>
        {edits === undefined ? <Spinner /> : edits.length === 0 ? (
          <p className="rounded-2xl border border-line bg-white/[0.02] px-4 py-6 text-sm text-slate-400">No manual edits yet. Pick clips on the right to start one: cut, fix the sound, add captions and text, and export. No AI, no credits.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
            {edits.map((doc) => {
              const thumb = assets.find((asset) => asset.id === doc.clips[0]?.asset_id)?.thumbnail_url;
              return (
                <article key={doc.id} className="group flex overflow-hidden rounded-2xl border border-line bg-white/[0.02] transition hover:border-accent/50">
                  <button onClick={() => onOpen(doc.id)} className="flex min-w-0 flex-1 items-center gap-3 p-3 text-left">
                    <span className="h-16 w-11 shrink-0 overflow-hidden rounded-md bg-black">{thumb && <img src={mediaUrl(thumb)} alt="" className="h-full w-full object-cover" />}</span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-semibold text-white">{doc.name}</span>
                      <span className="block text-[11px] text-slate-500">{formatTime(duration(doc))} · {doc.clips.length} cut{doc.clips.length === 1 ? "" : "s"} · {doc.captions.length} captions{doc.texts.length ? ` · ${doc.texts.length} texts` : ""}</span>
                      <span className="block text-[11px] text-slate-500">Edited {new Date(doc.updated_at).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}</span>
                    </span>
                  </button>
                  <button onClick={() => void remove(doc)} className="px-3 text-[11px] text-slate-500 opacity-0 transition hover:text-red-300 group-hover:opacity-100">Delete</button>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <Card title="New edit" className="h-fit">
        <div className="space-y-3 p-4">
          <Input placeholder="Name (optional)" value={name} onChange={(event) => setName(event.target.value)} />
          <p className="text-[11px] text-slate-500">Pick clips in the order they should play. Upload new ones in the Library.</p>
          {clips.length === 0 && <p className="text-xs text-slate-400">No clips in this project yet.</p>}
          <div className="grid max-h-[50vh] grid-cols-3 gap-2 overflow-y-auto">
            {clips.map((clip) => {
              const order = picked.indexOf(clip.id);
              return (
                <button key={clip.id} onClick={() => setPicked((current) => (order >= 0 ? current.filter((id) => id !== clip.id) : [...current, clip.id]))} className={`relative overflow-hidden rounded-lg border text-left transition ${order >= 0 ? "border-accent ring-1 ring-accent" : "border-line hover:border-accent/50"}`}>
                  <span className="block aspect-[9/12] bg-black">{clip.thumbnail_url && <img src={mediaUrl(clip.thumbnail_url)} alt="" className="h-full w-full object-cover" />}</span>
                  {order >= 0 && <span className="absolute left-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-white">{order + 1}</span>}
                  <span className="block truncate px-1.5 py-1 text-[10px] text-slate-300">{clip.filename}</span>
                </button>
              );
            })}
          </div>
          {error && <p className="text-xs text-red-300">{error}</p>}
          <Button className="w-full" onClick={() => void create()} disabled={!picked.length || busy}>{busy && <Spinner />}Start editing{picked.length > 1 ? ` (${picked.length} clips)` : ""}</Button>
        </div>
      </Card>
    </div>
  );
}
