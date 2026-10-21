"use client";

import { useMemo, useRef, useState } from "react";
import type { MouseEvent } from "react";
import type { Output, Project } from "../lib/api-client";
import { api, mediaUrl } from "../lib/api-client";
import { timeAgo } from "./ChatList";
import { StyleBadge } from "./LibraryView";
import { Empty, Input, Spinner, formatDuration } from "./ui";
import { PlayIcon } from "./icons";

export type Video = { project: Project; output: Output };

function styleLabel(skill?: string | null) {
  return skill ? skill.replace(/-style$/, "").replace(/-/g, " ") : "custom";
}

function TrailerLink({ video }: { video: Video }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  async function use(event: MouseEvent) {
    event.stopPropagation();
    setState("busy");
    try {
      await api.setSkillPreview(String(video.output.skill), { project_id: video.project.id, path: video.output.path });
      setState("done");
    } catch {
      setState("error");
    }
  }
  return (
    <span role="button" tabIndex={0} onClick={(event) => void use(event)} onKeyDown={(event) => { if (event.key === "Enter") void use(event as unknown as MouseEvent); }} className="mt-1 inline-block text-[11px] text-slate-500 underline-offset-2 hover:text-accent-soft hover:underline">
      {state === "done" ? "Set as style trailer ✓" : state === "busy" ? "Setting…" : state === "error" ? "Could not set the trailer" : "Use as style trailer"}
    </span>
  );
}

function VideoCard({ video, onOpen }: { video: Video; onOpen: () => void }) {
  const player = useRef<HTMLVideoElement>(null);
  const [duration, setDuration] = useState<number>();
  const { output, project } = video;
  const src = mediaUrl(output.url);

  // Hovering plays a muted preview, like a YouTube thumbnail.
  function hover(on: boolean) {
    const element = player.current;
    if (!element) return;
    if (on) void element.play().catch(() => undefined);
    else { element.pause(); element.currentTime = 1; }
  }

  return (
    <button onClick={onOpen} onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)} className="group text-left">
      <span className="relative block aspect-[9/16] overflow-hidden rounded-2xl bg-black ring-1 ring-line transition group-hover:ring-accent/60">
        <video ref={player} src={`${src}#t=1`} preload="metadata" muted loop playsInline onLoadedMetadata={(event) => setDuration(event.currentTarget.duration * 1000)} className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]" />
        <span className="absolute left-2 top-2"><StyleBadge skill={output.skill} /></span>
        {duration ? <span className="absolute bottom-2 right-2 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-white">{formatDuration(duration)}</span> : null}
        <span className="absolute inset-0 flex items-center justify-center opacity-0 transition group-hover:opacity-100">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-black/50 text-white backdrop-blur"><PlayIcon width={20} height={20} /></span>
        </span>
      </span>
      <span className="mt-2.5 block line-clamp-2 text-sm font-medium leading-snug text-slate-100 group-hover:text-white" dir="auto">{output.title || output.name}</span>
      <span className="mt-0.5 block truncate text-xs text-slate-500">{project.name} · {timeAgo(output.modified_at)}</span>
      {output.skill && output.skill !== "manual" && <TrailerLink video={video} />}
    </button>
  );
}

/** Every finished video across all projects, re-renders included, filterable by style. */
export function VideosView({ videos, loading, onOpen }: { videos: Video[]; loading: boolean; onOpen: (video: Video) => void }) {
  const [style, setStyle] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");

  const styles = useMemo(() => {
    const counts = new Map<string, number>();
    for (const video of videos) {
      const key = video.output.skill ?? "";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [videos]);

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return videos
      .filter((video) => style === null || (video.output.skill ?? "") === style)
      .filter((video) => !needle || `${video.output.title ?? video.output.name} ${video.project.name} ${video.output.skill ?? ""}`.toLowerCase().includes(needle))
      .sort((a, b) => (sort === "newest" ? -1 : 1) * a.output.modified_at.localeCompare(b.output.modified_at));
  }, [videos, style, query, sort]);

  if (loading && videos.length === 0) return <div className="flex justify-center py-24 text-slate-500"><Spinner /></div>;
  if (videos.length === 0) return <Empty icon={<PlayIcon />} title="No edited videos yet">Finished edits from every project show up here, sorted by style.</Empty>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div className="scroll-quiet flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
          <button onClick={() => setStyle(null)} className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition ${style === null ? "bg-white text-ink" : "bg-white/[0.06] text-slate-200 hover:bg-white/[0.1]"}`}>All <span className="opacity-60">{videos.length}</span></button>
          {styles.map(([name, count]) => (
            <button key={name || "custom"} onClick={() => setStyle(name === style ? null : name)} className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium capitalize transition ${style === name ? "bg-white text-ink" : "bg-white/[0.06] text-slate-200 hover:bg-white/[0.1]"}`}>
              {styleLabel(name || null)} <span className="opacity-60">{count}</span>
            </button>
          ))}
        </div>
        <Input className="h-9 w-56" placeholder="Search videos" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select aria-label="Sort" value={sort} onChange={(event) => setSort(event.target.value as "newest" | "oldest")} className="h-9 rounded-lg border border-line bg-black/30 px-2 text-sm text-slate-200 outline-none">
          <option value="newest" className="bg-panel">Newest</option>
          <option value="oldest" className="bg-panel">Oldest</option>
        </select>
      </div>

      {shown.length === 0 ? (
        <Empty icon={<PlayIcon />} title="No match">Try another style or search.</Empty>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
          {shown.map((video) => <VideoCard key={`${video.project.id}:${video.output.path}`} video={video} onOpen={() => onOpen(video)} />)}
        </div>
      )}
    </div>
  );
}
