from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image

from video_analysis.adapters.fake import FakeCaptionAdapter, FakeEmbedAdapter, FakeOcrAdapter
from video_analysis.models import AnalysisJob, Segment, Video
from video_analysis.segmenting import SegmentWindow
from video_analysis.worker import analyze_video_task, celery_app, build_adapters


celery_app.conf.task_always_eager = True


class _SessionProxy:
    """Reuse pytest session; ignore close so assertions still work."""

    def __init__(self, session) -> None:
        self._session = session

    def __getattr__(self, name: str):
        return getattr(self._session, name)

    def close(self) -> None:
        pass


def _make_jpeg(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (10, 20, 30)).save(path, "JPEG")
    return path


def _patch_session(monkeypatch, db_session) -> None:
    monkeypatch.setattr(
        "video_analysis.worker.SessionLocal",
        lambda: _SessionProxy(db_session),
    )


def test_analyze_video_task_marks_ready(db_session, tmp_path: Path, monkeypatch) -> None:
    video_id = uuid4()
    storage_root = tmp_path / "data"
    video_dir = storage_root / str(video_id)
    video_dir.mkdir(parents=True)
    (video_dir / "source.mp4").write_bytes(b"fake-mp4")
    frame0 = _make_jpeg(video_dir / "frames" / "0.jpg")
    frame1 = _make_jpeg(video_dir / "frames" / "4000.jpg")

    video = Video(id=video_id, filename="a.mp4", duration_ms=8000, status="queued")
    db_session.add(video)
    db_session.commit()

    windows = [
        SegmentWindow(0, 4000, 0, [frame0]),
        SegmentWindow(4000, 8000, 4000, [frame1]),
    ]

    monkeypatch.setattr("video_analysis.worker.settings.data_dir", storage_root)
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        "video_analysis.worker.extract_frames",
        lambda source, dest_dir, interval_s=2.0, **kwargs: [frame0, frame1],
    )
    monkeypatch.setattr(
        "video_analysis.worker.group_segments",
        lambda frames, **kwargs: windows,
    )
    monkeypatch.setattr(
        "video_analysis.worker.build_adapters",
        lambda: (FakeOcrAdapter({"0.jpg": "确定"}), FakeCaptionAdapter(), FakeEmbedAdapter()),
    )

    result = analyze_video_task.delay(str(video_id), "resume").get()
    assert result == "ready"

    db_session.refresh(video)
    assert video.status == "ready"
    assert video.progress_pct == 100
    segs = db_session.query(Segment).filter(Segment.video_id == video_id).all()
    assert len(segs) == 2


def test_extract_frames_failure_marks_failed(db_session, tmp_path: Path, monkeypatch) -> None:
    video_id = uuid4()
    storage_root = tmp_path / "data"
    video_dir = storage_root / str(video_id)
    video_dir.mkdir(parents=True)
    source = video_dir / "source.mp4"
    source.write_bytes(b"fake-mp4")

    video = Video(id=video_id, filename="a.mp4", duration_ms=8000, status="queued")
    job = AnalysisJob(video_id=video_id, status="queued")
    db_session.add_all([video, job])
    db_session.commit()

    monkeypatch.setattr("video_analysis.worker.settings.data_dir", storage_root)
    _patch_session(monkeypatch, db_session)

    def boom(source, dest_dir, interval_s=2.0, **kwargs):
        raise RuntimeError("ffmpeg exploded")

    monkeypatch.setattr("video_analysis.worker.extract_frames", boom)

    result = analyze_video_task.delay(str(video_id), "resume").get()
    assert result == "failed"

    db_session.refresh(video)
    db_session.refresh(job)
    assert video.status == "failed"
    assert video.error_message
    assert job.status == "failed"
    assert source.exists()


def test_resume_skips_completed_windows(db_session, tmp_path: Path, monkeypatch) -> None:
    video_id = uuid4()
    storage_root = tmp_path / "data"
    video_dir = storage_root / str(video_id)
    video_dir.mkdir(parents=True)
    (video_dir / "source.mp4").write_bytes(b"fake-mp4")
    frame0 = _make_jpeg(video_dir / "frames" / "0.jpg")
    frame1 = _make_jpeg(video_dir / "frames" / "4000.jpg")

    video = Video(
        id=video_id,
        filename="a.mp4",
        duration_ms=8000,
        status="processing",
        total_segments=2,
        done_segments=1,
    )
    job = AnalysisJob(
        video_id=video_id,
        status="processing",
        last_segment_index=1,
    )
    existing = Segment(
        video_id=video_id,
        t_start_ms=0,
        t_end_ms=4000,
        keyframe_path=f"{video_id}/frames/0.jpg",
        ocr_text="已有",
        caption="已有段",
        embedding=[0.0] * 1024,
    )
    db_session.add_all([video, job, existing])
    db_session.commit()

    windows = [
        SegmentWindow(0, 4000, 0, [frame0]),
        SegmentWindow(4000, 8000, 4000, [frame1]),
    ]

    monkeypatch.setattr("video_analysis.worker.settings.data_dir", storage_root)
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        "video_analysis.worker.extract_frames",
        lambda source, dest_dir, interval_s=2.0, **kwargs: [frame0, frame1],
    )
    monkeypatch.setattr(
        "video_analysis.worker.group_segments",
        lambda frames, **kwargs: windows,
    )
    monkeypatch.setattr(
        "video_analysis.worker.build_adapters",
        lambda: (FakeOcrAdapter({"4000.jpg": "下一步"}), FakeCaptionAdapter(), FakeEmbedAdapter()),
    )

    result = analyze_video_task.delay(str(video_id), "resume").get()
    assert result == "ready"

    segs = db_session.query(Segment).filter(Segment.video_id == video_id).all()
    assert len(segs) == 2


def test_worker_sets_processing_before_extract(db_session, tmp_path: Path, monkeypatch) -> None:
    video_id = uuid4()
    storage_root = tmp_path / "data"
    video_dir = storage_root / str(video_id)
    video_dir.mkdir(parents=True)
    (video_dir / "source.mp4").write_bytes(b"fake-mp4")
    frame0 = _make_jpeg(video_dir / "frames" / "0.jpg")

    video = Video(id=video_id, filename="a.mp4", duration_ms=4000, status="queued")
    db_session.add(video)
    db_session.commit()

    seen: dict = {}

    def extract_and_record(source, dest_dir, interval_s=2.0, **kwargs):
        db_session.refresh(video)
        seen["status"] = video.status
        seen["total_segments"] = video.total_segments
        seen["progress_pct"] = video.progress_pct
        return [frame0]

    monkeypatch.setattr("video_analysis.worker.settings.data_dir", storage_root)
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr("video_analysis.worker.extract_frames", extract_and_record)
    monkeypatch.setattr(
        "video_analysis.worker.group_segments",
        lambda frames, **kwargs: [SegmentWindow(0, 4000, 0, [frame0])],
    )
    monkeypatch.setattr(
        "video_analysis.worker.build_adapters",
        lambda: (FakeOcrAdapter(), FakeCaptionAdapter(), FakeEmbedAdapter()),
    )

    analyze_video_task.delay(str(video_id), "resume").get()
    assert seen["status"] == "processing"
    assert seen["total_segments"] is None
    assert seen["progress_pct"] == 1


def test_unexpected_exception_marks_failed(db_session, tmp_path: Path, monkeypatch) -> None:
    video_id = uuid4()
    storage_root = tmp_path / "data"
    video_dir = storage_root / str(video_id)
    video_dir.mkdir(parents=True)
    (video_dir / "source.mp4").write_bytes(b"fake-mp4")
    frame0 = _make_jpeg(video_dir / "frames" / "0.jpg")

    video = Video(id=video_id, filename="a.mp4", duration_ms=4000, status="queued")
    job = AnalysisJob(video_id=video_id, status="queued")
    db_session.add_all([video, job])
    db_session.commit()

    monkeypatch.setattr("video_analysis.worker.settings.data_dir", storage_root)
    _patch_session(monkeypatch, db_session)
    monkeypatch.setattr(
        "video_analysis.worker.extract_frames",
        lambda source, dest_dir, interval_s=2.0, **kwargs: [frame0],
    )

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr("video_analysis.worker.group_segments", boom)

    result = analyze_video_task.delay(str(video_id), "resume").get()
    assert result == "failed"
    db_session.refresh(video)
    db_session.refresh(job)
    assert video.status == "failed"
    assert "分析失败" in (video.error_message or "")
    assert job.status == "failed"


def test_celery_acks_late_and_prefetch() -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_build_adapters_without_key_raises_on_caption(monkeypatch) -> None:
    monkeypatch.setattr("video_analysis.worker.settings.zhipu_api_key", "")
    ocr, captioner, embedder = build_adapters()
    assert ocr is not None
    assert embedder is not None
    try:
        captioner.caption([], "")
        raised = False
    except Exception:
        raised = True
    assert raised
