import { describe, expect, it } from "vitest";
import { type EditDoc, deleteClip, deleteRange, duration, locate, moveClip, splitAt, trimClip } from "./manual-edit";

function doc(overrides: Partial<EditDoc> = {}): EditDoc {
  return {
    id: "e1", name: "Test", width: 1080, height: 1920, fps: 30,
    clips: [{ id: "c1", asset_id: "a", in_ms: 0, out_ms: 4000, volume: 1 }],
    captions: [
      { id: "l1", text: "first", start_ms: 0, end_ms: 900 },
      { id: "l2", text: "middle", start_ms: 1500, end_ms: 2200 },
      { id: "l3", text: "last", start_ms: 3000, end_ms: 3800 },
    ],
    caption_style: { enabled: true, font: "Inter", size: 5, color: "#FFFFFF", background: "#000000", background_opacity: 0.5, bold: true, y: 0.8, uppercase: false },
    texts: [{ id: "t1", text: "Title", start_ms: 0, end_ms: 4000, x: 0.5, y: 0.2, size: 7, font: "Inter", color: "#FFFFFF", background: null, bold: true }],
    audio: { volume: 1, normalize: false, denoise: false, fade_in_ms: 0, fade_out_ms: 0 },
    created_at: "", updated_at: "",
    ...overrides,
  };
}

describe("manual edit operations", () => {
  it("splits a clip at the playhead without moving anything", () => {
    const edited = splitAt(doc(), 2000);
    expect(edited.clips.map((clip) => [clip.in_ms, clip.out_ms])).toEqual([[0, 2000], [2000, 4000]]);
    expect(edited.captions.map((line) => [line.start_ms, line.end_ms])).toEqual([[0, 900], [1500, 2200], [3000, 3800]]);
  });

  it("deleting a range removes its captions and pulls the rest earlier", () => {
    const edited = deleteRange(doc(), 1000, 2500);
    expect(duration(edited)).toBe(2500);
    expect(edited.captions.map((line) => [line.text, line.start_ms, line.end_ms])).toEqual([["first", 0, 900], ["last", 1500, 2300]]);
    expect(edited.texts[0].end_ms).toBe(2500);
  });

  it("trimming the start shifts captions with the footage", () => {
    const edited = trimClip(doc(), "c1", "in", 1000, 4000);
    expect(edited.captions.map((line) => [line.text, line.start_ms])).toEqual([["middle", 500], ["last", 2000]]);
  });

  it("captions follow clips when they are reordered or deleted", () => {
    const split = splitAt(doc(), 2000);
    const [first, second] = split.clips;
    const swapped = moveClip(split, second.id, -1);
    expect(swapped.captions.map((line) => [line.text, line.start_ms])).toEqual([["last", 1000], ["first", 2000], ["middle", 3500]]);
    const removed = deleteClip(split, first.id);
    expect(removed.captions.map((line) => line.text)).toEqual(["last"]);
  });

  it("maps timeline time to the source frame", () => {
    const edited = trimClip(splitAt(doc(), 2000), "c1", "in", 500, 4000);
    expect(locate(edited.clips, 1600)).toMatchObject({ index: 1, source: 2100 });
  });
});
