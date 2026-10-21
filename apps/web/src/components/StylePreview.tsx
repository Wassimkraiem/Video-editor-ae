"use client";

import { useRef } from "react";
import { mediaUrl, type Skill } from "../lib/api-client";
import { SparkIcon } from "./icons";

/** A style's cover; hovering plays its trailer (muted, looping). */
export function StylePreview({ skill, className = "" }: { skill: Skill; className?: string }) {
  const player = useRef<HTMLVideoElement>(null);
  const hover = (on: boolean) => {
    const element = player.current;
    if (!element) return;
    if (on) void element.play().catch(() => undefined);
    else { element.pause(); element.currentTime = 0; }
  };
  return (
    <span onMouseEnter={() => hover(true)} onMouseLeave={() => hover(false)} className={`relative block aspect-[9/16] shrink-0 overflow-hidden rounded-lg bg-black/60 ring-1 ring-line ${className}`}>
      {skill.cover_url && <img src={mediaUrl(skill.cover_url)} alt="" className="absolute inset-0 h-full w-full object-cover" />}
      {skill.preview_url && <video ref={player} src={mediaUrl(skill.preview_url)} muted loop playsInline preload="none" className="absolute inset-0 h-full w-full object-cover opacity-0 transition-opacity duration-200" onPlaying={(event) => { event.currentTarget.style.opacity = "1"; }} onPause={(event) => { event.currentTarget.style.opacity = "0"; }} />}
      {!skill.cover_url && <span className="absolute inset-0 flex items-center justify-center text-slate-600"><SparkIcon width={18} height={18} /></span>}
    </span>
  );
}
