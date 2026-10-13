"use client";

import type { TimelineVersion } from "../lib/api-client";
import { Badge, Card, Empty, formatDuration } from "./ui";
import { LayersIcon } from "./icons";

const trackColors: Record<string, string> = {
  video: "bg-accent/70 ring-accent",
  audio: "bg-emerald-500/60 ring-emerald-400",
  caption: "bg-amber-500/60 ring-amber-400",
  graphics: "bg-fuchsia-500/60 ring-fuchsia-400",
};

export function TimelinePanel({ version }: { version?: TimelineVersion }) {
  const timeline = version?.data;
  const duration = Math.max(timeline?.duration_ms ?? 1, 1);
  const tracks = timeline?.tracks ?? [];

  return (
    <Card
      title="Timeline"
      action={timeline && <div className="flex items-center gap-2 text-[11px] text-slate-500"><Badge>v{version?.version}</Badge>{timeline.width}×{timeline.height} · {timeline.fps ?? 30} fps · {formatDuration(timeline.duration_ms)}</div>}
    >
      {tracks.length === 0 ? (
        <Empty icon={<LayersIcon />} title="Timeline is empty">Cut edits made by the agent land here. HyperFrames reels render straight to the preview.</Empty>
      ) : (
        <div className="space-y-2 p-4">
          <div className="ml-20 flex justify-between text-[10px] tabular-nums text-slate-500">
            {Array.from({ length: 6 }, (_, index) => <span key={index}>{formatDuration((duration / 5) * index) || "0:00"}</span>)}
          </div>
          {tracks.map((track) => (
            <div key={track.id} className="flex items-center gap-3">
              <div className="w-[68px] shrink-0 truncate text-[11px] font-medium uppercase tracking-wide text-slate-400">{track.type}</div>
              <div className="timeline-grid relative h-9 flex-1 rounded-lg bg-black/30 ring-1 ring-inset ring-line">
                {track.items?.map((item) => (
                  <div key={item.id} title={`${item.label ?? item.type} · ${formatDuration(item.start_ms) || "0:00"}–${formatDuration(item.end_ms)}`} className={`absolute inset-y-1 truncate rounded-md px-2 py-1 text-[11px] font-medium text-white ring-1 ring-inset ${trackColors[track.type] ?? "bg-slate-500/60 ring-slate-400"}`} style={{ left: `${(item.start_ms / duration) * 100}%`, width: `${Math.max(((item.end_ms - item.start_ms) / duration) * 100, 0.5)}%` }}>
                    {item.label ?? item.type}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
