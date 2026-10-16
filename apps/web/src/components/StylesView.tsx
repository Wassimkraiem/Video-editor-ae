"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { RunEvent } from "../lib/agent-events";
import { API_URL, api, type Skill, type StyleClone } from "../lib/api-client";
import { subscribeSSE } from "../lib/sse";
import { ChatTranscript, stylesFrom } from "./AgentPanel";
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

function CloneLog({ clone }: { clone: StyleClone }) {
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
      {clone.status === "completed" && <p className="text-sm text-emerald-300">Style ready: pick <b>{clone.skill_name}</b> in the Edit tab and run it on any clip.</p>}
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

        <Card title="Clone jobs">
          {clones.length === 0 ? <Empty icon={<BookIcon />} title="No cloned styles yet">Your first clone appears here with a live log.</Empty> : (
            <>
              <ul className="flex gap-2 overflow-x-auto p-3">
                {clones.map((clone) => (
                  <li key={clone.id}>
                    <button onClick={() => setSelected(clone.id)} className={`min-w-[180px] rounded-lg border px-3 py-2 text-left transition ${selected === clone.id ? "border-accent/50 bg-accent/10" : "border-line hover:bg-white/[0.04]"}`}>
                      <span className="block text-sm font-medium text-slate-200">{clone.name}</span>
                      <span className="mt-1 flex items-center gap-2 text-[11px] text-slate-500"><StatusBadge status={clone.status === "completed" ? "succeeded" : ACTIVE.has(clone.status) ? "running" : clone.status} />{timeAgo(clone.created_at)}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {current && <CloneLog key={current.id} clone={current} />}
            </>
          )}
        </Card>
      </div>

      <Card title={<span className="flex items-center gap-2"><BookIcon className="text-slate-400" /> Your styles <Badge>{styles.length}</Badge></span>}>
        <ul className="scroll-quiet max-h-[calc(100vh-12rem)] space-y-2 overflow-auto p-3">
          {styles.map((skill) => (
            <li key={skill.id} className="rounded-xl border border-line bg-white/[0.02] p-3">
              <span className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-100">{skill.name}</span>
                <Badge tone={skill.scope === "user" ? "accent" : "neutral"} className="ml-auto">{skill.scope === "user" ? "cloned" : skill.scope === "library" ? "house" : "built-in"}</Badge>
              </span>
              <p className="mt-1 line-clamp-3 text-xs text-slate-400">{skill.description}</p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
