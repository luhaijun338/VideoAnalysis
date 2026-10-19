from pgvector.sqlalchemy import Vector
from sqlalchemy import select

from video_analysis.models import Segment, Video


def test_insert_video_and_segment_with_embedding(db_session) -> None:
    video = Video(filename="a.mp4", duration_ms=10_000, status="queued")
    db_session.add(video)
    db_session.flush()
    seg = Segment(
        video_id=video.id,
        t_start_ms=0,
        t_end_ms=4000,
        keyframe_path="frames/0.jpg",
        ocr_text="导出 客户名单",
        caption="点击导出",
        caption_degraded=False,
        embedding=[0.01] * 1024,
        fts="导出 客户 名单 点击 导出",
        model_caption="fake",
        model_embed="fake",
    )
    db_session.add(seg)
    db_session.commit()
    loaded = db_session.scalar(select(Segment).where(Segment.video_id == video.id))
    assert loaded is not None
    assert len(loaded.embedding) == 1024
    assert video.status == "queued"
