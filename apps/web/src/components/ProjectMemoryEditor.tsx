"use client";

import { useEffect, useState } from "react";
import { Button, Card, Spinner, Textarea } from "./ui";
import { BookIcon, ChevronIcon } from "./icons";

type ProjectMemoryEditorProps = {
  projectId?: string;
  load: (projectId: string) => Promise<string>;
  onSave: (projectId: string, value: string) => Promise<void>;
};

/** Edits the project's CLAUDE.md, which the agent loads on every run. */
export function ProjectMemoryEditor({ projectId, load, onSave }: ProjectMemoryEditorProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState("");
  const [state, setState] = useState<"idle" | "loading" | "saving" | "error">("idle");

  useEffect(() => {
    if (!projectId || !open) return;
    let cancelled = false;
    setState("loading");
    load(projectId)
      .then((content) => { if (!cancelled) { setValue(content); setSaved(content); setState("idle"); } })
      .catch(() => { if (!cancelled) setState("error"); });
    return () => { cancelled = true; };
  }, [projectId, open, load]);

  async function save() {
    if (!projectId) return;
    setState("saving");
    try { await onSave(projectId, value); setSaved(value); setState("idle"); }
    catch { setState("error"); }
  }

  const dirty = value !== saved;
  return (
    <Card
      title={<button className="flex items-center gap-2" onClick={() => setOpen((current) => !current)}><BookIcon className="text-slate-400" /> Project memory <ChevronIcon className={`text-slate-500 transition ${open ? "rotate-90" : ""}`} /></button>}
      action={open && <Button size="sm" variant={dirty ? "primary" : "secondary"} onClick={() => void save()} disabled={!dirty || state === "saving" || !projectId}>{state === "saving" ? <Spinner /> : null}{dirty ? "Save" : "Saved"}</Button>}
    >
      {open && (
        <div className="p-3">
          <p className="mb-2 text-xs text-slate-500">Brand, palette, fonts and standing rules. Claude reads this <code className="font-mono">CLAUDE.md</code> before every edit in this project.</p>
          {state === "loading" ? <div className="flex h-40 items-center justify-center text-slate-500"><Spinner /></div> : (
            <Textarea className="min-h-[220px] font-mono text-xs leading-relaxed" value={value} onChange={(event) => setValue(event.target.value)} spellCheck={false} />
          )}
          {state === "error" && <p className="mt-2 text-xs text-red-300">Could not load or save memory.</p>}
        </div>
      )}
    </Card>
  );
}
