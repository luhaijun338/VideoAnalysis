from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from video_analysis.adapters.base import CaptionAdapter, EmbedAdapter, OcrAdapter
from video_analysis.indexing import CAPTION_WORKERS, build_segment_payload, index_segment
from video_analysis.models import AnalysisJob, Segment, Video
from video_analysis.segmenting import SegmentWindow, frames_visually_same
from video_analysis.storage import LocalStorage

ACTIVE_JOB_STATUSES = ("queued", "processing")
EXTRACT_PROGRESS_MAX = 20
ANALYSIS_PROGRESS_MAX = 99


def extract_progress_pct(fraction: float) -> int:
    frac = max(0.0, min(1.0, fraction))
    return max(1, min(EXTRACT_PROGRESS_MAX, round(1 + frac * (EXTRACT_PROGRESS_MAX - 1))))


def analysis_progress_pct(done: int, total: int, *, captioning: float = 0.0) -> int:
    if total <= 0:
        return EXTRACT_PROGRESS_MAX
    units = min(float(total), max(0.0, done + 0.6 * captioning))
    return EXTRACT_PROGRESS_MAX + int((ANALYSIS_PROGRESS_MAX - EXTRACT_PROGRESS_MAX) * units / total)


def get_current_job(session: Session, video_id: UUID) -> AnalysisJob | None:
    """Shared lookup: the unique active job, else the latest job for this video."""
    active = session.scalar(
        select(AnalysisJob)
        .where(
            AnalysisJob.video_id == video_id,
            AnalysisJob.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(AnalysisJob.created_at.desc())
    )
    if active is not None:
        return active
    return session.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.video_id == video_id)
        .order_by(AnalysisJob.created_at.desc())
    )


def ensure_queued_job(
    session: Session,
    video_id: UUID,
    *,
    reset_index: bool = False,
) -> tuple[AnalysisJob, bool]:
    """Reuse the current job or create one. Returns (job, newly_enqueued).

    newly_enqueued is False when a queued/processing job already exists, so
    callers must not insert a second active row or fire a duplicate Celery task.
    """
    job = get_current_job(session, video_id)
    if job is not None and job.status in ACTIVE_JOB_STATUSES:
        return job, False
    if job is None:
        job = AnalysisJob(video_id=video_id, status="queued")
        session.add(job)
        session.flush()
        return job, True
    job.status = "queued"
    job.attempt = (job.attempt or 0) + 1
    if reset_index:
        job.last_segment_index = 0
    return job, True


def reset_video_segments(session: Session, video_id: UUID) -> None:
    session.query(Segment).filter(Segment.video_id == video_id).delete()
    job = get_current_job(session, video_id)
    if job:
        job.last_segment_index = 0


def _get_or_create_job(session: Session, video_id: UUID) -> AnalysisJob:
    job = get_current_job(session, video_id)
    if job is None:
        job = AnalysisJob(video_id=video_id, status="processing")
        session.add(job)
        session.flush()
    else:
        job.status = "processing"
    return job


def _existing_segment(
    session: Session, video_id: UUID, window: SegmentWindow
) -> Segment | None:
    return session.scalar(
        select(Segment).where(
            Segment.video_id == video_id,
            Segment.t_start_ms == window.t_start_ms,
        )
    )


def analysis_cancelled(session: Session, video_id: UUID) -> bool:
    session.expire_all()
    return session.get(Video, video_id) is None


def analyze_video(
    session: Session,
    video_id: UUID,
    windows: list[SegmentWindow],
    ocr: OcrAdapter,
    captioner: CaptionAdapter,
    embedder: EmbedAdapter,
    storage: LocalStorage,
    start_index: int = 0,
) -> str:
    video = session.get(Video, video_id)
    if video is None:
        raise ValueError(f"video not found: {video_id}")

    job = _get_or_create_job(session, video_id)
    video.status = "processing"
    video.total_segments = len(windows)
    if start_index > video.done_segments:
        video.done_segments = start_index
    if start_index > job.last_segment_index:
        job.last_segment_index = start_index
    video.progress_pct = analysis_progress_pct(video.done_segments, len(windows))
    session.commit()

    pending: list[tuple[int, SegmentWindow, bool]] = []
    prev_keyframe = None
    prev_seg: Segment | None = None
    for i, window in enumerate(windows):
        existing = _existing_segment(session, video_id, window)
        skip = i < start_index and (existing is None or existing.embedding is not None)
        keyframe = window.frame_paths[-1]
        if skip:
            prev_keyframe = keyframe
            if existing is not None:
                prev_seg = existing
            continue
        reuse = prev_keyframe is not None and frames_visually_same(keyframe, prev_keyframe)
        pending.append((i, window, reuse))
        prev_keyframe = keyframe

    total = len(windows)

    def _run(window: SegmentWindow):
        return window.t_start_ms, build_segment_payload(window, ocr, captioner, embedder)

    def _index_window(window: SegmentWindow, *, reuse: bool, payload=None) -> Segment:
        existing = _existing_segment(session, video_id, window)
        if existing is not None:
            session.delete(existing)
            session.flush()
        if reuse and prev_seg is not None:
            return index_segment(
                session, video, window, ocr, captioner, embedder, storage, reuse_from=prev_seg
            )
        return index_segment(
            session,
            video,
            window,
            ocr,
            captioner,
            embedder,
            storage,
            payload=payload,
        )

    def _commit_done(i: int) -> None:
        job.last_segment_index = i + 1
        video.done_segments = i + 1
        video.progress_pct = analysis_progress_pct(i + 1, total)
        session.commit()

    pos = 0
    while pos < len(pending):
        if analysis_cancelled(session, video_id):
            return "cancelled"
        i, window, reuse = pending[pos]
        if reuse:
            prev_seg = _index_window(window, reuse=True)
            if analysis_cancelled(session, video_id):
                return "cancelled"
            _commit_done(i)
            pos += 1
            continue

        batch: list[tuple[int, SegmentWindow]] = []
        while pos < len(pending) and not pending[pos][2] and len(batch) < CAPTION_WORKERS:
            batch.append((pending[pos][0], pending[pos][1]))
            pos += 1

        if analysis_cancelled(session, video_id):
            return "cancelled"
        workers = min(CAPTION_WORKERS, len(batch))
        payloads: dict[int, object] = {}
        captioned = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run, win): win for _, win in batch}
            for fut in as_completed(futures):
                t_start, payload = fut.result()
                payloads[t_start] = payload
                captioned += 1
                if analysis_cancelled(session, video_id):
                    return "cancelled"
                video.progress_pct = analysis_progress_pct(
                    video.done_segments, total, captioning=captioned
                )
                session.commit()

        for i, window in batch:
            if analysis_cancelled(session, video_id):
                return "cancelled"
            prev_seg = _index_window(window, reuse=False, payload=payloads.get(window.t_start_ms))
            if analysis_cancelled(session, video_id):
                return "cancelled"
            _commit_done(i)

    if analysis_cancelled(session, video_id):
        return "cancelled"

    segs = session.query(Segment).filter(Segment.video_id == video_id).all()
    missing_count = sum(1 for s in segs if s.embedding is None)
    status = "failed" if total > 0 and (missing_count / total) > 0.30 else "ready"
    video.status = status
    job.status = status
    video.progress_pct = 100 if status == "ready" else video.progress_pct
    if status == "ready":
        video.error_message = None
    session.commit()
    return status
