from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from video_analysis.adapters.base import EmbedAdapter
from video_analysis.embed_text import operation_embed_text
from video_analysis.fts import tokenize_fts
from video_analysis.models import Segment, Video

DEFAULT_MIN_SCORE = 0.45
VECTOR_CANDIDATES = 80
FTS_CANDIDATES = 50


@dataclass
class Hit:
    segment_id: str
    video_id: str
    t_start_ms: int
    t_end_ms: int
    caption: str
    ocr_text: str
    keyframe_url: str
    score: float
    caption_degraded: bool


@dataclass
class VideoGroup:
    video_id: str
    filename: str
    duration_ms: int
    best_score: float
    hits: list[Hit]


@dataclass
class SearchResult:
    query: str
    total_hits: int
    limit_hits: int
    offset_hits: int
    total_videos: int
    videos: list[VideoGroup]
    min_score: float = DEFAULT_MIN_SCORE


def rrf_merge(ranked_ids: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranked in ranked_ids:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def merge_overlapping_hits(hits: list[Hit]) -> list[Hit]:
    if not hits:
        return []
    ordered = sorted(hits, key=lambda h: h.t_start_ms)
    merged: list[Hit] = [ordered[0]]
    for hit in ordered[1:]:
        acc = merged[-1]
        if hit.video_id == acc.video_id and hit.t_start_ms < acc.t_end_ms:
            if hit.score >= acc.score:
                merged[-1] = replace(
                    hit,
                    t_start_ms=min(acc.t_start_ms, hit.t_start_ms),
                    t_end_ms=max(acc.t_end_ms, hit.t_end_ms),
                    score=max(acc.score, hit.score),
                )
            else:
                merged[-1] = replace(
                    acc,
                    t_start_ms=min(acc.t_start_ms, hit.t_start_ms),
                    t_end_ms=max(acc.t_end_ms, hit.t_end_ms),
                    score=max(acc.score, hit.score),
                )
        else:
            merged.append(hit)
    return merged


def _keyframe_url(video_id: uuid.UUID | str, keyframe_path: str) -> str:
    return f"/api/videos/{video_id}/frames/{Path(keyframe_path).name}"


def _video_time_filters(
    created_from: datetime | None,
    created_to: datetime | None,
) -> list:
    conds = [Video.status == "ready"]
    if created_from is not None:
        conds.append(Video.created_at >= created_from)
    if created_to is not None:
        conds.append(Video.created_at <= created_to)
    return conds


def _vector_ranked_ids(
    session: Session,
    query_vec: list[float],
    created_from: datetime | None,
    created_to: datetime | None,
) -> list[str]:
    stmt = (
        select(Segment.id)
        .join(Video, Segment.video_id == Video.id)
        .where(and_(*_video_time_filters(created_from, created_to)))
        .where(Segment.embedding.is_not(None))
        .order_by(Segment.embedding.cosine_distance(query_vec))
        .limit(VECTOR_CANDIDATES)
    )
    return [str(row) for row in session.scalars(stmt).all()]


def _fts_ranked_ids(
    session: Session,
    query: str,
    created_from: datetime | None,
    created_to: datetime | None,
) -> list[str]:
    tokens = tokenize_fts(query)
    if not tokens.strip():
        return []
    tsq = func.plainto_tsquery("simple", tokens)
    stmt = (
        select(Segment.id)
        .join(Video, Segment.video_id == Video.id)
        .where(and_(*_video_time_filters(created_from, created_to)))
        .where(Segment.embedding.is_not(None))
        .where(Segment.fts.op("@@")(tsq))
        .order_by(func.ts_rank(Segment.fts, tsq).desc())
        .limit(FTS_CANDIDATES)
    )
    return [str(row) for row in session.scalars(stmt).all()]


def _cosine_by_id(session: Session, query_vec: list[float], ids: list[str]) -> dict[str, float]:
    if not ids:
        return {}
    uuids = [uuid.UUID(sid) for sid in ids]
    dist = Segment.embedding.cosine_distance(query_vec)
    rows = session.execute(select(Segment.id, dist).where(Segment.id.in_(uuids))).all()
    return {str(sid): 1.0 - float(distance) for sid, distance in rows}


def search_videos(
    session: Session,
    embedder: EmbedAdapter,
    query: str,
    limit_hits: int = 3,
    offset_hits: int = 0,
    min_score: float = DEFAULT_MIN_SCORE,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> SearchResult:
    embed_q = operation_embed_text(query)
    query_vec = embedder.embed(embed_q or query)
    vector_ids = _vector_ranked_ids(session, query_vec, created_from, created_to)
    fts_ids = _fts_ranked_ids(session, query, created_from, created_to)
    candidate_ids = list(dict.fromkeys([*vector_ids, *fts_ids]))
    cosine = _cosine_by_id(session, query_vec, candidate_ids)

    scores: dict[str, float] = {}
    for sid in candidate_ids:
        sim = max(0.0, min(1.0, cosine.get(sid, 0.0)))
        if min_score <= 0 or sim >= min_score:
            scores[sid] = sim

    if not scores:
        return SearchResult(
            query=query,
            total_hits=0,
            limit_hits=limit_hits,
            offset_hits=offset_hits,
            total_videos=0,
            videos=[],
            min_score=min_score,
        )

    seg_uuids = [uuid.UUID(sid) for sid in scores]
    rows = session.execute(
        select(Segment, Video)
        .join(Video, Segment.video_id == Video.id)
        .where(Segment.id.in_(seg_uuids))
    ).all()

    by_video: dict[str, list[Hit]] = {}
    video_meta: dict[str, Video] = {}
    for segment, video in rows:
        sid = str(segment.id)
        vid = str(video.id)
        hit = Hit(
            segment_id=sid,
            video_id=vid,
            t_start_ms=segment.t_start_ms,
            t_end_ms=segment.t_end_ms,
            caption=segment.caption,
            ocr_text=segment.ocr_text,
            keyframe_url=_keyframe_url(vid, segment.keyframe_path),
            score=scores[sid],
            caption_degraded=segment.caption_degraded,
        )
        by_video.setdefault(vid, []).append(hit)
        video_meta[vid] = video

    ranked: list[Hit] = []
    for hits in by_video.values():
        ranked.extend(merge_overlapping_hits(hits))
    ranked.sort(key=lambda h: h.score, reverse=True)
    total_hits = len(ranked)
    page_hits = ranked[offset_hits : offset_hits + limit_hits]

    grouped: dict[str, list[Hit]] = {}
    order: list[str] = []
    for hit in page_hits:
        if hit.video_id not in grouped:
            grouped[hit.video_id] = []
            order.append(hit.video_id)
        grouped[hit.video_id].append(hit)

    groups: list[VideoGroup] = []
    for vid in order:
        hits = grouped[vid]
        video = video_meta[vid]
        groups.append(
            VideoGroup(
                video_id=vid,
                filename=video.filename,
                duration_ms=video.duration_ms,
                best_score=hits[0].score,
                hits=hits,
            )
        )

    return SearchResult(
        query=query,
        total_hits=total_hits,
        limit_hits=limit_hits,
        offset_hits=offset_hits,
        total_videos=len({h.video_id for h in ranked}),
        videos=groups,
        min_score=min_score,
    )
