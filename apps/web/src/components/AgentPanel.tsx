"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { Asset, Run, Skill } from "../lib/api-client";
import { buildChat, type ChatItem, type RunEvent } from "../lib/agent-events";
import { Badge, Button, Card, Spinner, StatusBadge, Textarea } from "./ui";
import { ResourcePicker } from "./ResourcePicker";
import { AlertIcon, BookIcon, CheckIcon, ChevronIcon, FileIcon, SendIcon, SparkIcon, StopIcon, TerminalIcon } from "./icons";

/** House styles first; helper skills (hyperframes-*, media-use) stay out of the picker. */
const FEATURED = ["wassim-style", "devin-style", "talking-head-glass-edit", "kinetic-editorial-reel", "talking-head-recut", "product-launch-video", "product-launch-motion", "general-video"];
const HELPER = /^(hyperframes|media-use)/;

const PROMPTS: Record<string, string> = {
  "wassim-style": "Edit my latest clip in my house style. Darija captions with Latin tech words, keep the default blue palette.",
  "devin-style": "Turn my clip into a Devin-style reel with a studio background and glowing keyword captions.",
  "talking-head-glass-edit": "Make a premium social reel from my clip with glass cards, kinetic keywords and soft SFX.",
  "kinetic-editorial-reel": "Make a kinetic editorial reel about: ",
};

export function stylesFrom(skills: Skill[]) {
  const visible = skills.filter((skill) => skill.enabled && !HELPER.test(skill.name));
  return visible.sort((a, b) => {
    const rank = (skill: Skill) => { const index = FEATURED.indexOf(skill.name); return index === -1 ? (skill.scope === "user" ? 50 : 100 + (skill.scope === "library" ? 0 : 1)) : index; };
    return rank(a) - rank(b) || a.name.localeCompare(b.name);
  });
}

function prettyName(name: string) {
  return name.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function StylePicker({ styles, value, onChange }: { styles: Skill[]; value: string | null; onChange: (value: string | null) => void }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? styles : styles.slice(0, 5);
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">Style</span>
        {styles.length > 5 && <button className="text-[11px] text-slate-400 hover:text-white" onClick={() => setExpanded((open) => !open)}>{expanded ? "Fewer" : `All ${styles.length}`}</button>}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => onChange(null)} className={`rounded-full px-2.5 py-1 text-xs transition ${value === null ? "bg-white text-ink" : "bg-white/[0.05] text-slate-300 hover:bg-white/[0.1]"}`}>Auto</button>
        {shown.map((skill) => (
          <button key={skill.id} title={skill.description} onClick={() => onChange(skill.name === value ? null : skill.name)} className={`rounded-full px-2.5 py-1 text-xs transition ${value === skill.name ? "bg-accent text-white shadow-glow" : "bg-white/[0.05] text-slate-300 hover:bg-white/[0.1]"}`}>
            {prettyName(skill.name)}
          </button>
        ))}
      </div>
    </div>
  );
}

const toolIcon = (name: string) => (name === "Bash" ? <TerminalIcon /> : name === "Skill" ? <BookIcon /> : name.startsWith("mcp__") ? <SparkIcon /> : <FileIcon />);

function ToolRow({ item }: { item: Extract<ChatItem, { kind: "tool" }> }) {
  const [open, setOpen] = useState(false);
  const { call } = item;
  const pending = call.result === undefined;
  const isSkill = call.name === "Skill";
  return (
    <div className={`animate-fade-in rounded-lg border text-xs ${isSkill ? "border-accent/30 bg-accent/[0.07]" : "border-line bg-white/[0.02]"}`}>
      <button onClick={() => setOpen((value) => !value)} className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left">
        <span className={isSkill ? "text-accent-soft" : "text-slate-500"}>{toolIcon(call.name)}</span>
        <span className="shrink-0 font-medium capitalize text-slate-300">{call.label}</span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-slate-500">{call.detail}</span>
        {pending ? <Spinner className="text-slate-500" /> : call.isError ? <AlertIcon className="text-red-300" /> : <CheckIcon className="text-emerald-400" />}
        <ChevronIcon className={`text-slate-600 transition ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-line px-2.5 py-2">
          <pre className="scroll-quiet max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-slate-400">{JSON.stringify(call.input, null, 2)}</pre>
          {call.result !== undefined && <pre className={`scroll-quiet max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md bg-black/30 p-2 font-mono text-[11px] ${call.isError ? "text-red-300" : "text-slate-400"}`}>{call.result.slice(0, 6000) || "(no output)"}</pre>}
        </div>
      )}
    </div>
  );
}

function ChatRow({ item, onAnswer }: { item: ChatItem; onAnswer: (text: string) => void }) {
  switch (item.kind) {
    case "user":
      return (
        <div className="flex animate-fade-in justify-end">
          <div className="max-w-[88%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-sm text-white">
            {item.skill && <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-blue-100/80">{prettyName(item.skill)}</span>}
            <p className="whitespace-pre-wrap">{item.text}</p>
          </div>
        </div>
      );
    case "assistant":
      return <div className="prose-chat animate-fade-in whitespace-pre-wrap text-sm leading-relaxed text-slate-200">{item.text}</div>;
    case "thinking":
      return <p className="line-clamp-2 animate-fade-in border-l-2 border-line pl-3 text-xs italic text-slate-500">{item.text}</p>;
    case "tool":
      return <ToolRow item={item} />;
    case "question":
      return (
        <div className="animate-fade-in rounded-xl border border-amber-400/30 bg-amber-500/[0.07] p-3">
          <p className="text-sm text-amber-100">{item.question}</p>
          {item.options.length > 0 && <div className="mt-2 flex flex-wrap gap-1.5">{item.options.map((option) => <Button key={option} size="sm" variant="secondary" onClick={() => onAnswer(option)}>{option}</Button>)}</div>}
        </div>
      );
    case "status": {
      const tone = item.tone === "success" ? "text-emerald-300" : item.tone === "error" ? "text-red-300" : "text-sky-300";
      return (
        <div className="flex animate-fade-in items-start gap-2 py-1 text-xs">
          <span className={`mt-0.5 ${tone}`}>{item.tone === "success" ? <CheckIcon /> : item.tone === "error" ? <AlertIcon /> : <SparkIcon />}</span>
          <span className="min-w-0"><span className={tone}>{item.text}</span>{item.meta && <span className="ml-2 break-words text-slate-500">{item.meta}</span>}</span>
        </div>
      );
    }
  }
}

/** Read-only conversation view, shared by the agent panel and style cloning. */
export function ChatTranscript({ events, onAnswer }: { events: RunEvent[]; onAnswer?: (text: string) => void }) {
  const items = useMemo(() => buildChat(events), [events]);
  return <>{items.map((item) => <ChatRow key={item.key} item={item} onAnswer={(text) => onAnswer?.(text)} />)}</>;
}

export type StartOptions = { mode: "fast" | "agent"; assetId?: string; quick: boolean; resources?: string[] };

export function AgentPanel({ projectId, run, events, styles, agentReady, onStart, onReply, onCancel, onNewRun, clips, runs, onSelectRun, onReviewTranscript, resources = [], onUploadResources }: {
  projectId?: string;
  run?: Run;
  events: RunEvent[];
  styles: Skill[];
  agentReady: boolean;
  onStart: (brief: string, skill: string | null, options: StartOptions) => Promise<void>;
  onReply: (text: string, resources?: string[]) => Promise<void>;
  onCancel: () => Promise<void>;
  onNewRun: () => void;
  resources?: Asset[];
  onUploadResources?: (files: File[]) => Promise<Asset[]>;
  clips: Asset[];
  runs: Run[];
  onSelectRun: (run: Run) => void;
  onReviewTranscript: (assetId: string) => void;
}) {
  const [draft, setDraft] = useState("");
  const [skill, setSkill] = useState<string | null>("wassim-style");
  const [mode, setMode] = useState<"fast" | "agent">("fast");
  const [clipId, setClipId] = useState<string>();
  const [quick, setQuick] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [attached, setAttached] = useState<string[]>([]);
  const videos = clips.filter((clip) => clip.kind === "video" && clip.role !== "resource");
  const clip = videos.find((item) => item.id === clipId) ?? videos[0];
  const fastAvailable = Boolean(styles.find((style) => style.name === skill)?.fast);
  const effectiveMode = fastAvailable ? mode : "agent";
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const items = useMemo(() => buildChat(events), [events]);
  const working = run?.status === "queued" || run?.status === "running";
  const awaitingApproval = run?.status === "waiting_for_approval";

  useEffect(() => { if (!styles.some((style) => style.name === skill)) setSkill(styles[0]?.name ?? null); }, [styles, skill]);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }); }, [items.length]);

  async function send(text = draft) {
    if (!text.trim() || !projectId || sending) return;
    setSending(true);
    setError("");
    try {
      if (run && !working) await onReply(text.trim(), attached);
      else await onStart(text.trim(), skill, { mode: effectiveMode, assetId: clip?.id, quick: effectiveMode === "fast" && quick, resources: attached });
      setDraft("");
      setAttached([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not send");
    } finally {
      setSending(false);
    }
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); void send(); }
  }

  return (
    <Card
      className="flex h-full min-h-[560px] flex-col"
      title={<span className="flex items-center gap-2"><SparkIcon className="text-accent-soft" /> Agent</span>}
      action={
        <div className="flex items-center gap-2">
          <Button size="sm" variant={showHistory ? "secondary" : "ghost"} onClick={() => setShowHistory((open) => !open)}>History{runs.length ? ` (${runs.length})` : ""}</Button>
          {run && <StatusBadge status={run.status} />}
          {working && <Button size="sm" variant="danger" onClick={() => void onCancel()}><StopIcon width={12} height={12} /> Stop</Button>}
          {run && !working && <Button size="sm" variant="ghost" onClick={() => { onNewRun(); setDraft(""); }}>New edit</Button>}
        </div>
      }
    >
      <div ref={scroller} className="scroll-quiet flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {showHistory && (
          <ul className="space-y-1">
            {runs.length === 0 && <li className="text-xs text-slate-500">No chats yet.</li>}
            {runs.map((item) => (
              <li key={item.id}>
                <button onClick={() => { onSelectRun(item); setShowHistory(false); }} className={`w-full rounded-lg px-2.5 py-2 text-left transition ${run?.id === item.id ? "bg-accent/15 ring-1 ring-inset ring-accent/30" : "hover:bg-white/[0.04]"}`}>
                  <span className="line-clamp-2 text-xs text-slate-200" dir="auto">{item.brief}</span>
                  <span className="mt-1 flex items-center gap-2 text-[11px] text-slate-500"><StatusBadge status={item.status} />{item.skill}{item.mode === "fast" && <Badge tone="accent">fast</Badge>}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {!showHistory && !run && (
          <div className="flex h-full flex-col justify-center py-6">
            <p className="text-lg font-semibold tracking-tight text-white">What should we make?</p>
            <p className="mt-1 text-sm text-slate-400">Upload a clip, pick a style, and describe the edit. The agent plans, builds with HyperFrames, checks its work and renders.</p>
            <div className="mt-4 space-y-1.5">
              {Object.entries(PROMPTS).filter(([name]) => styles.some((style) => style.name === name)).slice(0, 3).map(([name, prompt]) => (
                <button key={name} onClick={() => { setSkill(name); setDraft(prompt); }} className="block w-full rounded-lg border border-line bg-white/[0.02] px-3 py-2 text-left text-xs text-slate-300 transition hover:border-accent/40 hover:bg-accent/[0.06]">
                  <span className="font-medium text-accent-soft">{prettyName(name)}</span> · {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
        {!showHistory && items.map((item) => <ChatRow key={item.key} item={item} onAnswer={(text) => void send(text)} />)}
        {working && <div className="flex items-center gap-2 text-xs text-slate-500"><Spinner /> {run?.status === "queued" ? "Waiting for the worker…" : "Working…"}</div>}
      </div>

      <div className="space-y-3 border-t border-line p-3">
        {!agentReady && <p className="flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200"><AlertIcon /> ANTHROPIC_API_KEY is not set on the server; runs will fail.</p>}
        {awaitingApproval ? (
          <div className="flex gap-2">
            <Button className="flex-1" onClick={() => void send("Approve")}>Approve storyboard</Button>
            <Button variant="secondary" onClick={() => void send("Revise")}>Request changes</Button>
          </div>
        ) : (
          <>
            {!run && <StylePicker styles={styles} value={skill} onChange={setSkill} />}
            {!run && (
              <div className="space-y-2 rounded-xl border border-line bg-white/[0.02] p-2.5">
                <div className="grid grid-cols-2 gap-1 rounded-lg bg-black/30 p-0.5">
                  {(["fast", "agent"] as const).map((item) => (
                    <button key={item} disabled={item === "fast" && !fastAvailable} onClick={() => setMode(item)} title={item === "fast" && !fastAvailable ? "This style has no fast engine yet" : undefined} className={`rounded-md px-2 py-1.5 text-left transition disabled:opacity-40 ${effectiveMode === item ? "bg-accent text-white" : "text-slate-300 hover:bg-white/[0.06]"}`}>
                      <span className="block text-xs font-semibold">{item === "fast" ? "Fast edit" : "Full agent"}</span>
                      <span className="block text-[10px] opacity-80">{item === "fast" ? (styles.find((style) => style.name === skill)?.fast_engine === "generic" ? "1 call writes it · ~$0.30–0.80" : "1 plan call · ~$0.10–0.30") : "free-form · ~$1–3"}</span>
                    </button>
                  ))}
                </div>
                {videos.length > 0 && (
                  <select value={clip?.id} onChange={(event) => setClipId(event.target.value)} className="h-8 w-full truncate rounded-md border border-line bg-black/30 px-2 text-xs text-slate-200 outline-none" aria-label="Clip">
                    {videos.map((item) => <option key={item.id} value={item.id} className="bg-panel">{item.filename}</option>)}
                  </select>
                )}
                {effectiveMode === "fast" && skill === "wassim-style" && (
                  <label className="flex items-center gap-2 text-[11px] text-slate-400"><input type="checkbox" checked={quick} onChange={(event) => setQuick(event.target.checked)} /> Skip the speaker cut-out (much faster, no head pop-out)</label>
                )}
                {clip && clip.transcript_status === "ready" && !clip.transcript_reviewed && (
                  <p className="flex items-center gap-2 text-[11px] text-amber-200"><AlertIcon className="shrink-0" /> The transcript isn't reviewed: captions use it exactly as it is. <button className="font-semibold underline" onClick={() => onReviewTranscript(clip.id)}>Review it</button></p>
                )}
              </div>
            )}
            <div className="relative">
              <Textarea
                rows={3}
                className="pr-12"
                placeholder={!projectId ? "Create a project first" : run ? (working ? "The agent is working…" : "Reply or ask for changes…") : "Describe the edit: cut the pauses, add captions, make it punchy…"}
                value={draft}
                disabled={!projectId || working}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKey}
              />
              <Button aria-label="Send" className="absolute bottom-2 right-2 h-8 w-8 !px-0" disabled={!projectId || working || !draft.trim() || sending} onClick={() => void send()}>
                {sending ? <Spinner /> : <SendIcon />}
              </Button>
            </div>
            {onUploadResources && <ResourcePicker compact resources={resources} selected={attached} onChange={setAttached} onUpload={onUploadResources} />}
            <div className="flex items-center justify-between text-[11px] text-slate-500">
              <span>{error ? <span className="text-red-300">{error}</span> : run?.skill ? <>Style: <Badge tone="accent">{prettyName(run.skill)}</Badge></> : "Ctrl + Enter to send"}</span>
              {typeof run?.usage?.total_cost_usd === "number" && <span>Cost so far ${(run.usage.total_cost_usd as number).toFixed(3)}</span>}
            </div>
          </>
        )}
      </div>
    </Card>
  );
}
