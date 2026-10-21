/**
 * The manual editor's document and the pure operations on it (split, trim,
 * delete, move). Mirrors services/worker/manual_edit.py, which exports it.
 *
 * Captions are timed on the edit timeline but belong to the footage under
 * them, so every cut re-times them through `remapCaptions`. Text layers are
 * overlays on top of the timeline and keep their times.
 */

export type Clip = { id: string; asset_id: string; in_ms: number; out_ms: number; volume: number };
export type CaptionLine = { id: string; text: string; start_ms: number; end_ms: number };
export type CaptionStyle = { enabled: boolean; font: string; size: number; color: string; background: string | null; background_opacity: number; bold: boolean; y: number; uppercase: boolean };
export type TextLayer = { id: string; text: string; start_ms: number; end_ms: number; x: number; y: number; size: number; font: string; color: string; background: string | null; bold: boolean };
export type AudioSettings = { volume: number; normalize: boolean; denoise: boolean; fade_in_ms: number; fade_out_ms: number };
export type EditDoc = {
  id: string; name: string; width: number; height: number; fps: number;
  clips: Clip[]; captions: CaptionLine[]; caption_style: CaptionStyle; texts: TextLayer[]; audio: AudioSettings;
  created_at: string; updated_at: string;
};

export const FONTS = ["Inter Display", "Inter", "Noto Sans", "Noto Sans Arabic", "DejaVu Sans"];
export const MIN_CLIP_MS = 100;

export const newId = (prefix: string) => `${prefix}${Math.random().toString(36).slice(2, 10)}`;
export const clipLength = (clip: Clip) => clip.out_ms - clip.in_ms;
export const duration = (doc: Pick<EditDoc, "clips">) => doc.clips.reduce((total, clip) => total + clipLength(clip), 0);

/** Timeline start of every clip, in order. */
export function clipStarts(clips: Clip[]) {
  const starts: number[] = [];
  let at = 0;
  for (const clip of clips) { starts.push(at); at += clipLength(clip); }
  return starts;
}

/** The clip under a timeline time, and the matching time in its source. */
export function locate(clips: Clip[], time: number): { index: number; clip: Clip; start: number; source: number } | null {
  let start = 0;
  for (let index = 0; index < clips.length; index++) {
    const clip = clips[index];
    const length = clipLength(clip);
    if (time < start + length || index === clips.length - 1) {
      const offset = Math.min(Math.max(time - start, 0), length);
      return { index, clip, start, source: clip.in_ms + offset };
    }
    start += length;
  }
  return null;
}

/**
 * Where a moment of footage lands after the clips changed: the same clip if
 * it still covers it, else any clip showing that part of the same source
 * (split halves get new ids). Null when the footage was cut out.
 */
function remapTime(before: Clip[], after: Clip[], time: number): number | null {
  const found = locate(before, time);
  if (!found) return null;
  const { clip, source } = found;
  const starts = clipStarts(after);
  const covers = (item: Clip) => item.asset_id === clip.asset_id && source >= item.in_ms && source < item.out_ms;
  let index = after.findIndex((item) => item.id === clip.id && covers(item));
  if (index < 0) index = after.findIndex(covers);
  return index < 0 ? null : starts[index] + source - after[index].in_ms;
}

export function remapCaptions(captions: CaptionLine[], before: Clip[], after: Clip[]): CaptionLine[] {
  const total = duration({ clips: after });
  const out: CaptionLine[] = [];
  for (const line of captions) {
    const start = remapTime(before, after, line.start_ms);
    if (start === null) continue;
    const end = remapTime(before, after, Math.max(line.end_ms - 1, line.start_ms));
    // The end was cut but the start kept: stop the line where the footage now ends.
    const stop = end !== null && end > start ? end + 1 : Math.min(start + Math.max(line.end_ms - line.start_ms, 300), total);
    if (stop - start >= 80) out.push({ ...line, start_ms: start, end_ms: stop });
  }
  return out.sort((a, b) => a.start_ms - b.start_ms);
}

/** Apply new clips and keep captions and texts consistent with them. */
export function withClips(doc: EditDoc, clips: Clip[]): EditDoc {
  const total = duration({ clips });
  const texts = doc.texts
    .filter((layer) => layer.start_ms < total)
    .map((layer) => ({ ...layer, end_ms: Math.min(layer.end_ms, total) }))
    .filter((layer) => layer.end_ms - layer.start_ms >= 80);
  return { ...doc, clips, captions: remapCaptions(doc.captions, doc.clips, clips), texts };
}

export function splitAt(doc: EditDoc, time: number): EditDoc {
  const found = locate(doc.clips, time);
  if (!found) return doc;
  const { index, clip, source } = found;
  if (source - clip.in_ms < MIN_CLIP_MS || clip.out_ms - source < MIN_CLIP_MS) return doc;
  const clips = [...doc.clips];
  clips.splice(index, 1, { ...clip, out_ms: source }, { ...clip, id: newId("c"), in_ms: source });
  return withClips(doc, clips);
}

export function deleteClip(doc: EditDoc, id: string): EditDoc {
  if (doc.clips.length <= 1) return doc;
  return withClips(doc, doc.clips.filter((clip) => clip.id !== id));
}

/** Delete a timeline range across clips (e.g. a pause or a bad take). */
export function deleteRange(doc: EditDoc, from: number, to: number): EditDoc {
  if (to - from < 40) return doc;
  const edited = splitAt(splitAt(doc, to), from);
  const starts = clipStarts(edited.clips);
  const kept = edited.clips.filter((clip, index) => starts[index] + clipLength(clip) <= from + 1 || starts[index] >= to - 1);
  return kept.length ? withClips(edited, kept) : doc;
}

export function trimClip(doc: EditDoc, id: string, edge: "in" | "out", sourceMs: number, sourceDuration: number): EditDoc {
  const clips = doc.clips.map((clip) => {
    if (clip.id !== id) return clip;
    if (edge === "in") return { ...clip, in_ms: Math.round(Math.min(Math.max(sourceMs, 0), clip.out_ms - MIN_CLIP_MS)) };
    return { ...clip, out_ms: Math.round(Math.max(Math.min(sourceMs, sourceDuration || clip.out_ms), clip.in_ms + MIN_CLIP_MS)) };
  });
  return withClips(doc, clips);
}

export function moveClip(doc: EditDoc, id: string, by: -1 | 1): EditDoc {
  const index = doc.clips.findIndex((clip) => clip.id === id);
  const target = index + by;
  if (index < 0 || target < 0 || target >= doc.clips.length) return doc;
  const clips = [...doc.clips];
  [clips[index], clips[target]] = [clips[target], clips[index]];
  return withClips(doc, clips);
}

export function activeAt<T extends { start_ms: number; end_ms: number }>(items: T[], time: number) {
  return items.filter((item) => time >= item.start_ms && time < item.end_ms);
}

export function formatTime(ms: number) {
  const total = Math.max(ms, 0) / 1000;
  const minutes = Math.floor(total / 60);
  const seconds = total - minutes * 60;
  return `${minutes}:${seconds.toFixed(1).padStart(4, "0")}`;
}
