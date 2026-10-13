"use client";

import { useRef, useState } from "react";
import type { DragEvent, FormEvent } from "react";
import type { Asset, Project } from "../lib/api-client";
import { Badge, Button, Card, Empty, Input, StatusBadge, formatBytes, formatDuration } from "./ui";
import { FilmIcon, PlusIcon, UploadIcon } from "./icons";

const WORKFLOWS = [
  { value: "raw-footage", label: "Talking-head / footage" },
  { value: "motion-graphics", label: "Motion graphics" },
  { value: "explainer", label: "Explainer (no footage)" },
];

export function ProjectList({ projects, activeId, onSelect, onCreate }: { projects: Project[]; activeId?: string; onSelect: (id: string) => void; onCreate: (name: string, workflow: string) => Promise<void> }) {
  const [toggled, setToggled] = useState(false);
  // Always offer the form when there is nothing to pick from.
  const creating = toggled || projects.length === 0;
  const [name, setName] = useState("");
  const [workflow, setWorkflow] = useState("raw-footage");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    await onCreate(name.trim(), workflow);
    setName("");
    setToggled(false);
  }

  return (
    <Card title="Projects" action={<Button size="sm" variant="ghost" onClick={() => setToggled((value) => !value)} aria-label="New project"><PlusIcon /></Button>}>
      {creating && (
        <form onSubmit={(event) => void submit(event)} className="space-y-2 border-b border-line p-3">
          <Input autoFocus placeholder="Project name" value={name} onChange={(event) => setName(event.target.value)} />
          <select className="h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-slate-200 outline-none focus:border-accent/60" value={workflow} onChange={(event) => setWorkflow(event.target.value)}>
            {WORKFLOWS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <Button type="submit" size="sm" className="w-full" disabled={!name.trim()}>Create project</Button>
        </form>
      )}
      <nav className="scroll-quiet max-h-64 space-y-0.5 overflow-auto p-2">
        {projects.map((project) => (
          <button key={project.id} onClick={() => onSelect(project.id)} className={`group flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition ${activeId === project.id ? "bg-accent/15 text-white ring-1 ring-inset ring-accent/30" : "text-slate-300 hover:bg-white/[0.04]"}`}>
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${activeId === project.id ? "bg-accent" : "bg-slate-600 group-hover:bg-slate-400"}`} />
            <span className="min-w-0 flex-1 truncate">{project.name}</span>
            <span className="shrink-0 text-[10px] uppercase tracking-wide text-slate-500">{project.workflow.split("-")[0]}</span>
          </button>
        ))}
      </nav>
    </Card>
  );
}

export function AssetLibrary({ assets, onUpload, onPreview, disabled }: { assets: Asset[]; onUpload: (files: File[]) => Promise<void>; onPreview: (asset: Asset) => void; disabled?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState("");

  async function upload(files: File[]) {
    if (!files.length || disabled) return;
    setError("");
    setUploading(files.length);
    try { await onUpload(files); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Upload failed"); }
    finally { setUploading(0); }
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  }

  return (
    <Card title={<span className="flex items-center gap-2">Media <Badge>{assets.length}</Badge></span>}>
      <div className="p-3">
        <button
          type="button"
          disabled={disabled}
          onClick={() => input.current?.click()}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={drop}
          className={`flex w-full flex-col items-center gap-1.5 rounded-xl border border-dashed px-3 py-4 text-center transition disabled:opacity-40 ${dragging ? "border-accent bg-accent/10" : "border-slate-600/50 hover:border-accent/50 hover:bg-white/[0.02]"}`}
        >
          <UploadIcon className="text-accent-soft" width={18} height={18} />
          <span className="text-xs font-medium text-slate-200">{uploading ? `Uploading ${uploading} file${uploading > 1 ? "s" : ""}…` : "Drop clips or click to upload"}</span>
          <span className="text-[11px] text-slate-500">Video, audio, images, screenshots</span>
        </button>
        <input ref={input} className="hidden" type="file" multiple accept="video/*,audio/*,image/*" onChange={(event) => { void upload(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
        {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
      </div>
      <ul className="scroll-quiet max-h-72 space-y-1 overflow-auto px-2 pb-2">
        {assets.length === 0 && <Empty icon={<FilmIcon />} title="No media yet">Upload a talking-head clip, then ask the agent to edit it.</Empty>}
        {assets.map((asset) => (
          <li key={asset.id}>
            <button onClick={() => onPreview(asset)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition hover:bg-white/[0.04]">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white/[0.05] text-[10px] font-semibold uppercase text-slate-400">{asset.kind.slice(0, 3)}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium text-slate-200">{asset.filename}</span>
                <span className="block text-[11px] text-slate-500">
                  {[formatBytes(asset.size_bytes), formatDuration(asset.probe?.duration_ms), asset.probe?.width ? `${asset.probe.width}×${asset.probe.height}` : ""].filter(Boolean).join(" · ")}
                </span>
              </span>
              {asset.status !== "ready" && <StatusBadge status={asset.status === "uploaded" ? "running" : asset.status} />}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
