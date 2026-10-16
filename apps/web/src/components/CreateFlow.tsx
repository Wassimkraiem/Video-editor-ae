"use client";

import { useEffect, useRef, useState } from "react";
import type { DragEvent, ReactNode } from "react";
import type { RunEvent } from "../lib/agent-events";
import { mediaUrl, type Asset, type Run, type Skill } from "../lib/api-client";
import { AgentPanel, stylesFrom, type StartOptions } from "./AgentPanel";
import { ResourcePicker, isResource } from "./ResourcePicker";
import { Badge, Button, Card, Empty, Spinner, Textarea, formatDuration } from "./ui";
import { AlertIcon, CheckIcon, FilmIcon, UploadIcon } from "./icons";
import { TranscriptEditor } from "./TranscriptEditor";

export type Step = 1 | 2 | 3 | 4;

const STEPS: { step: Step; title: string; hint: string }[] = [
  { step: 1, title: "Upload", hint: "Your clip" },
  { step: 2, title: "Transcript", hint: "Fix & approve" },
  { step: 3, title: "Style", hint: "Pick the look" },
  { step: 4, title: "Edit", hint: "Result & changes" },
];

function prettyName(name: string) {
  return name.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function Stepper({ current, reachable, onGo }: { current: Step; reachable: (step: Step) => boolean; onGo: (step: Step) => void }) {
  return (
    <ol className="flex items-center gap-2">
      {STEPS.map((item, index) => {
        const done = item.step < current;
        const active = item.step === current;
        const enabled = reachable(item.step);
        return (
          <li key={item.step} className="flex flex-1 items-center gap-2">
            <button disabled={!enabled} onClick={() => onGo(item.step)} className={`flex min-w-0 flex-1 items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${active ? "border-accent/60 bg-accent/15" : "border-line bg-white/[0.02] hover:bg-white/[0.05]"}`}>
              <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${active ? "bg-accent text-white shadow-glow" : done ? "bg-emerald-500/20 text-emerald-300" : "bg-white/[0.06] text-slate-400"}`}>{done ? <CheckIcon width={14} height={14} /> : item.step}</span>
              <span className="min-w-0">
                <span className={`block text-sm font-medium ${active ? "text-white" : "text-slate-300"}`}>{item.title}</span>
                <span className="block truncate text-[11px] text-slate-500">{item.hint}</span>
              </span>
            </button>
            {index < STEPS.length - 1 && <span className="hidden h-px w-4 shrink-0 bg-line xl:block" />}
          </li>
        );
      })}
    </ol>
  );
}

function UploadStep({ clips, onUpload, onPick }: { clips: Asset[]; onUpload: (files: File[]) => Promise<Asset[]>; onPick: (asset: Asset) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  async function upload(files: File[]) {
    if (!files.length) return;
    setUploading(true);
    setError("");
    try {
      const [first] = await onUpload(files);
      if (first) onPick(first);
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

  return (
    <div className="space-y-6">
      <button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        className={`flex w-full flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-6 py-16 text-center transition ${dragging ? "border-accent bg-accent/10" : "border-slate-600/50 bg-white/[0.02] hover:border-accent/60 hover:bg-accent/[0.04]"}`}
      >
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-accent/15 text-accent-soft">{uploading ? <Spinner /> : <UploadIcon width={26} height={26} />}</span>
        <span className="text-lg font-semibold text-white">{uploading ? "Uploading…" : "Drop your talking-head clip here"}</span>
        <span className="text-sm text-slate-400">or click to choose a video. It's transcribed automatically right after the upload.</span>
      </button>
      <input ref={input} className="hidden" type="file" accept="video/*" onChange={(event) => { void upload(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
      {error && <p className="text-sm text-red-300">{error}</p>}

      {clips.length > 0 && (
        <div>
          <p className="mb-3 text-sm font-medium text-slate-300">Or continue with a clip you already uploaded</p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {clips.map((clip) => (
              <button key={clip.id} onClick={() => onPick(clip)} className="group overflow-hidden rounded-xl border border-line bg-black/30 text-left transition hover:border-accent/50">
                <span className="relative block aspect-[9/12] bg-black">
                  {clip.thumbnail_url ? <img src={mediaUrl(clip.thumbnail_url)} alt="" className="h-full w-full object-cover transition group-hover:scale-[1.03]" /> : <span className="flex h-full items-center justify-center text-slate-600"><FilmIcon /></span>}
                </span>
                <span className="block p-2">
                  <span className="block truncate text-xs font-medium text-slate-200">{clip.filename}</span>
                  <span className="block text-[11px] text-slate-500">{formatDuration(clip.probe?.duration_ms)} · {clip.transcript_reviewed ? "transcript approved" : clip.transcript_status === "ready" ? "transcript to check" : clip.transcript_status ?? "processing"}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StyleStep({ styles, clip, resources, onUploadResources, onStart, onBack }: { styles: Skill[]; clip: Asset; resources: Asset[]; onUploadResources: (files: File[]) => Promise<Asset[]>; onStart: (brief: string, skill: string, options: StartOptions) => Promise<void>; onBack: () => void }) {
  const [skill, setSkill] = useState(styles[0]?.name ?? "wassim-style");
  const [attached, setAttached] = useState<string[]>([]);
  const [brief, setBrief] = useState("");
  const [mode, setMode] = useState<"fast" | "agent">("fast");
  const [quick, setQuick] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const chosen = styles.find((style) => style.name === skill);
  const fast = Boolean(chosen?.fast);
  const effective = fast ? mode : "agent";

  async function start() {
    setBusy(true);
    setError("");
    try {
      await onStart(brief.trim() || `Edit ${clip.filename} in ${prettyName(skill)}.`, skill, { mode: effective, assetId: clip.id, quick: effective === "fast" && quick, resources: attached });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the edit");
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div>
        <p className="mb-3 text-sm font-medium text-slate-300">Choose the look</p>
        <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3">
          {styles.map((style) => {
            const selected = style.name === skill;
            return (
              <button key={style.id} onClick={() => setSkill(style.name)} className={`flex flex-col rounded-2xl border p-4 text-left transition ${selected ? "border-accent/60 bg-accent/10 shadow-glow" : "border-line bg-white/[0.02] hover:border-accent/40"}`}>
                <span className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-white">{prettyName(style.name)}</span>
                  {style.scope === "user" && <Badge tone="accent">cloned</Badge>}
                  <span className="ml-auto">{style.fast_engine === "style" ? <Badge tone="success">fast · tuned</Badge> : style.fast ? <Badge tone="success">fast</Badge> : <Badge>agent</Badge>}</span>
                </span>
                <span className="mt-2 line-clamp-4 text-xs leading-relaxed text-slate-400">{style.description}</span>
              </button>
            );
          })}
        </div>
      </div>

      <Card title="Your edit" className="h-fit xl:sticky xl:top-4">
        <div className="space-y-4 p-4">
          <div className="flex items-center gap-3 rounded-xl bg-black/30 p-2">
            <span className="h-14 w-10 shrink-0 overflow-hidden rounded-md bg-black">{clip.thumbnail_url && <img src={mediaUrl(clip.thumbnail_url)} alt="" className="h-full w-full object-cover" />}</span>
            <span className="min-w-0">
              <span className="block truncate text-sm text-slate-200">{clip.filename}</span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-300"><CheckIcon width={11} height={11} /> transcript approved</span>
            </span>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium text-slate-400">What do you want? <span className="font-normal text-slate-500">(optional)</span></span>
            <Textarea rows={4} placeholder="e.g. punchy hook, highlight the price, show logo.png when I say the brand, pop.mp3 on each price" value={brief} onChange={(event) => setBrief(event.target.value)} />
          </label>
          <ResourcePicker resources={resources} selected={attached} onChange={setAttached} onUpload={onUploadResources} />
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-black/30 p-0.5">
            {(["fast", "agent"] as const).map((item) => (
              <button key={item} disabled={item === "fast" && !fast} onClick={() => setMode(item)} className={`rounded-md px-2 py-1.5 text-left transition disabled:opacity-40 ${effective === item ? "bg-accent text-white" : "text-slate-300 hover:bg-white/[0.06]"}`}>
                <span className="block text-xs font-semibold">{item === "fast" ? "Fast edit" : "Full agent"}</span>
                <span className="block text-[10px] opacity-80">{item === "fast" ? (chosen?.fast_engine === "generic" ? "1 call writes it · ~$0.30–0.80" : "1 plan call · ~$0.10–0.30") : "free-form · ~$1–3"}</span>
              </button>
            ))}
          </div>
          {!fast && <p className="text-[11px] text-slate-500">{prettyName(skill)} has no fast engine yet, so it runs as the full agent.</p>}
          {effective === "fast" && skill === "wassim-style" && (
            <label className="flex items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={quick} onChange={(event) => setQuick(event.target.checked)} /> Skip the speaker cut-out (much faster, no head pop-out)</label>
          )}
          {error && <p className="flex items-start gap-2 text-xs text-red-300"><AlertIcon className="mt-0.5 shrink-0" />{error}</p>}
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onBack}>Back</Button>
            <Button className="flex-1" onClick={() => void start()} disabled={busy}>{busy && <Spinner />}Start the edit</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

/**
 * The guided path: upload a clip, fix and approve its transcript, choose a
 * style, then watch the edit and ask for changes.
 */
export function CreateFlow({ step, onStep, clipId, onClip, assets, skills, run, runs, events, agentReady, onUpload, onRefreshAssets, onStart, onReply, onCancel, onSelectRun, result, onUploadResources }: {
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
  const clips = assets.filter((asset) => asset.kind === "video" && !isResource(asset));
  const resources = assets.filter(isResource);
  const clip = clips.find((item) => item.id === clipId);
  const approved = Boolean(clip?.transcript_reviewed);
  const clipRuns = runs.filter((item) => !clip || !item.asset_id || item.asset_id === clip.id);
  const styles = stylesFrom(skills);

  // A clip picked elsewhere (or a reload) lands on the right step.
  useEffect(() => {
    if (step === 2 && !clip) onStep(1);
  }, [step, clip, onStep]);

  const reachable = (target: Step) => target === 1 || (target === 2 && Boolean(clip)) || (target === 3 && approved) || (target === 4 && Boolean(run || clipRuns.length));

  return (
    <div className="space-y-5">
      <Stepper current={step} reachable={reachable} onGo={onStep} />

      {step === 1 && <UploadStep clips={clips} onUpload={onUpload} onPick={(asset) => { onClip(asset.id); onStep(asset.transcript_reviewed ? 3 : 2); }} />}

      {step === 2 && clip && (
        <TranscriptEditor assets={assets} assetId={clip.id} onChanged={onRefreshAssets} onApproved={() => onStep(3)} />
      )}

      {step === 3 && clip && (approved ? (
        <StyleStep styles={styles} clip={clip} resources={resources} onUploadResources={onUploadResources} onStart={async (brief, skill, options) => { await onStart(brief, skill, options); onStep(4); }} onBack={() => onStep(2)} />
      ) : (
        <Card><Empty icon={<AlertIcon />} title="Approve the transcript first">Captions use the transcript exactly as you approve it. <button className="font-semibold text-accent-soft underline" onClick={() => onStep(2)}>Go to the transcript</button></Empty></Card>
      ))}

      {step === 4 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
          <section className="min-w-0 space-y-4">{result}</section>
          <aside className="min-w-0 lg:sticky lg:top-4 lg:h-[calc(100vh-11rem)]">
            <AgentPanel
              projectId={clip?.project_id ?? run?.project_id}
              run={run}
              events={events}
              styles={styles}
              agentReady={agentReady}
              onStart={onStart}
              onReply={onReply}
              onCancel={onCancel}
              onNewRun={() => onStep(3)}
              clips={assets}
              resources={resources}
              onUploadResources={onUploadResources}
              runs={clipRuns}
              onSelectRun={onSelectRun}
              onReviewTranscript={() => onStep(2)}
            />
          </aside>
        </div>
      )}
    </div>
  );
}
