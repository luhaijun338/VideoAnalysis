from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func

from video_analysis.adapters.fake import FakeEmbedAdapter
from video_analysis.embed_text import operation_embed_text
from video_analysis.fts import tokenize_fts
from video_analysis.models import Segment, Video
from video_analysis.search import Hit, merge_overlapping_hits, rrf_merge, search_videos


def _hit(
    *,
    t_start_ms: int,
    t_end_ms: int,
    score: float,
    caption: str = "x",
    video_id: str = "vid",
    segment_id: str = "seg",
) -> Hit:
    return Hit(
        segment_id=segment_id,
        video_id=video_id,
        t_start_ms=t_start_ms,
        t_end_ms=t_end_ms,
        caption=caption,
        ocr_text="",
        keyframe_url="/f.jpg",
        score=score,
        caption_degraded=False,
    )


def test_merge_does_not_collapse_adjacent_tiled_segments() -> None:
    """Segments tile the video (end of one == start of next). Those are not overlaps."""
    early = _hit(t_start_ms=0, t_end_ms=2000, score=0.2, caption="early", segment_id="a")
    late = _hit(
        t_start_ms=2000,
        t_end_ms=4000,
        score=0.9,
        caption="click 连接测试",
        segment_id="b",
    )
    merged = merge_overlapping_hits([early, late])
    assert [(h.t_start_ms, h.t_end_ms, h.caption) for h in merged] == [
        (0, 2000, "early"),
        (2000, 4000, "click 连接测试"),
    ]


def test_merge_true_time_overlap_keeps_best_caption() -> None:
    low = _hit(t_start_ms=10000, t_end_ms=15000, score=0.4, caption="low", segment_id="a")
    high = _hit(
        t_start_ms=12000,
        t_end_ms=18000,
        score=0.9,
        caption="high",
        segment_id="b",
    )
    merged = merge_overlapping_hits([low, high])
    assert len(merged) == 1
    assert merged[0].t_start_ms == 10000
    assert merged[0].t_end_ms == 18000
    assert merged[0].caption == "high"


def _add_ready_video(session, filename: str, duration_ms: int = 60_000) -> Video:
    video = Video(filename=filename, duration_ms=duration_ms, status="ready")
    session.add(video)
    session.flush()
    return video


def _add_segment(
    session,
    video: Video,
    *,
    t_start_ms: int,
    t_end_ms: int,
    caption: str,
    ocr_text: str,
    embedding: list[float],
    keyframe_path: str = "frames/0.jpg",
) -> Segment:
    seg = Segment(
        video_id=video.id,
        t_start_ms=t_start_ms,
        t_end_ms=t_end_ms,
        keyframe_path=keyframe_path,
        caption=caption,
        ocr_text=ocr_text,
        embedding=embedding,
        fts=func.to_tsvector("simple", tokenize_fts(caption, ocr_text)),
    )
    session.add(seg)
    session.flush()
    return seg


def test_rrf_prefers_items_high_in_both_lists() -> None:
    scores = rrf_merge(
        [
            ["shared", "only_first"],
            ["shared", "only_second"],
        ]
    )
    assert scores["shared"] > scores["only_first"]
    assert scores["shared"] > scores["only_second"]


def test_search_returns_global_top_3_hits(db_session) -> None:
    embedder = FakeEmbedAdapter()
    query = "唯一导出令牌 ALPHA-HIT-LIMIT"
    emb = embedder.embed(operation_embed_text(query))
    video = _add_ready_video(db_session, "a.mp4")
    for i in range(4):
        t0 = i * 10_000
        _add_segment(
            db_session,
            video,
            t_start_ms=t0,
            t_end_ms=t0 + 4000,
            caption=query,
            ocr_text=query,
            embedding=emb,
            keyframe_path=f"frames/{t0}.jpg",
        )
    db_session.flush()

    result = search_videos(db_session, embedder, query, limit_hits=3, offset_hits=0)
    hits = [h for group in result.videos for h in group.hits]
    assert len(hits) == 3
    assert {h.caption for h in hits} == {query}
    assert result.limit_hits == 3
    assert result.total_hits >= 4


def test_keyword_path_hits_ocr_only(db_session) -> None:
    embedder = FakeEmbedAdapter()
    video = _add_ready_video(db_session, "ocr-only.mp4")
    _add_segment(
        db_session,
        video,
        t_start_ms=0,
        t_end_ms=4000,
        caption="点击按钮",
        ocr_text="客户名单",
        embedding=embedder.embed("zzzz-unrelated"),
    )
    db_session.flush()

    result = search_videos(db_session, embedder, "客户名单", min_score=0.0)
    assert str(video.id) in {v.video_id for v in result.videos}


def test_offset_hits_pages(db_session) -> None:
    embedder = FakeEmbedAdapter()
    video = _add_ready_video(db_session, "paged.mp4")
    emb = embedder.embed(operation_embed_text("客户名单"))
    for i in range(6):
        t0 = i * 10_000
        _add_segment(
            db_session,
            video,
            t_start_ms=t0,
            t_end_ms=t0 + 4000,
            caption="客户名单",
            ocr_text="客户名单",
            embedding=emb,
            keyframe_path=f"frames/{t0}.jpg",
        )
    db_session.flush()

    page1 = search_videos(db_session, embedder, "客户名单", limit_hits=3, offset_hits=0)
    page2 = search_videos(db_session, embedder, "客户名单", limit_hits=3, offset_hits=3)
    starts1 = {h.t_start_ms for g in page1.videos for h in g.hits}
    starts2 = {h.t_start_ms for g in page2.videos for h in g.hits}
    assert sum(len(g.hits) for g in page1.videos) == 3
    assert sum(len(g.hits) for g in page2.videos) == 3
    assert starts1.isdisjoint(starts2)


def test_search_score_is_cosine_similarity_near_one(db_session) -> None:
    embedder = FakeEmbedAdapter()
    query = "在手工升级点击连接测试"
    video = _add_ready_video(db_session, "cos.mp4")
    _add_segment(
        db_session,
        video,
        t_start_ms=0,
        t_end_ms=4000,
        caption=query,
        ocr_text="侧栏菜单",
        embedding=embedder.embed(operation_embed_text(query)),
    )
    db_session.flush()

    result = search_videos(db_session, embedder, query, min_score=0.0)
    hits = [h for group in result.videos for h in group.hits]
    assert len(hits) == 1
    assert hits[0].score == pytest.approx(1.0, abs=1e-5)


def test_search_min_score_drops_unrelated_vector_hit(db_session) -> None:
    embedder = FakeEmbedAdapter()
    video = _add_ready_video(db_session, "weak.mp4")
    _add_segment(
        db_session,
        video,
        t_start_ms=0,
        t_end_ms=4000,
        caption="打开帮助文档",
        ocr_text="帮助",
        embedding=embedder.embed(operation_embed_text("打开帮助文档")),
    )
    db_session.flush()

    weak = search_videos(db_session, embedder, "连接测试网络连通性", min_score=0.45)
    assert weak.total_hits == 0
    all_hits = search_videos(db_session, embedder, "连接测试网络连通性", min_score=0.0)
    assert all_hits.total_hits >= 1
    assert all(h.score < 0.45 for g in all_hits.videos for h in g.hits)


def test_search_filters_by_video_created_at(db_session) -> None:
    embedder = FakeEmbedAdapter()
    query = "导出客户名单"
    emb = embedder.embed(operation_embed_text(query))
    old = _add_ready_video(db_session, "old.mp4")
    old.created_at = datetime(2020, 1, 15, tzinfo=timezone.utc)
    new = _add_ready_video(db_session, "new.mp4")
    new.created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    _add_segment(
        db_session,
        old,
        t_start_ms=0,
        t_end_ms=4000,
        caption=query,
        ocr_text=query,
        embedding=emb,
    )
    _add_segment(
        db_session,
        new,
        t_start_ms=0,
        t_end_ms=4000,
        caption=query,
        ocr_text=query,
        embedding=emb,
    )
    db_session.flush()

    result = search_videos(
        db_session,
        embedder,
        query,
        min_score=0.0,
        created_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    names = {v.filename for v in result.videos}
    assert names == {"new.mp4"}

    bounded = search_videos(
        db_session,
        embedder,
        query,
        min_score=0.0,
        created_from=datetime(2019, 1, 1, tzinfo=timezone.utc),
        created_to=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    assert {v.filename for v in bounded.videos} == {"old.mp4"}
