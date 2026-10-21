"use client";

import type { Output, Render } from "../lib/api-client";
import { mediaUrl } from "../lib/api-client";
import { Badge, Button, Card, Empty, Spinner, formatBytes } from "./ui";
import { DownloadIcon, PlayIcon } from "./icons";

export type PreviewSource = { url: string; title: string; subtitle?: string; composition?: string | null; skill?: string | null };

export function PreviewPanel({ source, outputs, renders, onSelect, onRender, canRender, onOpenInStudio, working = false }: {
  source?: PreviewSource;
  outputs: Output[];
  renders: Render[];
  onSelect: (source: PreviewSource) => void;
  onRender: () => void;
  canRender: boolean;
  onOpenInStudio: (composition: string) => void;
  working?: boolean;
}) {
  const active = renders.find((render) => render.status === "queued" || render.status === "running");
  const failed = renders.find((render) => render.status === "failed");

  return (
    <Card
      title={source ? <span className="flex items-center gap-2 truncate">{source.title}{source.subtitle && <span className="font-normal text-slate-500">{source.subtitle}</span>}</span> : "Preview"}
      action={
        <div className="flex items-center gap-2">
          {source?.composition && <Button size="sm" variant="secondary" onClick={() => onOpenInStudio(source.composition as string)}>Open in Studio</Button>}
          {source && <a href={mediaUrl(source.url)} download className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs text-slate-300 hover:bg-white/[0.06]"><DownloadIcon /> Download</a>}
          <Button size="sm" variant="secondary" onClick={onRender} disabled={!canRender || Boolean(active)}>{active ? <><Spinner /> Rendering</> : "Render"}</Button>
        </div>
      }
    >
      <div className="p-3">
        <div className="relative flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-black ring-1 ring-line">
          {source ? (
            <video key={source.url} src={mediaUrl(source.url)} controls playsInline className="h-full w-full object-contain" />
          ) : (
            working ? <div className="flex items-center gap-2 text-sm text-slate-400"><Spinner /> Your video is being edited…</div> : <Empty icon={<PlayIcon />} title="No video yet">This edit's video appears here when it's ready. Other videos are in the Library.</Empty>
          )}
        </div>
        {failed && !active && <p className="mt-2 truncate rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-200" title={failed.error ?? undefined}>Last render failed: {failed.error ?? "unknown error"}</p>}
        {outputs.length > 1 && (
          <div className="scroll-quiet mt-3 flex gap-2 overflow-x-auto pb-1">
            {outputs.map((output) => {
              const selected = source?.url === output.url;
              return (
                <button key={output.path} onClick={() => onSelect({ url: output.url, title: output.title || output.name, subtitle: output.skill ?? undefined, composition: output.composition, skill: output.skill })} className={`flex min-w-[180px] items-center gap-2.5 rounded-lg border px-2.5 py-2 text-left transition ${selected ? "border-accent/50 bg-accent/10" : "border-line bg-white/[0.02] hover:bg-white/[0.05]"}`}>
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-accent/15 text-accent-soft"><PlayIcon width={14} height={14} /></span>
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium text-slate-200" dir="auto">{output.title || output.name}</span>
                    {output.skill && <span className="block truncate text-[10px] font-semibold uppercase tracking-wide text-accent-soft">{output.skill}</span>}
                    <span className="block text-[11px] text-slate-500">{formatBytes(output.size_bytes)} · {new Date(output.modified_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  </span>
                  {selected && <Badge tone="accent" className="ml-auto">Playing</Badge>}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
}
