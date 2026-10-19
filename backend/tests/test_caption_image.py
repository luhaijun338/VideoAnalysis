from pathlib import Path

from PIL import Image

from video_analysis.adapters.caption_zhipu import jpeg_bytes_for_caption


def test_jpeg_bytes_for_caption_shrinks_large_frame(tmp_path: Path) -> None:
    src = tmp_path / "big.jpg"
    Image.new("RGB", (1920, 1080), (10, 20, 30)).save(src, "JPEG", quality=95)
    out = jpeg_bytes_for_caption(src, max_side=768, quality=80)
    assert len(out) < src.stat().st_size
    from io import BytesIO

    img = Image.open(BytesIO(out))
    assert max(img.size) <= 768
