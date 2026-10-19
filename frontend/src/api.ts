export type VideoStatus = "queued" | "processing" | "ready" | "failed";

export interface Video {
  id: string;
  filename: string;
  duration_ms: number;
  status: VideoStatus | string;
  error_message: string | null;
  total_segments: number | null;
  done_segments: number;
  progress_pct?: number;
}

export interface Hit {
  segment_id: string;
  video_id?: string;
  t_start_ms: number;
  t_end_ms: number;
  caption: string;
  ocr_text: string;
  keyframe_url: string;
  score: number;
  caption_degraded: boolean;
}

export interface VideoGroup {
  video_id: string;
  filename: string;
  duration_ms: number;
  best_score: number;
  hits: Hit[];
}

export interface SearchResult {
  query: string;
  total_hits: number;
  limit_hits: number;
  offset_hits: number;
  total_videos: number;
  videos: VideoGroup[];
  min_score?: number;
}

export type SearchQuery = {
  q: string;
  limit?: number;
  offset?: number;
  minScore?: number;
  createdFrom?: string;
  createdTo?: string;
};

export class DuplicateUploadError extends Error {
  video_id: string;
  filename: string;

  constructor(detail: { message: string; video_id: string; filename?: string }) {
    super(detail.message);
    this.name = "DuplicateUploadError";
    this.video_id = detail.video_id;
    this.filename = detail.filename ?? "";
  }
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export class UploadAbortedError extends Error {
  constructor() {
    super("upload aborted");
    this.name = "UploadAbortedError";
  }
}

export async function uploadVideo(
  file: File,
  overwrite = false,
  signal?: AbortSignal,
): Promise<{ id: string; status: string; overwritten?: boolean }> {
  const form = new FormData();
  form.append("file", file);
  const url = overwrite ? "/api/videos?overwrite=true" : "/api/videos";
  let res: Response;
  try {
    res = await fetch(url, { method: "POST", body: form, signal });
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) {
      throw new UploadAbortedError();
    }
    throw err;
  }
  if (res.status === 409) {
    const body = (await res.json()) as {
      detail?: { message?: string; video_id?: string; filename?: string };
    };
    const detail = body.detail;
    throw new DuplicateUploadError({
      message: detail?.message || "该录像已上传",
      video_id: detail?.video_id || "",
      filename: detail?.filename,
    });
  }
  return parseJson(res);
}

export async function listVideos(): Promise<Video[]> {
  const res = await fetch("/api/videos");
  return parseJson(res);
}

export async function getVideo(id: string): Promise<Video> {
  const res = await fetch(`/api/videos/${id}`);
  return parseJson(res);
}

export async function reanalyze(
  id: string,
  mode: "resume" | "full" = "resume",
): Promise<{ id: string; status: string }> {
  const res = await fetch(`/api/videos/${id}/reanalyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  return parseJson(res);
}

export async function searchVideos(params: SearchQuery): Promise<SearchResult> {
  const qs = new URLSearchParams({
    q: params.q,
    limit_hits: String(params.limit ?? 3),
    offset_hits: String(params.offset ?? 0),
  });
  if (params.minScore != null) qs.set("min_score", String(params.minScore));
  if (params.createdFrom) qs.set("created_from", params.createdFrom);
  if (params.createdTo) qs.set("created_to", params.createdTo);
  const res = await fetch(`/api/search?${qs}`);
  return parseJson(res);
}

export async function deleteVideo(id: string): Promise<{ id: string; deleted: boolean }> {
  const res = await fetch(`/api/videos/${id}`, { method: "DELETE" });
  return parseJson(res);
}
