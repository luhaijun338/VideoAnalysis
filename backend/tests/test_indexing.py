from pathlib import Path

from PIL import Image
from sqlalchemy import select

from video_analysis.adapters.caption_zhipu import RaisingCaptionAdapter
from video_analysis.adapters.fake import FakeCaptionAdapter, FakeEmbedAdapter, FakeOcrAdapter
from video_analysis.embed_text import operation_embed_text
from video_analysis.indexing import index_segment, ocr_pseudo_log, pick_representative_frames
from video_analysis.models import Segment, Video
from video_analysis.segmenting import SegmentWindow
from video_analysis.storage import LocalStorage


def _jpeg(path: Path) -> Path:
    Image.new("RGB", (16, 16), (255, 0, 0)).save(path, "JPEG")
    return path


def test_index_segment_writes_caption_embedding_fts(db_session, tmp_path: Path) -> None:
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=8000, status="processing")
    db_session.add(video)
    db_session.flush()
    storage = LocalStorage(tmp_path)
    window = SegmentWindow(0, 4000, 0, [frame])
    seg = index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "导出 客户名单"}),
        FakeCaptionAdapter("点击导出"),
        FakeEmbedAdapter(),
        storage,
    )
    db_session.commit()
    loaded = db_session.scalar(select(Segment).where(Segment.id == seg.id))
    assert "导出" in loaded.caption
    assert len(loaded.embedding) == 1024
    assert loaded.fts is not None
    assert loaded.caption_degraded is False


def test_ocr_pseudo_log_compacts_whitespace_and_truncates() -> None:
    assert ocr_pseudo_log("导出\n  客户") == "导出 客户"
    long = "字" * 100
    out = ocr_pseudo_log(long, max_chars=20)
    assert len(out) == 20
    assert out.endswith("…")


def test_index_segment_degrades_when_caption_fails(db_session, tmp_path: Path) -> None:
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=8000, status="processing")
    db_session.add(video)
    db_session.flush()
    window = SegmentWindow(0, 4000, 0, [frame])
    seg = index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "导出 客户名单"}),
        FakeCaptionAdapter(fail=True),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    assert seg.caption_degraded is True
    assert seg.caption == "导出 客户名单"
    assert seg.embedding is not None


def test_pick_representative_frames_prefers_last() -> None:
    frames = [Path(f"{i}.jpg") for i in range(6)]
    picked = pick_representative_frames(frames, max_count=3)
    assert len(picked) <= 3
    assert picked[-1] == frames[-1]


def test_pick_representative_frames_defaults_to_one() -> None:
    frames = [Path(f"{i}.jpg") for i in range(6)]
    picked = pick_representative_frames(frames)
    assert picked == [frames[-1]]


def test_index_segment_embeds_caption_not_ocr_noise(db_session, tmp_path: Path) -> None:
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=8000, status="processing")
    db_session.add(video)
    db_session.flush()

    class FixedCaption:
        model_name = "fixed"

        def caption(self, frames: list[Path], ocr_text: str) -> str:
            return "在「手工升级」· 点击 「连接测试」"

    class RecordingEmbed(FakeEmbedAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[str] = []

        def embed(self, text: str) -> list[float]:
            self.seen.append(text)
            return super().embed(text)

    embedder = RecordingEmbed()
    window = SegmentWindow(0, 4000, 0, [frame])
    index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "云 Easy-RFC 配置管理 系统管理 监控中心"}),
        FixedCaption(),
        embedder,
        LocalStorage(tmp_path),
    )
    assert embedder.seen
    assert embedder.seen[0] == operation_embed_text("在「手工升级」· 点击 「连接测试」")
    assert "Easy-RFC" not in embedder.seen[0]
    assert "配置管理" not in embedder.seen[0]


def test_index_segment_uses_at_most_three_frames(db_session, tmp_path: Path) -> None:
    frames = [_jpeg(tmp_path / f"{i * 2000}.jpg") for i in range(6)]
    video = Video(filename="a.mp4", duration_ms=12000, status="processing")
    db_session.add(video)
    db_session.flush()

    class RecordingOcr(FakeOcrAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[str] = []

        def recognize(self, image_path: Path) -> str:
            self.seen.append(image_path.name)
            return "字"

    class RecordingCaption(FakeCaptionAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[list[str]] = []

        def caption(self, frames: list[Path], ocr_text: str) -> str:
            self.seen.append([f.name for f in frames])
            return super().caption(frames, ocr_text)

    ocr = RecordingOcr()
    captioner = RecordingCaption()
    window = SegmentWindow(0, 12000, 10000, frames)
    index_segment(db_session, video, window, ocr, captioner, FakeEmbedAdapter(), LocalStorage(tmp_path))
    assert len(ocr.seen) <= 3
    assert ocr.seen[-1] == frames[-1].name
    assert captioner.seen
    assert len(captioner.seen[0]) <= 3
    assert captioner.seen[0][-1] == frames[-1].name


def test_caption_retries_with_backoff(db_session, tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("video_analysis.indexing.retry_sleep", lambda delay: sleeps.append(delay))
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=4000, status="processing")
    db_session.add(video)
    db_session.flush()

    class FlakyCaption:
        model_name = "flaky"

        def __init__(self) -> None:
            self.n = 0

        def caption(self, frames: list[Path], ocr_text: str) -> str:
            self.n += 1
            if self.n < 3:
                raise RuntimeError("transient")
            return "ok"

    window = SegmentWindow(0, 4000, 0, [frame])
    seg = index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "导出"}),
        FlakyCaption(),
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    assert seg.caption == "ok"
    assert sleeps == [0.5, 1.0]


def test_empty_zhipu_skips_caption_retries(db_session, tmp_path: Path, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("video_analysis.indexing.retry_sleep", lambda delay: sleeps.append(delay))
    frame = _jpeg(tmp_path / "0.jpg")
    video = Video(filename="a.mp4", duration_ms=4000, status="processing")
    db_session.add(video)
    db_session.flush()
    captioner = RaisingCaptionAdapter()
    calls = {"n": 0}
    original = captioner.caption

    def counting(frames, ocr_text):
        calls["n"] += 1
        return original(frames, ocr_text)

    captioner.caption = counting  # type: ignore[method-assign]
    window = SegmentWindow(0, 4000, 0, [frame])
    seg = index_segment(
        db_session,
        video,
        window,
        FakeOcrAdapter({frame.name: "导出"}),
        captioner,
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    assert seg.caption_degraded is True
    assert calls["n"] == 0
    assert sleeps == []


def test_index_segment_reuses_previous_without_caption(db_session, tmp_path: Path) -> None:
    frame_a = _jpeg(tmp_path / "0.jpg")
    frame_b = _jpeg(tmp_path / "4000.jpg")
    video = Video(filename="a.mp4", duration_ms=8000, status="processing")
    db_session.add(video)
    db_session.flush()

    class RecCaption:
        model_name = "rec"
        n = 0

        def caption(self, frames: list[Path], ocr_text: str) -> str:
            type(self).n += 1
            return "在「页面」· 等待结果"

    captioner = RecCaption()
    first = index_segment(
        db_session,
        video,
        SegmentWindow(0, 4000, 0, [frame_a]),
        FakeOcrAdapter({frame_a.name: "确定"}),
        captioner,
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
    )
    second = index_segment(
        db_session,
        video,
        SegmentWindow(4000, 8000, 4000, [frame_b]),
        FakeOcrAdapter({frame_b.name: "不应该用到"}),
        captioner,
        FakeEmbedAdapter(),
        LocalStorage(tmp_path),
        reuse_from=first,
    )
    assert RecCaption.n == 1
    assert second.caption == first.caption
    assert second.ocr_text == first.ocr_text
    assert second.embedding == first.embedding
