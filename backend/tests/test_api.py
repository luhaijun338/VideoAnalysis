from __future__ import annotations

from sqlalchemy import func

from video_analysis.adapters.fake import FakeEmbedAdapter
from video_analysis.embed_text import operation_embed_text
from video_analysis.fts import tokenize_fts
from video_analysis.models import Segment, Video


def test_health(client) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_upload_rejects_txt(client) -> None:
    resp = client.post(
        "/api/videos",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_queues_and_enqueues(client, monkeypatch) -> None:
    calls: list[tuple] = []

    def capture(video_id: str, mode: str = "resume") -> None:
        calls.append((video_id, mode))

    monkeypatch.setattr("video_analysis.api.enqueue_analyze", capture)
    monkeypatch.setattr("video_analysis.api.probe_video", lambda path: 12500)

    resp = client.post(
        "/api/videos",
        files={"file": ("demo.mp4", b"fake-mp4-bytes", "video/mp4")},
    )
    assert resp.status_code in (200, 201)
    body = resp.json()
    assert body["status"] == "queued"
    assert "id" in body
    assert len(calls) == 1
    assert calls[0] == (body["id"], "resume")


def test_upload_duplicate_returns_409(client, monkeypatch) -> None:
    monkeypatch.setattr("video_analysis.api.enqueue_analyze", lambda *a, **k: None)
    monkeypatch.setattr("video_analysis.api.probe_video", lambda path: 12500)
    payload = {"file": ("dup.mp4", b"same-video-bytes", "video/mp4")}
    first = client.post("/api/videos", files=payload)
    assert first.status_code in (200, 201)
    second = client.post(
        "/api/videos",
        files={"file": ("dup.mp4", b"same-video-bytes", "video/mp4")},
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "duplicate"
    assert detail["video_id"] == first.json()["id"]
    assert "已上传" in detail["message"]


def test_upload_duplicate_overwrite_reuses_id(client, monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        "video_analysis.api.enqueue_analyze",
        lambda video_id, mode="resume": calls.append((video_id, mode)),
    )
    monkeypatch.setattr("video_analysis.api.probe_video", lambda path: 12500)
    first = client.post(
        "/api/videos",
        files={"file": ("ow.mp4", b"overwrite-video-bytes", "video/mp4")},
    )
    assert first.status_code in (200, 201)
    video_id = first.json()["id"]
    second = client.post(
        "/api/videos",
        params={"overwrite": True},
        files={"file": ("ow.mp4", b"overwrite-video-bytes", "video/mp4")},
    )
    assert second.status_code in (200, 201)
    body = second.json()
    assert body["id"] == video_id
    assert body["overwritten"] is True
    assert calls[-1] == (video_id, "full")


def test_list_videos_includes_uploaded(client, monkeypatch) -> None:
    monkeypatch.setattr("video_analysis.api.enqueue_analyze", lambda *a, **k: None)
    monkeypatch.setattr("video_analysis.api.probe_video", lambda path: 12500)

    client.post(
        "/api/videos",
        files={"file": ("listed.mp4", b"listed-mp4-bytes", "video/mp4")},
    )
    resp = client.get("/api/videos")
    assert resp.status_code == 200
    filenames = [v["filename"] for v in resp.json()]
    assert "listed.mp4" in filenames
    listed = next(v for v in resp.json() if v["filename"] == "listed.mp4")
    assert listed["progress_pct"] == 0
    assert listed["status"] == "queued"


def test_search_returns_videos_array(client, db_session) -> None:
    embedder = FakeEmbedAdapter()
    query = "客户名单"
    video = Video(filename="search.mp4", duration_ms=60_000, status="ready")
    db_session.add(video)
    db_session.flush()
    seg = Segment(
        video_id=video.id,
        t_start_ms=1000,
        t_end_ms=5000,
        keyframe_path="frames/1000.jpg",
        caption=query,
        ocr_text="导出 客户名单",
            embedding=embedder.embed(operation_embed_text(query)),
        fts=func.to_tsvector("simple", tokenize_fts(query, "导出 客户名单")),
    )
    db_session.add(seg)
    db_session.commit()

    resp = client.get("/api/search", params={"q": query})
    assert resp.status_code == 200
    body = resp.json()
    assert "videos" in body
    assert isinstance(body["videos"], list)
    assert body["limit_hits"] == 3
    assert len(body["videos"]) >= 1
    group = body["videos"][0]
    assert "best_score" in group
    hit = group["hits"][0]
    assert "t_start_ms" in hit
    assert "keyframe_url" in hit


def test_video_file_missing_returns_404(client, db_session) -> None:
    video = Video(filename="missing.mp4", duration_ms=1000, status="queued")
    db_session.add(video)
    db_session.commit()

    resp = client.get(f"/api/videos/{video.id}/file")
    assert resp.status_code == 404


def test_search_db_failure_returns_503(client, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("video_analysis.api.search_videos", boom)
    resp = client.get("/api/search", params={"q": "客户名单"})
    assert resp.status_code == 503
    assert resp.json() == {"detail": "search unavailable"}


def test_search_empty_q_returns_400(client) -> None:
    resp = client.get("/api/search", params={"q": ""})
    assert resp.status_code == 400


def test_search_time_filter_excludes_old_videos(client, db_session) -> None:
    embedder = FakeEmbedAdapter()
    query = "客户名单"
    video = Video(filename="search.mp4", duration_ms=60_000, status="ready")
    db_session.add(video)
    db_session.flush()
    db_session.add(
        Segment(
            video_id=video.id,
            t_start_ms=1000,
            t_end_ms=5000,
            keyframe_path="frames/1000.jpg",
            caption=query,
            ocr_text=query,
            embedding=embedder.embed(operation_embed_text(query)),
            fts=func.to_tsvector("simple", tokenize_fts(query, query)),
        )
    )
    db_session.commit()

    resp = client.get(
        "/api/search",
        params={"q": query, "min_score": 0, "created_from": "2099-01-01T00:00:00Z"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_hits"] == 0
    assert body["min_score"] == 0.0


def test_reanalyze_full_calls_reset(client, db_session, monkeypatch) -> None:
    video = Video(filename="re.mp4", duration_ms=1000, status="ready", total_segments=1, done_segments=1)
    db_session.add(video)
    db_session.flush()
    db_session.add(
        Segment(
            video_id=video.id,
            t_start_ms=0,
            t_end_ms=1000,
            keyframe_path="frames/0.jpg",
            caption="x",
            ocr_text="",
        )
    )
    db_session.commit()

    reset_calls: list = []
    monkeypatch.setattr(
        "video_analysis.api.reset_video_segments",
        lambda session, video_id: reset_calls.append(video_id),
    )
    monkeypatch.setattr("video_analysis.api.enqueue_analyze", lambda *a, **k: None)

    resp = client.post(f"/api/videos/{video.id}/reanalyze", json={"mode": "full"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert reset_calls == [video.id]


def test_reanalyze_failed_reuses_job(client, db_session, monkeypatch) -> None:
    from video_analysis.models import AnalysisJob

    video = Video(filename="fail.mp4", duration_ms=1000, status="failed")
    db_session.add(video)
    db_session.flush()
    job = AnalysisJob(video_id=video.id, status="failed", last_segment_index=4)
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    calls: list[tuple] = []
    monkeypatch.setattr(
        "video_analysis.api.enqueue_analyze",
        lambda video_id, mode="resume": calls.append((video_id, mode)),
    )

    resp = client.post(f"/api/videos/{video.id}/reanalyze", json={"mode": "resume"})
    assert resp.status_code == 200
    jobs = db_session.query(AnalysisJob).filter(AnalysisJob.video_id == video.id).all()
    assert len(jobs) == 1
    assert jobs[0].id == job_id
    assert jobs[0].status == "queued"
    assert calls == [(str(video.id), "resume")]


def test_reanalyze_while_queued_does_not_create_second_job(client, db_session, monkeypatch) -> None:
    from video_analysis.models import AnalysisJob

    video = Video(filename="q.mp4", duration_ms=1000, status="queued")
    db_session.add(video)
    db_session.flush()
    db_session.add(AnalysisJob(video_id=video.id, status="queued"))
    db_session.commit()

    calls: list = []
    monkeypatch.setattr(
        "video_analysis.api.enqueue_analyze",
        lambda *a, **k: calls.append((a, k)),
    )

    resp = client.post(f"/api/videos/{video.id}/reanalyze", json={"mode": "resume"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert calls == []
    assert db_session.query(AnalysisJob).filter(AnalysisJob.video_id == video.id).count() == 1


def test_illegal_frame_name_returns_400(client, db_session) -> None:
    video = Video(filename="f.mp4", duration_ms=1000, status="queued")
    db_session.add(video)
    db_session.commit()

    resp = client.get(f"/api/videos/{video.id}/frames/foo.jpg")
    assert resp.status_code == 400


def test_delete_video_removes_row_segments_jobs_and_files(
    client, db_session, tmp_path, monkeypatch
) -> None:
    from uuid import UUID

    from video_analysis.models import AnalysisJob

    monkeypatch.setattr("video_analysis.api.probe_video", lambda path: 12500)
    resp = client.post(
        "/api/videos",
        files={"file": ("gone.mp4", b"delete-me-bytes", "video/mp4")},
    )
    assert resp.status_code in (200, 201)
    video_id = resp.json()["id"]
    source = tmp_path / video_id / "source.mp4"
    assert source.is_file()

    video = db_session.get(Video, UUID(video_id))
    assert video is not None
    db_session.add(
        Segment(
            video_id=video.id,
            t_start_ms=0,
            t_end_ms=1000,
            keyframe_path="frames/0.jpg",
            caption="x",
            ocr_text="",
        )
    )
    db_session.commit()

    del_resp = client.delete(f"/api/videos/{video_id}")
    assert del_resp.status_code == 200
    assert del_resp.json() == {"id": video_id, "deleted": True}
    assert client.get(f"/api/videos/{video_id}").status_code == 404
    assert db_session.get(Video, UUID(video_id)) is None
    assert db_session.query(Segment).filter(Segment.video_id == UUID(video_id)).count() == 0
    assert db_session.query(AnalysisJob).filter(AnalysisJob.video_id == UUID(video_id)).count() == 0
    assert not source.exists()


def test_delete_processing_video_removes_row(client, db_session) -> None:
    video = Video(filename="busy.mp4", duration_ms=1000, status="processing")
    db_session.add(video)
    db_session.commit()

    resp = client.delete(f"/api/videos/{video.id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert db_session.get(Video, video.id) is None


def test_delete_missing_video_returns_404(client) -> None:
    resp = client.delete("/api/videos/00000000-0000-0000-0000-000000000001")
    assert resp.status_code == 404
