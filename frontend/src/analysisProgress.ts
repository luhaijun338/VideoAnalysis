import type { Video } from "./api";

export function analysisPercent(video: Video): number {
  if (video.status === "ready") return 100;
  if (video.status === "queued") return 0;
  const pct = video.progress_pct;
  if (typeof pct === "number" && Number.isFinite(pct)) {
    const cap = video.status === "processing" ? 99 : 100;
    return Math.max(0, Math.min(cap, Math.round(pct)));
  }
  if (video.total_segments) {
    return Math.min(99, Math.round((video.done_segments / video.total_segments) * 100));
  }
  return 0;
}
