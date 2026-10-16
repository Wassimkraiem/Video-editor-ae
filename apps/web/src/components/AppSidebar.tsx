"use client";

import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import type { Health, Project } from "../lib/api-client";
import { Badge, Button, Input } from "./ui";
import { BookIcon, FilmIcon, LayersIcon, LogoutIcon, PlusIcon, SparkIcon } from "./icons";

export type View = "create" | "library" | "styles";

const NAV: { id: View; label: string; hint: string; icon: ReactNode }[] = [
  { id: "create", label: "Create", hint: "Upload → transcript → style → edit", icon: <SparkIcon width={18} height={18} /> },
  { id: "library", label: "Library", hint: "Raw, in progress, edited", icon: <LayersIcon width={18} height={18} /> },
  { id: "styles", label: "Styles", hint: "Your styles and cloning", icon: <BookIcon width={18} height={18} /> },
];

const WORKFLOWS = [
  { value: "raw-footage", label: "Talking-head / footage" },
  { value: "motion-graphics", label: "Motion graphics" },
  { value: "explainer", label: "Explainer (no footage)" },
];

/** The app's navigation: project, sections, account. Replaces the old top bar. */
export function AppSidebar({ view, onView, projects, activeId, onSelectProject, onCreateProject, reviewCount, health, email, onSignOut }: {
  view: View;
  onView: (view: View) => void;
  projects: Project[];
  activeId?: string;
  onSelectProject: (id: string) => void;
  onCreateProject: (name: string, workflow: string) => Promise<void>;
  reviewCount: number;
  health?: Health;
  email: string;
  onSignOut: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [workflow, setWorkflow] = useState("raw-footage");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    await onCreateProject(name.trim(), workflow);
    setName("");
    setCreating(false);
  }

  return (
    <aside className="sticky top-0 flex h-screen w-[248px] shrink-0 flex-col border-r border-line bg-panel/70 backdrop-blur">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow-glow"><FilmIcon width={18} height={18} /></div>
        <div>
          <p className="text-sm font-semibold text-white">Studio</p>
          <p className="text-[11px] text-slate-500">AI video editor</p>
        </div>
      </div>

      <div className="px-3">
        <div className="mb-1.5 flex items-center justify-between px-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Project</span>
          <button onClick={() => setCreating((value) => !value)} className="rounded-md p-1 text-slate-400 hover:bg-white/[0.06] hover:text-white" aria-label="New project"><PlusIcon width={14} height={14} /></button>
        </div>
        {creating || projects.length === 0 ? (
          <form onSubmit={(event) => void submit(event)} className="space-y-2 rounded-xl border border-line bg-black/20 p-2">
            <Input autoFocus placeholder="Project name" value={name} onChange={(event) => setName(event.target.value)} />
            <select value={workflow} onChange={(event) => setWorkflow(event.target.value)} className="h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-slate-200 outline-none">
              {WORKFLOWS.map((item) => <option key={item.value} value={item.value} className="bg-panel">{item.label}</option>)}
            </select>
            <Button type="submit" size="sm" className="w-full" disabled={!name.trim()}>Create project</Button>
          </form>
        ) : (
          <select aria-label="Project" value={activeId ?? ""} onChange={(event) => onSelectProject(event.target.value)} className="h-10 w-full truncate rounded-xl border border-line bg-black/30 px-3 text-sm font-medium text-slate-100 outline-none focus:border-accent/50">
            {projects.map((project) => <option key={project.id} value={project.id} className="bg-panel">{project.name}</option>)}
          </select>
        )}
      </div>

      <nav className="mt-5 flex-1 space-y-1 px-3">
        {NAV.map((item) => {
          const active = view === item.id;
          return (
            <button key={item.id} onClick={() => onView(item.id)} className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${active ? "bg-accent/15 text-white ring-1 ring-inset ring-accent/30" : "text-slate-400 hover:bg-white/[0.04] hover:text-white"}`}>
              <span className={active ? "text-accent-soft" : "text-slate-500 group-hover:text-slate-300"}>{item.icon}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{item.label}</span>
                <span className="block truncate text-[11px] text-slate-500">{item.hint}</span>
              </span>
              {item.id === "create" && reviewCount > 0 && <span className="rounded-full bg-amber-400/90 px-1.5 text-[10px] font-semibold text-ink" title="Transcripts waiting for your review">{reviewCount}</span>}
            </button>
          );
        })}
      </nav>

      <div className="space-y-2 border-t border-line p-3">
        {health && <Badge tone={health.agent_key_configured ? "success" : "warning"}>{health.worker === "local" ? "Local worker" : "Queue worker"}{health.agent_key_configured ? "" : " · no API key"}</Badge>}
        <div className="flex items-center gap-2">
          <span className="min-w-0 flex-1 truncate text-xs text-slate-500">{email}</span>
          <button onClick={onSignOut} className="rounded-lg p-2 text-slate-400 transition hover:bg-white/[0.06] hover:text-white" aria-label="Sign out"><LogoutIcon /></button>
        </div>
      </div>
    </aside>
  );
}
