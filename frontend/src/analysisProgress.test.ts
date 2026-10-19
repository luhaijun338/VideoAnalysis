import { describe, expect, it } from "vitest";
import { analysisPercent } from "./analysisProgress";
import type { Video } from "./api";

function video(partial: Partial<Video>): Video {
  return {
    id: "1",
    filename: "a.mp4",
    duration_ms: 1000,
    status: "queued",
    error_message: null,
    total_segments: null,
    done_segments: 0,
    ...partial,
  };
}

describe("analysisPercent", () => {
  it("shows 0 while queued and 100 when ready", () => {
    expect(analysisPercent(video({ status: "queued", progress_pct: 40 }))).toBe(0);
    expect(analysisPercent(video({ status: "ready", progress_pct: 40 }))).toBe(100);
  });

  it("uses progress_pct during processing and caps below 100", () => {
    expect(analysisPercent(video({ status: "processing", progress_pct: 37 }))).toBe(37);
    expect(analysisPercent(video({ status: "processing", progress_pct: 100 }))).toBe(99);
  });

  it("falls back to segment counts when progress_pct is missing", () => {
    expect(
      analysisPercent(
        video({ status: "processing", total_segments: 4, done_segments: 1, progress_pct: undefined }),
      ),
    ).toBe(25);
  });
});
