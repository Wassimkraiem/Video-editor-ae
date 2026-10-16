"use client";

import { useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import type { Asset, Output, Run } from "../lib/api-client";
import { mediaUrl } from "../lib/api-client";
import { timeAgo } from "./ChatList";
import { Badge, Empty, Spinner, StatusBadge, formatBytes, formatDuration } from "./ui";
import { CheckIcon, FilmIcon, PlayIcon, SparkIcon, UploadIcon } from "./icons";

function Column({ title, count, tone, icon, children }: { title: string; count: number; tone: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="flex min-h-[420px] flex-col rounded-2xl border border-line bg-panel/60">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <span className={`flex h-6 w-6 items-center justify-center rounded-md ${tone}`}>{icon}</span>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        <Badge className="ml-auto">{count}</Badge>
      </header>
      <div className="scroll-quiet flex-1 space-y-2 overflow-auto p-3">{children}</div>
    </section>
  );
}

function Thumb({ src, video, label }: { src?: string | null; video?: string; label: string }) {
  return (
    <div className="relative flex aspect-video w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-black ring-1 ring-line">
      {src ? <img src={mediaUrl(src)} alt="" className="h-full w-full object-cover" /> : video ? <video src={`${mediaUrl(video)}#t=0.5`} preload="metadata" muted className="h-full w-full object-cover" /> : <span className="text-[10px] font-semibold uppercase text-slate-500">{label}</span>}
    </div>
  );
}

/** The project's videos grouped by stage: raw footage → in progress → edited. */
export function StyleBadge({ skill }: { skill?: string | null }) {
  const label = skill ? skill.replace(/-style$/, "").replace(/-/g, " ") : "custom";
  return <span className="inline-flex max-w-[140px] items-center truncate rounded-full bg-accent/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white shadow-glow">{label}</span>;
}

export function LibraryView({ assets, runs, outputs, onUpload, onPlayAsset, onPlayOutput, onOpenRun, onOpenInStudio }: {
  assets: Asset[];
  runs: Run[];
  outputs: Output[];
  onUpload: (files: File[]) => Promise<unknown>;
  onPlayAsset: (asset: Asset) => void;
  onPlayOutput: (output: Output) => void;
  onOpenRun: (run: Run) => void;
  onOpenInStudio: (output: Output) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const active = runs.filter((run) => ["queued", "running", "waiting_for_approval"].includes(run.status));

  async function upload(files: File[]) {
    if (!files.length) return;
    setUploading(true);
    try { await onUpload(files); } finally { setUploading(false); }
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Column title="Raw footage" count={assets.length} tone="bg-slate-500/20 text-slate-300" icon={<FilmIcon width={14} height={14} />}>
        <button
          type="button"
          onClick={() => input.current?.click()}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
          className={`flex w-full items-center justify-center gap-2 rounded-xl border border-dashed px-3 py-4 text-xs transition ${dragging ? "border-accent bg-accent/10 text-white" : "border-slate-600/50 text-slate-300 hover:border-accent/50"}`}
        >
          {uploading ? <Spinner /> : <UploadIcon />} {uploading ? "Uploading…" : "Drop clips or click to upload"}
        </button>
        <input ref={input} className="hidden" type="file" multiple accept="video/*,audio/*,image/*" onChange={(event) => { void upload(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
        {assets.map((asset) => (
          <button key={asset.id} onClick={() => onPlayAsset(asset)} className="flex w-full items-center gap-3 rounded-xl p-2 text-left transition hover:bg-white/[0.04]">
            <Thumb src={asset.thumbnail_url} label={asset.kind} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-slate-200">{asset.filename}</span>
              <span className="block text-[11px] text-slate-500">{[formatDuration(asset.probe?.duration_ms), asset.probe?.width ? `${asset.probe.width}×${asset.probe.height}` : "", formatBytes(asset.size_bytes)].filter(Boolean).join(" · ")}</span>
              {asset.status !== "ready" && <span className="mt-1 inline-block"><StatusBadge status={asset.status === "uploaded" ? "running" : asset.status} /></span>}
              {asset.status === "ready" && (asset.transcript_status === "transcribing" || asset.transcript_status === "cleaning") && <span className="mt-1 flex items-center gap-1.5 text-[11px] text-sky-300"><Spinner className="h-2.5 w-2.5 border" /> {asset.transcript_status === "cleaning" ? "Cleaning up words" : "Transcribing"}</span>}
              {asset.transcript_status === "ready" && <span className={`mt-1 block text-[11px] ${asset.transcript_reviewed ? "text-emerald-300" : "text-amber-300"}`}>{asset.transcript_reviewed ? "Transcript reviewed" : "Transcript ready: review it"}</span>}
            </span>
          </button>
        ))}
      </Column>

      <Column title="In progress" count={active.length} tone="bg-sky-500/15 text-sky-300" icon={<SparkIcon width={14} height={14} />}>
        {active.length === 0 && <Empty icon={<SparkIcon />} title="Nothing in progress">Start an edit from the Edit tab; it shows here while the agent works.</Empty>}
        {active.map((run) => (
          <button key={run.id} onClick={() => onOpenRun(run)} className="w-full rounded-xl border border-line bg-white/[0.02] p-3 text-left transition hover:border-accent/40">
            <span className="line-clamp-2 text-sm text-slate-200" dir="auto">{run.brief}</span>
            <span className="mt-2 flex items-center gap-2 text-[11px] text-slate-500"><StatusBadge status={run.status} />{run.skill}<span className="ml-auto">{timeAgo(run.created_at)}</span></span>
          </button>
        ))}
      </Column>

      <Column title="Edited" count={outputs.length} tone="bg-emerald-500/15 text-emerald-300" icon={<CheckIcon width={14} height={14} />}>
        {outputs.length === 0 && <Empty icon={<PlayIcon />} title="No finished videos yet">Renders from the agent and from Studio land here.</Empty>}
        <div className="grid grid-cols-2 gap-3">
          {outputs.map((output) => (
            <article key={output.path} className="group overflow-hidden rounded-xl border border-line bg-black/30">
              <button onClick={() => onPlayOutput(output)} className="relative block aspect-[9/12] w-full overflow-hidden bg-black" title={output.title ?? output.name}>
                <video src={`${mediaUrl(output.url)}#t=1`} preload="metadata" muted className="h-full w-full object-cover transition group-hover:scale-[1.03]" />
                <span className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent" />
                {/* The style on the cover, so videos are told apart at a glance. */}
                <span className="absolute left-2 top-2"><StyleBadge skill={output.skill} /></span>
                <span className="absolute inset-x-2 bottom-2 text-left">
                  <span className="line-clamp-2 text-xs font-medium text-white" dir="auto">{output.title || output.name}</span>
                  <span className="block text-[10px] text-slate-300">{formatBytes(output.size_bytes)} · {timeAgo(output.modified_at)}</span>
                </span>
              </button>
              <div className="flex gap-1 p-1.5">
                <button onClick={() => onPlayOutput(output)} className="flex-1 rounded-md px-2 py-1 text-[11px] text-slate-300 hover:bg-white/[0.06]">Play</button>
                <button onClick={() => onOpenInStudio(output)} disabled={!output.composition} className="flex-1 rounded-md bg-accent/15 px-2 py-1 text-[11px] font-medium text-accent-soft hover:bg-accent/25 disabled:opacity-40" title={output.composition ?? "No HyperFrames reel for this video"}>Open in Studio</button>
              </div>
            </article>
          ))}
        </div>
      </Column>
    </div>
  );
}
