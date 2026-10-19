from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from video_analysis.adapters.base import CaptionAdapter, EmbedAdapter, OcrAdapter
from video_analysis.embed_text import operation_embed_text
from video_analysis.fts import tokenize_fts
from video_analysis.models import Segment, Video
from video_analysis.segmenting import SegmentWindow
from video_analysis.storage import LocalStorage

retry_sleep: Callable[[float], None] = time.sleep
RETRY_DELAYS: tuple[float, ...] = (0.5, 1.0, 2.0)
CAPTION_WORKERS = 4


@dataclass
class SegmentPayload:
    ocr_text: str
    caption: str
    caption_degraded: bool
    embedding: list[float] | None
    model_caption: str
    model_embed: str


def pick_representative_frames(frames: list[Path], max_count: int = 1) -> list[Path]:
    """1 frame by default (last of window) to keep VLM caption latency low."""
    if not frames:
        return []
    if len(frames) <= max_count:
        return list(frames)
    last = frames[-1]
    n_earlier = max_count - 1
    earlier = frames[:-1]
    if n_earlier == 1:
        picked = [earlier[len(earlier) // 2]]
    else:
        last_i = len(earlier) - 1
        picked = [earlier[round(i * last_i / (n_earlier - 1))] for i in range(n_earlier)]
    out: list[Path] = []
    seen: set[Path] = set()
    for p in [*picked, last]:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _ocr_text(ocr: OcrAdapter, frames: list[Path]) -> str:
    parts: list[str] = []
    for frame in frames:
        try:
            text = ocr.recognize(frame)
        except Exception:
            continue
        if text:
            parts.append(text)
    return "\n".join(parts)


def _with_retries(
    fn,
    attempts: int = 3,
    delays: Sequence[float] = RETRY_DELAYS,
    sleep_fn: Callable[[float], None] | None = None,
):
    sleeper = sleep_fn or retry_sleep
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if i < attempts - 1:
                delay = delays[i] if i < len(delays) else delays[-1]
                sleeper(delay)
    assert last_exc is not None
    raise last_exc


def _keyframe_path(storage: LocalStorage, window: SegmentWindow) -> str:
    keyframe = window.frame_paths[-1]
    try:
        return str(keyframe.relative_to(storage.root))
    except ValueError:
        return str(keyframe)


def ocr_pseudo_log(ocr_text: str, max_chars: int = 80) -> str:
    compact = " ".join(ocr_text.split())
    if not compact:
        return ""
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1] + "…"


def _as_embedding(value) -> list[float] | None:
    if value is None:
        return None
    return [float(x) for x in value]


def payload_from_segment(segment: Segment) -> SegmentPayload:
    return SegmentPayload(
        ocr_text=segment.ocr_text,
        caption=segment.caption,
        caption_degraded=segment.caption_degraded,
        embedding=_as_embedding(segment.embedding),
        model_caption=segment.model_caption,
        model_embed=segment.model_embed,
    )


def build_segment_payload(
    window: SegmentWindow,
    ocr: OcrAdapter,
    captioner: CaptionAdapter,
    embedder: EmbedAdapter,
) -> SegmentPayload:
    frames = pick_representative_frames(window.frame_paths)
    ocr_text = _ocr_text(ocr, frames)

    caption = ""
    caption_degraded = False
    if getattr(captioner, "skip_caption", False):
        caption_degraded = True
        caption = ocr_pseudo_log(ocr_text)
    else:
        try:
            caption = _with_retries(lambda: captioner.caption(frames, ocr_text))
        except Exception:
            caption_degraded = True
            caption = ocr_pseudo_log(ocr_text)

    embedding: list[float] | None = None
    embed_input = operation_embed_text(caption or ocr_text)
    if embed_input:
        try:
            embedding = _with_retries(lambda: embedder.embed(embed_input))
        except Exception:
            embedding = None

    return SegmentPayload(
        ocr_text=ocr_text,
        caption=caption,
        caption_degraded=caption_degraded,
        embedding=embedding,
        model_caption=getattr(captioner, "model_name", "") or "",
        model_embed=getattr(embedder, "model_name", "") or "",
    )


def index_segment(
    session: Session,
    video: Video,
    window: SegmentWindow,
    ocr: OcrAdapter,
    captioner: CaptionAdapter,
    embedder: EmbedAdapter,
    storage: LocalStorage,
    reuse_from: Segment | None = None,
    payload: SegmentPayload | None = None,
) -> Segment:
    if reuse_from is not None:
        payload = payload_from_segment(reuse_from)
    elif payload is None:
        payload = build_segment_payload(window, ocr, captioner, embedder)

    seg = Segment(
        video_id=video.id,
        t_start_ms=window.t_start_ms,
        t_end_ms=window.t_end_ms,
        keyframe_path=_keyframe_path(storage, window),
        ocr_text=payload.ocr_text,
        caption=payload.caption,
        caption_degraded=payload.caption_degraded,
        embedding=payload.embedding,
        fts=func.to_tsvector("simple", tokenize_fts(payload.caption, payload.ocr_text)),
        model_caption=payload.model_caption,
        model_embed=payload.model_embed,
    )
    session.add(seg)
    session.flush()
    return seg
