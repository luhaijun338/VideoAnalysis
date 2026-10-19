from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from video_analysis.segmenting import (
    extract_frames,
    frames_visually_same,
    group_segments,
    keep_only_keyframes,
    parse_ffmpeg_out_time,
    parse_frame_t_ms,
)


def _solid(path: Path, color: tuple[int, int, int]) -> None:
    Image.new("RGB", (32, 32), color).save(path, "JPEG")


def _fake_ffmpeg_write(indices: tuple[int, ...]):
    def _fake_run(cmd, **kwargs):
        out_dir = Path(cmd[-1]).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        for idx in indices:
            Image.new("RGB", (8, 8), (0, 0, 0)).save(out_dir / f"{idx}.jpg", "JPEG")
        return MagicMock(returncode=0)

    return _fake_run


def test_parse_frame_t_ms() -> None:
    assert parse_frame_t_ms(Path("4000.jpg")) == 4000


def test_group_similar_frames_and_split_on_change(tmp_path: Path) -> None:
    colors = [(255, 0, 0)] * 3 + [(0, 0, 255)] * 3
    paths = []
    for i, color in enumerate(colors):
        p = tmp_path / f"{i * 2000}.jpg"
        _solid(p, color)
        paths.append(p)
    segs = group_segments(paths)
    assert len(segs) == 2
    assert segs[0].t_start_ms == 0
    assert segs[0].t_end_ms == 6000
    assert segs[0].keyframe_t_ms == 4000
    assert segs[1].t_start_ms == 6000
    assert segs[1].t_end_ms == 12000
    assert segs[1].keyframe_t_ms == 10000


def test_long_static_scene_stays_one_segment(tmp_path: Path) -> None:
    paths = []
    for i in range(6):
        p = tmp_path / f"{i * 2000}.jpg"
        _solid(p, (10, 10, 10))
        paths.append(p)
    segs = group_segments(paths)
    assert len(segs) == 1
    assert segs[0].t_start_ms == 0
    assert segs[0].t_end_ms == 12000
    assert segs[0].keyframe_t_ms == 10000


def test_keep_only_keyframes_deletes_intermediate_frames(tmp_path: Path) -> None:
    paths = []
    for i in range(4):
        p = tmp_path / f"{i * 2000}.jpg"
        _solid(p, (10, 10, 10) if i < 3 else (200, 0, 0))
        paths.append(p)
    segs = keep_only_keyframes(group_segments(paths))
    remaining = sorted(p.name for p in tmp_path.glob("*.jpg"))
    assert remaining == [s.frame_paths[-1].name for s in segs]
    assert all(len(s.frame_paths) == 1 for s in segs)


def test_frames_visually_same_for_identical_stills(tmp_path: Path) -> None:
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _solid(a, (40, 40, 40))
    _solid(b, (40, 40, 40))
    assert frames_visually_same(a, b)
    c = tmp_path / "c.jpg"
    _solid(c, (200, 10, 10))
    assert not frames_visually_same(a, c)


def test_extract_frames_renames_to_t_ms(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake")
    dest = tmp_path / "frames"

    with patch("video_analysis.segmenting.subprocess.run", side_effect=_fake_ffmpeg_write((1, 2, 3))):
        paths = extract_frames(source, dest, interval_s=2.0)

    assert [p.name for p in paths] == ["0.jpg", "2000.jpg", "4000.jpg"]
    assert all(p.exists() for p in paths)


def test_extract_frames_replaces_existing_timestamp_jpgs(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake")
    dest = tmp_path / "frames"
    dest.mkdir()
    Image.new("RGB", (8, 8), (255, 0, 0)).save(dest / "0.jpg", "JPEG")
    Image.new("RGB", (8, 8), (0, 255, 0)).save(dest / "2000.jpg", "JPEG")

    with patch("video_analysis.segmenting.subprocess.run", side_effect=_fake_ffmpeg_write((1, 2))):
        paths = extract_frames(source, dest, interval_s=2.0)

    names = sorted(p.name for p in dest.glob("*.jpg"))
    assert names == ["0.jpg", "2000.jpg"]
    assert [p.name for p in paths] == ["0.jpg", "2000.jpg"]
    assert not (dest / "-2000.jpg").exists()


def test_parse_ffmpeg_out_time() -> None:
    assert parse_ffmpeg_out_time("00:00:05.000000") == 5.0
    assert parse_ffmpeg_out_time("01:02:03.5") == 3723.5
    assert parse_ffmpeg_out_time("N/A") is None


def test_extract_frames_reports_progress(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake")
    dest = tmp_path / "frames"
    seen: list[float] = []

    def fake_popen(cmd, **kwargs):
        out_dir = Path(cmd[-1]).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), (0, 0, 0)).save(out_dir / "1.jpg", "JPEG")

        class FakeProc:
            stdout = iter(["out_time=00:00:05.000000\n", "progress=end\n"])
            stderr = MagicMock()
            stderr.read.return_value = ""

            def wait(self):
                return 0

        return FakeProc()

    with patch("video_analysis.segmenting.subprocess.Popen", side_effect=fake_popen):
        paths = extract_frames(
            source,
            dest,
            interval_s=2.0,
            duration_ms=10_000,
            on_progress=seen.append,
        )

    assert [p.name for p in paths] == ["0.jpg"]
    assert seen[0] == 0.5
    assert seen[-1] == 1.0
