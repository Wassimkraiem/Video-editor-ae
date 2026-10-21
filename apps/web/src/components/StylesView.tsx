"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { RunEvent } from "../lib/agent-events";
import { API_URL, api, type Skill, type StyleClone } from "../lib/api-client";
import { subscribeSSE } from "../lib/sse";
import { ChatTranscript, stylesFrom } from "./AgentPanel";
import { StylePreview } from "./StylePreview";
import { timeAgo } from "./ChatList";
import { Badge, Button, Card, Empty, Input, Spinner, StatusBadge, Textarea } from "./ui";
import { BookIcon, SparkIcon } from "./icons";

// Proven engines a clone can fork; "" lets the agent pick the closest.
const BASES = [
  { value: "", label: "Auto: closest match" },
  { value: "wassim-style", label: "Wassim style engine" },
  { value: "devin-style", label: "Devin style engine" },
  { value: "talking-head-glass-edit", label: "Glass edit engine" },
  { value: "kinetic-editorial-reel", label: "Kinetic editorial engine" },
];
const ACTIVE = new Set(["queued", "downloading", "analyzing"]);

/** Ask Claude to change a style. Built-in styles are saved as a new one. */
function ModifyStyle({ skill, onStarted, onClose }: { skill: Skill; onStarted: (job: StyleClone) => void; onClose: () => void }) {
  const builtIn = skill.scope !== "user";
  const [request, setRequest] = useState("");
  const [saveAs, setSaveAs] = useState(builtIn ? `${skill.name}-custom` : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function start() {
    setBusy(true);
    setError("");
    try {
      onStarted(await api.editSkill({ skill: skill.name, request: request.trim(), save_as: saveAs.trim() || null }));
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start the edit");
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2 border-t border-line pt-3">
      <Textarea rows={4} autoFocus placeholder="What should change? e.g. keyword box yellow instead of blue; captions a bit lower; no sound effects; Cairo font for Arabic; slower zooms" value={request} onChange={(event) => setRequest(event.target.value)} />
      <label className="block">
        <span className="mb-1 block text-[11px] font-medium text-slate-400">{builtIn ? "Save as (built-in styles stay as they are)" : "Save as a new style (optional; empty = change this one)"}</span>
        <Input value={saveAs} placeholder={builtIn ? "" : skill.name} onChange={(event) => setSaveAs(event.target.value)} />
      </label>
      {error && <p className="text-xs text-red-300">{error}</p>}
      <div className="flex items-center gap-2">
        <span className="mr-auto text-[11px] text-slate-500">Claude edits a copy; uses agent credits (usually less than a clone).</span>
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button size="sm" onClick={() => void start()} disabled={busy || request.trim().length < 3 || (builtIn && saveAs.trim().length < 2)}>{busy && <Spinner />}Modify</Button>
      </div>
    </div>
  );
}

function CloneLog({ clone, onMoreChanges }: { clone: StyleClone; onMoreChanges: (name: string) => void }) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    setEvents([]);
    return subscribeSSE<RunEvent>(`${API_URL}/style-extractions/${clone.id}/events`, ({ id, data }) => {
      setEvents((current) => (current.some((event) => event.id === id) ? current : [...current, { ...data, id }]));
    });
  }, [clone.id]);
  useEffect(() => { scroller.current?.scrollTo({ top: scroller.current.scrollHeight }); }, [events.length]);
  return (
    <div ref={scroller} className="scroll-quiet max-h-[420px] space-y-3 overflow-y-auto border-t border-line p-4">
      {events.length === 0 && <p className="text-xs text-slate-500">Waiting for the worker…</p>}
      <ChatTranscript events={events} />
      {clone.kind === "edit" && <p className="rounded-lg bg-white/[0.03] px-3 py-2 text-xs text-slate-400"><span className="font-medium text-slate-300">Requested change{clone.base && clone.base !== clone.name ? ` (from ${clone.base})` : ""}:</span> {clone.notes}</p>}
      {clone.status === "completed" && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-emerald-300">
          {clone.kind === "edit" ? <>Style updated: <b>{clone.skill_name}</b> uses your change from the next edit on.</> : <>Style ready: pick <b>{clone.skill_name}</b> in the Edit tab and run it on any clip.</>}
          {clone.skill_name && <Button size="sm" variant="secondary" onClick={() => onMoreChanges(clone.skill_name as string)}>Ask for more changes</Button>}
        </p>
      )}
      {clone.status === "failed" && <p className="text-sm text-red-300">{clone.error}</p>}
    </div>
  );
}

/** Clone an editing style from reference videos and browse every style. */
export function StylesView({ skills, onSkillsChanged }: { skills: Skill[]; onSkillsChanged: () => void }) {
  const [clones, setClones] = useState<StyleClone[]>([]);
  const [selected, setSelected] = useState<string>();
  const [urls, setUrls] = useState("");
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [base, setBase] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [modifying, setModifying] = useState<string>();
  const [notice, setNotice] = useState("");
  const [trailers, setTrailers] = useState<string[]>([]);
  const anyActive = clones.some((clone) => ACTIVE.has(clone.status));

  useEffect(() => {
    void api.styleClones().then((items) => { setClones(items); setSelected((current) => current ?? items[0]?.id); }).catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!anyActive) return;
    const timer = setInterval(() => {
      void api.styleClones().then((items) => {
        setClones(items);
        if (!items.some((clone) => ACTIVE.has(clone.status))) onSkillsChanged();
      });
    }, 3000);
    return () => clearInterval(timer);
  }, [anyActive, onSkillsChanged]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const list = urls.split(/[\s,]+/).map((url) => url.trim()).filter(Boolean);
      const clone = await api.cloneStyle({ urls: list, name, notes, base: base || null });
      setClones((current) => [clone, ...current]);
      setSelected(clone.id);
      setUrls(""); setName(""); setNotes(""); setBase("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start");
    } finally {
      setBusy(false);
    }
  }

  function started(job: StyleClone) {
    setClones((current) => [job, ...current]);
    setSelected(job.id);
  }

  // Refresh the list while trailers are being made, so they appear when ready.
  useEffect(() => {
    if (!trailers.length) return;
    const timer = setInterval(onSkillsChanged, 20000);
    const stop = setTimeout(() => setTrailers([]), 20 * 60 * 1000);
    return () => { clearInterval(timer); clearTimeout(stop); };
  }, [trailers.length, onSkillsChanged]);
  useEffect(() => { setTrailers((current) => current.filter((name) => !skills.find((skill) => skill.name === name)?.preview_url)); }, [skills]);

  async function makeTrailer(skill: Skill) {
    if (!window.confirm(`Make a ~15 s demo of ${skill.name} as its trailer? It runs one fast edit (about $0.30-0.80 in credits) in a "Style previews" project.`)) return;
    try {
      await api.generateSkillPreview(skill.name);
      setTrailers((current) => [...current, skill.name]);
      setNotice(`Making the ${skill.name} trailer: it appears here in a few minutes.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Could not start the trailer");
    }
  }

  async function undo(skill: Skill) {
    if (!window.confirm(`Undo the last change to ${skill.name}? The version before it comes back.`)) return;
    setNotice("");
    try {
      await api.restoreSkill(skill.name);
      setNotice(`${skill.name}: previous version restored.`);
      onSkillsChanged();
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Nothing to undo");
    }
  }

  // Cloned styles first, then the house styles in featured order, then built-ins.
  const ordered = stylesFrom(skills);
  const styles = [...ordered.filter((skill) => skill.scope === "user"), ...ordered.filter((skill) => skill.scope !== "user")];
  const current = clones.find((clone) => clone.id === selected);

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-4">
        <Card title={<span className="flex items-center gap-2"><SparkIcon className="text-accent-soft" /> Clone a style from a video</span>}>
          <form onSubmit={(event) => void submit(event)} className="space-y-3 p-4">
            <p className="text-sm text-slate-400">Paste reference reels (YouTube, Instagram, TikTok or a direct .mp4). The agent forks one of your proven style engines and restyles it to match: captions, typography, colours, scenes, motion graphics and sounds, all timed to the words. It copies the style, never the videos.</p>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-400">Reference videos <span className="font-normal text-slate-500">(separate with commas or new lines, up to 6)</span></span>
              <Textarea rows={2} placeholder="https://www.instagram.com/reel/…, https://www.youtube.com/shorts/…" value={urls} onChange={(event) => setUrls(event.target.value)} required />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-slate-400">Style name</span>
                <Input placeholder="e.g. neon-podcast" value={name} onChange={(event) => setName(event.target.value)} required minLength={2} />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-slate-400">Start from</span>
                <select value={base} onChange={(event) => setBase(event.target.value)} className="h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-slate-200 outline-none focus:border-accent/50">
                  {BASES.map((item) => <option key={item.value} value={item.value} className="bg-panel">{item.label}</option>)}
                </select>
              </label>
            </div>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-400">Your changes <span className="font-normal text-slate-500">(these win over the references)</span></span>
              <Textarea rows={4} placeholder="e.g. keep their caption animation but use my blue palette; no emojis; Cairo font for Arabic; calmer zooms; a cleaner end card" value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
            {error && <p className="text-xs text-red-300">{error}</p>}
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-slate-500">Takes several minutes and uses agent credits.</span>
              <Button type="submit" disabled={busy || !urls.trim() || name.trim().length < 2}>{busy && <Spinner />}Clone style</Button>
            </div>
          </form>
        </Card>

        <Card title="Style jobs">
          {clones.length === 0 ? <Empty icon={<BookIcon />} title="No style jobs yet">Clones and changes you ask Claude for appear here with a live log.</Empty> : (
            <>
              <ul className="flex gap-2 overflow-x-auto p-3">
                {clones.map((clone) => (
                  <li key={clone.id}>
                    <button onClick={() => setSelected(clone.id)} className={`min-w-[180px] rounded-lg border px-3 py-2 text-left transition ${selected === clone.id ? "border-accent/50 bg-accent/10" : "border-line hover:bg-white/[0.04]"}`}>
                      <span className="flex items-center gap-1.5 text-sm font-medium text-slate-200">{clone.name}{clone.kind === "edit" && <Badge tone="accent">edit</Badge>}</span>
                      <span className="mt-1 flex items-center gap-2 text-[11px] text-slate-500"><StatusBadge status={clone.status === "completed" ? "succeeded" : ACTIVE.has(clone.status) ? "running" : clone.status} />{timeAgo(clone.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {current && <CloneLog key={current.id} clone={current} onMoreChanges={setModifying} />}
            </>
          )}
        </Card>
      </div>

      <Card title={<span className="flex items-center gap-2"><BookIcon className="text-slate-400" /> Your styles <Badge>{styles.length}</Badge></span>}>
        {notice && <p className="mx-3 mt-3 rounded-lg bg-white/[0.04] px-3 py-2 text-xs text-slate-300">{notice}</p>}
        <ul className="scroll-quiet max-h-[calc(100vh-12rem)] space-y-2 overflow-auto p-3">
          {styles.map((skill) => (
            <li key={skill.id} className="flex gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
              <StylePreview skill={skill} className="w-20 self-start" />
              <div className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-100">{skill.name}</span>
                <Badge tone={skill.scope === "user" ? "accent" : "neutral"} className="ml-auto">{skill.scope === "user" ? "cloned" : skill.scope === "library" ? "house" : "built-in"}</Badge>
              </span>
              <p className="mt-1 line-clamp-3 text-xs text-slate-400">{skill.description}</p>
              {modifying === skill.name ? (
                <ModifyStyle skill={skill} onStarted={started} onClose={() => setModifying(undefined)} />
              ) : (
                <div className="mt-2 flex gap-1.5">
                  <Button size="sm" variant="secondary" onClick={() => setModifying(skill.name)} disabled={clones.some((clone) => clone.kind === "edit" && clone.name === skill.name && ACTIVE.has(clone.status))}><SparkIcon width={12} height={12} /> Modify with Claude</Button>
                  {skill.scope === "user" && <Button size="sm" variant="ghost" onClick={() => void undo(skill)}>Undo last edit</Button>}
                  {!skill.preview_url && (trailers.includes(skill.name) ? <span className="flex items-center gap-1.5 text-[11px] text-slate-400"><Spinner /> Trailer…</span> : <Button size="sm" variant="ghost" onClick={() => void makeTrailer(skill)}>Make a trailer</Button>)}
                </div>
              )}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
