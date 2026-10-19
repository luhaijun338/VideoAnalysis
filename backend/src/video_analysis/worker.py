from __future__ import annotations

from uuid import UUID

from celery import Celery

from video_analysis.adapters.base import CaptionAdapter, EmbedAdapter, OcrAdapter
from video_analysis.adapters.caption_zhipu import RaisingCaptionAdapter, ZhipuCaptionAdapter
from video_analysis.adapters.embed_zhipu import ZhipuEmbedAdapter
from video_analysis.adapters.ocr_rapid import RapidOcrAdapter
from video_analysis.analyze import analyze_video, extract_progress_pct, get_current_job, reset_video_segments
from video_analysis.config import settings
from video_analysis.db import SessionLocal
from video_analysis.models import Video
from video_analysis.segmenting import extract_frames, group_segments, keep_only_keyframes
from video_analysis.storage import LocalStorage

celery_app = Celery("video_analysis", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1


def build_adapters() -> tuple[OcrAdapter, CaptionAdapter, EmbedAdapter]:
    ocr: OcrAdapter = RapidOcrAdapter()
    if settings.zhipu_api_key:
        captioner: CaptionAdapter = ZhipuCaptionAdapter()
    else:
        captioner = RaisingCaptionAdapter()
    embedder: EmbedAdapter = ZhipuEmbedAdapter()
    return ocr, captioner, embedder


def _fail_video(session, video_id: UUID, message: str) -> None:
    video = session.get(Video, video_id)
    if video is None:
        return
    video.status = "failed"
    video.error_message = message
    job = get_current_job(session, video.id)
    if job is not None:
        job.status = "failed"
    session.commit()


def _analyze_video_task_body(session, storage: LocalStorage, video_id: str, mode: str) -> str:
    video = session.get(Video, UUID(video_id))
    if video is None:
        return "cancelled"

    if mode == "full":
        reset_video_segments(session, video.id)
        session.commit()

    job = get_current_job(session, video.id)
    video.status = "processing"
    video.total_segments = None
    video.progress_pct = 1
    video.error_message = None
    if job is not None:
        job.status = "processing"
    session.commit()

    source = storage.source_path(video_id)
    frames_dir = source.parent / "frames"
    last_pct = 0

    def on_extract_progress(fraction: float) -> None:
        nonlocal last_pct
        if session.get(Video, video.id) is None:
            return
        pct = extract_progress_pct(fraction)
        if pct == last_pct:
            return
        last_pct = pct
        video.progress_pct = pct
        session.commit()

    try:
        frames = extract_frames(
            source,
            frames_dir,
            duration_ms=video.duration_ms,
            on_progress=on_extract_progress,
        )
    except Exception as exc:
        if session.get(Video, UUID(video_id)) is None:
            return "cancelled"
        _fail_video(session, video.id, f"抽帧失败：{exc}")
        return "failed"

    if session.get(Video, UUID(video_id)) is None:
        return "cancelled"

    windows = keep_only_keyframes(group_segments(frames))

    job = get_current_job(session, video.id)
    start = job.last_segment_index if job else 0

    ocr, captioner, embedder = build_adapters()
    return analyze_video(
        session,
        video.id,
        windows,
        ocr,
        captioner,
        embedder,
        storage,
        start_index=start,
    )


@celery_app.task(bind=True, acks_late=True)
def analyze_video_task(self, video_id: str, mode: str = "resume") -> str:
    storage = LocalStorage(settings.data_dir)
    session = SessionLocal()
    try:
        return _analyze_video_task_body(session, storage, video_id, mode)
    except Exception as exc:
        try:
            session.rollback()
            if session.get(Video, UUID(video_id)) is None:
                return "cancelled"
            _fail_video(session, UUID(video_id), f"分析失败：{exc}")
        except Exception:
            pass
        return "failed"
    finally:
        session.close()
