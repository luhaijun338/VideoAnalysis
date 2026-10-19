from pathlib import Path
from uuid import uuid4

from PIL import Image

from video_analysis.adapters.fake import FakeCaptionAdapter, FakeEmbedAdapter, FakeOcrAdapter
from video_analysis.analyze import analysis_progress_pct, analyze_video, extract_progress_pct
from video_analysis.models import AnalysisJob, Segment, Video
from video_analysis.segmenting import SegmentWindow
from video_analysis.storage import LocalStorage


def test_extract_progress_pct_maps_fraction() -> None:
    assert extract_progress_pct(0) == 1
    assert extract_progress_pct(1) == 20
    assert 1 < extract_progress_pct(0.5) < 20


def test_analysis_progress_pct_stays_below_100_until_ready() -> None:
    assert analysis_progress_pct(0, 4) == 20
    assert analysis_progress_pct(2, 4) == 59
    assert analysis_progress_pct(4, 4) == 99
    mid = analysis_progress_pct(0, 4, captioning=2)
    assert 20 < mid < 59


def _windows(tmp_path: Path, n: int) -> list[SegmentWindow]:
    frame = tmp_path / "0.jpg"
    Image.new("RGB", (16, 16), (1, 2, 3)).save(frame, "JPEG")
    return [
        SegmentWindow(i * 4000, i * 4000 + 4000, i * 4000, [frame])
        for i in range(n)
    ]


def test_analyze_resumes_from_start_index(db_session, tmp_path: Path) -> None:
    video = Video(id=uuid4(), filename="a.mp4", duration_ms=16000, status="queued")
    db_session.add(video)
    db_session.commit()
    status = analyze_video(
        db_session,
        video.id,
        _windows(tmp_path, 4),
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
        start_index=2,
    )
    assert status == "ready"
    rows = db_session.query(Segment).filter(Segment.video_id == video.id).all()
    assert len(rows) == 2
    db_session.refresh(video)
    assert video.progress_pct == 100


class FailingEmbed:
    def embed(self, text: str) -> list[float]:
        raise RuntimeError("embed down")


def test_analyze_fails_when_too_many_missing_embeddings(db_session, tmp_path: Path) -> None:
    video = Video(id=uuid4(), filename="a.mp4", duration_ms=16000, status="queued")
    db_session.add(video)
    db_session.commit()
    status = analyze_video(
        db_session,
        video.id,
        _windows(tmp_path, 4),
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FailingEmbed(),
        LocalStorage(tmp_path),
        start_index=0,
    )
    assert status == "failed"


def test_analyze_reuses_existing_job_instead_of_creating(db_session, tmp_path: Path) -> None:
    video = Video(id=uuid4(), filename="a.mp4", duration_ms=8000, status="failed")
    job = AnalysisJob(video_id=video.id, status="failed", last_segment_index=0)
    db_session.add_all([video, job])
    db_session.commit()
    job_id = job.id
    status = analyze_video(
        db_session,
        video.id,
        _windows(tmp_path, 2),
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
        start_index=0,
    )
    assert status == "ready"
    jobs = db_session.query(AnalysisJob).filter(AnalysisJob.video_id == video.id).all()
    assert len(jobs) == 1
    assert jobs[0].id == job_id


def test_analyze_retries_segments_with_null_embedding(db_session, tmp_path: Path) -> None:
    video = Video(
        id=uuid4(),
        filename="a.mp4",
        duration_ms=8000,
        status="failed",
        total_segments=2,
        done_segments=2,
    )
    job = AnalysisJob(video_id=video.id, status="failed", last_segment_index=2)
    db_session.add_all([video, job])
    db_session.flush()
    for i in range(2):
        db_session.add(
            Segment(
                video_id=video.id,
                t_start_ms=i * 4000,
                t_end_ms=i * 4000 + 4000,
                keyframe_path=f"frames/{i}.jpg",
                caption="",
                ocr_text="界面",
                embedding=None,
            )
        )
    db_session.commit()

    status = analyze_video(
        db_session,
        video.id,
        _windows(tmp_path, 2),
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
        start_index=2,
    )
    assert status == "ready"
    rows = db_session.query(Segment).filter(Segment.video_id == video.id).all()
    assert len(rows) == 2
    assert all(s.embedding is not None for s in rows)


def test_analyze_skips_caption_when_consecutive_frames_match(db_session, tmp_path: Path) -> None:
    frame = tmp_path / "still.jpg"
    Image.new("RGB", (16, 16), (8, 8, 8)).save(frame, "JPEG")
    video = Video(id=uuid4(), filename="still.mp4", duration_ms=12000, status="queued")
    db_session.add(video)
    db_session.commit()

    class RecCaption:
        model_name = "rec"

        def __init__(self) -> None:
            self.n = 0

        def caption(self, frames: list[Path], ocr_text: str) -> str:
            self.n += 1
            return "画面静止"

    windows = [
        SegmentWindow(0, 4000, 0, [frame]),
        SegmentWindow(4000, 8000, 4000, [frame]),
        SegmentWindow(8000, 12000, 8000, [frame]),
    ]
    captioner = RecCaption()
    status = analyze_video(
        db_session,
        video.id,
        windows,
        FakeOcrAdapter(),
        captioner,
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    assert status == "ready"
    assert captioner.n == 1
    rows = db_session.query(Segment).filter(Segment.video_id == video.id).order_by(Segment.t_start_ms).all()
    assert len(rows) == 3
    assert {s.caption for s in rows} == {"画面静止"}


def test_analyze_stops_when_video_deleted(db_session, tmp_path: Path, monkeypatch) -> None:
    frame_a = tmp_path / "a.jpg"
    frame_b = tmp_path / "b.jpg"
    Image.new("RGB", (16, 16), (8, 8, 8)).save(frame_a, "JPEG")
    Image.new("RGB", (16, 16), (200, 10, 10)).save(frame_b, "JPEG")
    video = Video(id=uuid4(), filename="stop.mp4", duration_ms=8000, status="queued")
    db_session.add(video)
    db_session.commit()
    video_id = video.id

    import video_analysis.analyze as analyze_mod

    original = analyze_mod.index_segment
    calls = {"n": 0}

    def wrapping(*args, **kwargs):
        calls["n"] += 1
        seg = original(*args, **kwargs)
        if calls["n"] == 1:
            db_session.query(Segment).filter(Segment.video_id == video_id).delete()
            db_session.query(AnalysisJob).filter(AnalysisJob.video_id == video_id).delete()
            db_session.delete(db_session.get(Video, video_id))
            db_session.commit()
        return seg

    monkeypatch.setattr(analyze_mod, "index_segment", wrapping)
    windows = [
        SegmentWindow(0, 4000, 0, [frame_a]),
        SegmentWindow(4000, 8000, 4000, [frame_b]),
    ]
    status = analyze_video(
        db_session,
        video_id,
        windows,
        FakeOcrAdapter(),
        FakeCaptionAdapter(),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    assert status == "cancelled"
    assert db_session.get(Video, video_id) is None
    assert calls["n"] == 1
