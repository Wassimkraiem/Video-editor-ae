import { describe, expect, it } from "vitest";
import { transcriptLines } from "./TranscriptEditor";

const word = (id: number, start: number, end: number, segment = 0) => ({ id: `w${id}`, text: `word${id}`, start_ms: start, end_ms: end, segment });

describe("transcriptLines", () => {
  it("breaks long Whisper segments into short lines at pauses and length", () => {
    // One 30-word segment with no pauses: the old view showed it as one line.
    const words = Array.from({ length: 30 }, (_, index) => word(index, index * 300, index * 300 + 280));
    const lines = transcriptLines(words);
    expect(lines.every((line) => line.length <= 9)).toBe(true);
    expect(lines.flat()).toHaveLength(30);
  });

  it("starts a new line after a pause", () => {
    const lines = transcriptLines([word(0, 0, 300), word(1, 300, 600), word(2, 1200, 1500)]);
    expect(lines.map((line) => line.length)).toEqual([2, 1]);
  });
});
