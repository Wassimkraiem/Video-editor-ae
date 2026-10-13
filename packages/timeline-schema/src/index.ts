export type TrackType = "video" | "audio" | "text" | "graphics" | "image";
export type ItemType = "clip" | "audio" | "text" | "image" | "hyperframes" | "transition";

export type TimelineItem = {
  id: string;
  type: ItemType;
  start_ms: number;
  end_ms: number;
  in_ms: number;
  out_ms?: number;
  src_asset_id?: string;
  composition_path?: string;
  text?: string;
  transform?: { x: number; y: number; scale: number; rotation: number; opacity: number };
  effects: Record<string, unknown>[];
  props: Record<string, unknown>;
};

export type TimelineTrack = { id: string; type: TrackType; items: TimelineItem[] };
export type Timeline = {
  schema_version: string;
  fps: number;
  width: number;
  height: number;
  duration_ms: number;
  background: string;
  tracks: TimelineTrack[];
  markers: Record<string, unknown>[];
  captions: { id: string; text: string; start_ms: number; end_ms: number }[];
};
