"use client";

import { Badge, Card, formatDuration } from "./ui";

export type StoryboardScene = {
  id: string;
  title: string;
  start_ms: number;
  end_ms: number;
  assets: string[];
  template: string;
  notes?: string;
};

export type Storyboard = {
  project_id: string;
  brief: string;
  scenes: StoryboardScene[];
  status: "awaiting_approval" | "approved" | "revision_requested";
};

const statusTone = { awaiting_approval: "warning", approved: "success", revision_requested: "error" } as const;

/** Read-only plan view; approval happens in the agent panel. */
export function StoryboardPanel({ storyboard }: { storyboard: Storyboard }) {
  return (
    <Card title="Storyboard" action={<Badge tone={statusTone[storyboard.status]}>{storyboard.status.replace(/_/g, " ")}</Badge>}>
      <ol className="space-y-1.5 p-3">
        {storyboard.scenes.map((scene, index) => (
          <li key={scene.id} className="flex items-start gap-3 rounded-lg bg-white/[0.02] px-3 py-2">
            <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-accent/15 text-[10px] font-semibold text-accent-soft">{index + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-slate-200">{scene.title}</span>
              <span className="block text-[11px] text-slate-500">
                {formatDuration(scene.start_ms) || "0:00"}–{formatDuration(scene.end_ms)} · {scene.template || "custom"}
                {scene.assets.length > 0 && ` · ${scene.assets.join(", ")}`}
              </span>
              {scene.notes && <span className="mt-1 block text-xs text-slate-400">{scene.notes}</span>}
            </span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
