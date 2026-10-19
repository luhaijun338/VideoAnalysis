from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from video_analysis.adapters.base import EmbedAdapter
from video_analysis.adapters.embed_zhipu import ZhipuEmbedAdapter
from video_analysis.analyze import ensure_queued_job, reset_video_segments
from video_analysis.config import settings
from video_analysis.db import get_session
from video_analysis.models import AnalysisJob, Segment, Video
from video_analysis.probe import ProbeError, probe_video, validate_upload
from video_analysis.search import DEFAULT_MIN_SCORE, search_videos
from video_analysis.storage import LocalStorage

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_FRAME_NAME = re.compile(r"^\d+\.jpg$")
_embedder: ZhipuEmbedAdapter | None = None


def get_storage() -> LocalStorage:
    return LocalStorage(settings.data_dir)


def get_embedder() -> EmbedAdapter:
    global _embedder
    if _embedder is None:
        _embedder = ZhipuEmbedAdapter()
    return _embedder


def enqueue_analyze(video_id: str, mode: str = "resume") -> None:
    from video_analysis.worker import analyze_video_task

    analyze_video_task.delay(video_id, mode)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReanalyzeBody(BaseModel):
    mode: Literal["resume", "full"] = "resume"


class VideoOut(BaseModel):
    id: str
    filename: str
    duration_ms: int
    status: str
    error_message: str | None = None
    total_segments: int | None = None
    done_segments: int = 0
    progress_pct: int = 0


def _public_progress_pct(video: Video) -> int:
    pct = int(video.progress_pct or 0)
    if video.status == "ready":
        return 100
    if video.status == "queued":
        return 0
    if video.status == "processing":
        return max(0, min(99, pct))
    return max(0, min(100, pct))


def _video_out(video: Video) -> dict:
    return VideoOut(
        id=str(video.id),
        filename=video.filename,
        duration_ms=video.duration_ms,
        status=video.status,
        error_message=video.error_message,
        total_segments=video.total_segments,
        done_segments=video.done_segments,
        progress_pct=_public_progress_pct(video),
    ).model_dump()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/videos")
async def upload_video(
    file: Annotated[UploadFile, File()],
    overwrite: bool = Query(default=False),
    session: Session = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> dict:
    filename = file.filename or ""
    try:
        validate_upload(filename, 0)
    except ProbeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
        tmp_path = Path(tmp.name)
        shutil.copyfileobj(file.file, tmp)

    try:
        size = tmp_path.stat().st_size
        try:
            validate_upload(filename, size)
        except ProbeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        digest = sha256_file(tmp_path)
        existing = session.scalar(select(Video).where(Video.content_sha256 == digest))
        if existing is not None and not overwrite:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate",
                    "message": "该录像已上传",
                    "video_id": str(existing.id),
                    "filename": existing.filename,
                },
            )

        video_id = str(existing.id) if existing is not None else str(uuid.uuid4())
        if existing is not None:
            reset_video_segments(session, existing.id)
            storage.delete_video(video_id)

        with tmp_path.open("rb") as fh:
            storage.save_source(video_id, fh)

        source = storage.source_path(video_id)
        try:
            duration_ms = probe_video(source)
        except ProbeError as exc:
            storage.delete_video(video_id)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if existing is not None:
            existing.filename = filename
            existing.duration_ms = duration_ms
            existing.status = "queued"
            existing.error_message = None
            existing.done_segments = 0
            existing.total_segments = None
            existing.progress_pct = 0
            existing.content_sha256 = digest
            ensure_queued_job(session, existing.id, reset_index=True)
            session.commit()
            enqueue_analyze(video_id, mode="full")
            return {"id": video_id, "status": "queued", "overwritten": True}

        video = Video(
            id=UUID(video_id),
            filename=filename,
            duration_ms=duration_ms,
            status="queued",
            content_sha256=digest,
        )
        session.add(video)
        session.flush()
        ensure_queued_job(session, video.id)
        session.commit()
        enqueue_analyze(video_id, mode="resume")
        return {"id": video_id, "status": "queued"}
    finally:
        tmp_path.unlink(missing_ok=True)


@app.get("/api/videos")
def list_videos(session: Session = Depends(get_session)) -> list[dict]:
    videos = session.scalars(select(Video).order_by(Video.created_at.desc())).all()
    return [_video_out(v) for v in videos]


@app.get("/api/videos/{video_id}")
def get_video(video_id: UUID, session: Session = Depends(get_session)) -> dict:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    return _video_out(video)


@app.delete("/api/videos/{video_id}")
def delete_video(
    video_id: UUID,
    session: Session = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> dict:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    session.query(Segment).filter(Segment.video_id == video_id).delete()
    session.query(AnalysisJob).filter(AnalysisJob.video_id == video_id).delete()
    session.delete(video)
    session.commit()
    storage.delete_video(str(video_id))
    return {"id": str(video_id), "deleted": True}


@app.post("/api/videos/{video_id}/reanalyze")
def reanalyze_video(
    video_id: UUID,
    body: ReanalyzeBody | None = None,
    session: Session = Depends(get_session),
) -> dict:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    mode = (body or ReanalyzeBody()).mode
    _, should_enqueue = ensure_queued_job(
        session, video_id, reset_index=(mode == "full")
    )
    if not should_enqueue:
        return {"id": str(video_id), "status": "queued"}
    if mode == "full":
        reset_video_segments(session, video_id)
        video.done_segments = 0
        video.total_segments = None
        video.progress_pct = 0
        video.error_message = None
    video.status = "queued"
    session.commit()
    enqueue_analyze(str(video_id), mode=mode)
    return {"id": str(video_id), "status": "queued"}


@app.get("/api/videos/{video_id}/file")
def get_video_file(
    video_id: UUID,
    session: Session = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> FileResponse:
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    path = storage.source_path(str(video_id))
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type="video/mp4", filename=video.filename)


@app.get("/api/videos/{video_id}/frames/{name}")
def get_frame(
    video_id: UUID,
    name: str,
    session: Session = Depends(get_session),
    storage: LocalStorage = Depends(get_storage),
) -> FileResponse:
    if not _FRAME_NAME.match(name):
        raise HTTPException(status_code=400, detail="invalid frame name")
    video = session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")
    t_start_ms = int(name.removesuffix(".jpg"))
    path = storage.frame_path(str(video_id), t_start_ms)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="frame not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/search")
def search(
    q: Annotated[str, Query()],
    limit_hits: int = Query(default=3, ge=1, le=50),
    offset_hits: int = Query(default=0, ge=0),
    min_score: float = Query(default=DEFAULT_MIN_SCORE, ge=0, le=1),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    session: Session = Depends(get_session),
    embedder: EmbedAdapter = Depends(get_embedder),
) -> dict:
    if not q.strip():
        raise HTTPException(status_code=400, detail="q is required")
    try:
        result = search_videos(
            session,
            embedder,
            q,
            limit_hits=limit_hits,
            offset_hits=offset_hits,
            min_score=min_score,
            created_from=created_from,
            created_to=created_to,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail="search unavailable") from exc
    return asdict(result)


def _mount_spa(application: FastAPI) -> None:
    spa_dir = Path(os.environ.get("SPA_DIR", ""))
    if not spa_dir.is_dir() or not (spa_dir / "index.html").is_file():
        return
    spa_root = spa_dir.resolve()
    assets = spa_root / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="spa-assets")

    @application.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        target = (spa_root / full_path).resolve()
        try:
            target.relative_to(spa_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="not found") from None
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(spa_root / "index.html")


_mount_spa(app)
