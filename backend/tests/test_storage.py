import io
from pathlib import Path

from video_analysis.storage import LocalStorage

VIDEO_ID = "11111111-1111-1111-1111-111111111111"


def test_save_source_writes_source_mp4(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = storage.save_source(VIDEO_ID, io.BytesIO(b"fake-bytes"))
    assert path == tmp_path / VIDEO_ID / "source.mp4"
    assert path.read_bytes() == b"fake-bytes"
    assert storage.source_path(VIDEO_ID) == path


def test_save_frame_uses_millisecond_filename(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    path = storage.save_frame(VIDEO_ID, 123000, b"jpeg-bytes")
    assert path == tmp_path / VIDEO_ID / "frames" / "123000.jpg"
    assert path.read_bytes() == b"jpeg-bytes"
    assert storage.frame_path(VIDEO_ID, 123000) == path
