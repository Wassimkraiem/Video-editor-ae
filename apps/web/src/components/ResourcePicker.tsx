"use client";

import { useRef, useState } from "react";
import { mediaUrl, type Asset } from "../lib/api-client";
import { Spinner } from "./ui";
import { FileIcon, PlusIcon } from "./icons";

export const isResource = (asset: Asset) => asset.role === "resource";

function kindOf(asset: Asset) {
  if (asset.kind === "image") return "image";
  if (asset.kind === "audio") return "sound";
  return "video";
}

/**
 * Attach images, logos, screenshots, sounds or b-roll to an edit request.
 * Files upload as project resources (never transcribed) and can be reused
 * in later requests.
 */
export function ResourcePicker({ resources, selected, onChange, onUpload, compact = false }: {
  resources: Asset[];
  selected: string[];
  onChange: (ids: string[]) => void;
  onUpload: (files: File[]) => Promise<Asset[]>;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);

  async function add(files: FileList | null) {
    if (!files?.length) return;
    setUploading(true);
    setError("");
    try {
      const added = await onUpload(Array.from(files));
      onChange([...selected, ...added.map((asset) => asset.id)]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <div className="space-y-1.5">
      {!compact && <span className="block text-xs font-medium text-slate-400">Images, logos & sounds <span className="font-normal text-slate-500">(optional, say where in your request)</span></span>}
      <div className="flex flex-wrap items-center gap-1.5">
        {resources.map((asset) => {
          const on = selected.includes(asset.id);
          return (
            <button key={asset.id} type="button" onClick={() => toggle(asset.id)} title={on ? "Attached: click to remove" : "Click to attach"} className={`flex max-w-[180px] items-center gap-1.5 rounded-lg border py-1 pl-1 pr-2 text-[11px] transition ${on ? "border-accent/60 bg-accent/15 text-white" : "border-line bg-black/20 text-slate-400 hover:border-accent/40"}`}>
              <span className="flex h-6 w-6 shrink-0 items-center justify-center overflow-hidden rounded bg-black/40">
                {asset.thumbnail_url ? <img src={mediaUrl(asset.thumbnail_url)} alt="" className="h-full w-full object-cover" /> : <FileIcon width={12} height={12} />}
              </span>
              <span className="truncate">{asset.filename}</span>
              <span className="shrink-0 text-[10px] opacity-60">{kindOf(asset)}</span>
            </button>
          );
        })}
        <button type="button" onClick={() => input.current?.click()} disabled={uploading} className="flex items-center gap-1 rounded-lg border border-dashed border-line px-2 py-1.5 text-[11px] text-slate-400 transition hover:border-accent/50 hover:text-white disabled:opacity-50">
          {uploading ? <Spinner /> : <PlusIcon width={12} height={12} />} {compact ? "Attach" : "Add files"}
        </button>
        <input ref={input} type="file" multiple accept="image/*,audio/*,video/*" className="hidden" onChange={(event) => void add(event.target.files)} />
      </div>
      {error && <p className="text-[11px] text-red-300">{error}</p>}
    </div>
  );
}
