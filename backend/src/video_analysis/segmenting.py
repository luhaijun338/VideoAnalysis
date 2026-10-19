from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

# ffmpeg -f image2 `%d.jpg` is 1-based; never mix with timestamp names like 0.jpg / 2000.jpg
_FFMPEG_SEQ_JPG = re.compile(r"^[1-9]\d*\.jpg$")
_COMPARE_SIZE = 64
_DIFF_THRESHOLD = 12.0


@dataclass(frozen=True)
class SegmentWindow:
    t_start_ms: int
    t_end_ms: int
    keyframe_t_ms: int
    frame_paths: list[Path]


def parse_frame_t_ms(path: Path) -> int:
    return int(path.stem)


def _mean_abs_diff(a: Path, b: Path) -> float:
    ia = np.asarray(Image.open(a).convert("RGB").resize((_COMPARE_SIZE, _COMPARE_SIZE)), dtype=np.float32)
    ib = np.asarray(Image.open(b).convert("RGB").resize((_COMPARE_SIZE, _COMPARE_SIZE)), dtype=np.float32)
    return float(np.mean(np.abs(ia - ib)))


def frames_visually_same(a: Path, b: Path, threshold: float = _DIFF_THRESHOLD) -> bool:
    try:
        return _mean_abs_diff(a, b) < threshold
    except Exception:
        return False


def group_segments(
    frame_paths: list[Path],
    min_ms: int = 2000,
    max_ms: int = 8000,
    diff_threshold: float = _DIFF_THRESHOLD,
    interval_ms: int = 2000,
) -> list[SegmentWindow]:
    """Group similar frames. Static scenes stay one segment (max_ms is unused for merges)."""
    del max_ms  # kept for call-site compatibility; long idle must not be re-captioned every 8s
    if not frame_paths:
        return []
    ordered = sorted(frame_paths, key=parse_frame_t_ms)
    groups: list[list[Path]] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        same = _mean_abs_diff(prev, cur) < diff_threshold
        if same:
            groups[-1].append(cur)
        else:
            groups.append([cur])
    windows: list[SegmentWindow] = []
    for group in groups:
        t_start = parse_frame_t_ms(group[0])
        t_end = parse_frame_t_ms(group[-1]) + interval_ms
        if t_end - t_start < min_ms and windows:
            merged_paths = windows[-1].frame_paths + group
            t_start = windows[-1].t_start_ms
            t_end = parse_frame_t_ms(merged_paths[-1]) + interval_ms
            windows[-1] = SegmentWindow(
                t_start_ms=t_start,
                t_end_ms=t_end,
                keyframe_t_ms=parse_frame_t_ms(merged_paths[-1]),
                frame_paths=merged_paths,
            )
        else:
            windows.append(
                SegmentWindow(
                    t_start_ms=t_start,
                    t_end_ms=t_end,
                    keyframe_t_ms=parse_frame_t_ms(group[-1]),
                    frame_paths=group,
                )
            )
    return windows


def keep_only_keyframes(windows: list[SegmentWindow]) -> list[SegmentWindow]:
    """Drop intermediate stills: one jpg per segment (the keyframe)."""
    keep: set[Path] = set()
    out: list[SegmentWindow] = []
    for window in windows:
        keyframe = window.frame_paths[-1]
        keep.add(keyframe.resolve())
        out.append(replace(window, frame_paths=[keyframe], keyframe_t_ms=parse_frame_t_ms(keyframe)))
    parents = {p.parent for p in keep}
    for folder in parents:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.jpg"):
            if path.resolve() not in keep:
                path.unlink(missing_ok=True)
    return out


def parse_ffmpeg_out_time(value: str) -> float | None:
    text = value.strip()
    if not text or text.upper() == "N/A":
        return None
    parts = text.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None


def _ffmpeg_extract_cmd(source: Path, pattern: Path, interval_s: float, *, with_progress: bool) -> list[str]:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"fps=1/{interval_s},scale=min(960\\,iw):-2",
        "-q:v",
        "5",
    ]
    if with_progress:
        cmd.extend(["-nostats", "-progress", "pipe:1"])
    cmd.append(str(pattern))
    return cmd


def _run_ffmpeg_with_progress(
    cmd: list[str],
    *,
    duration_ms: int | None,
    on_progress: Callable[[float], None],
) -> None:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    err_chunks: list[str] = []

    def _drain_stderr() -> None:
        if proc.stderr is not None:
            err_chunks.append(proc.stderr.read())

    drain = threading.Thread(target=_drain_stderr, daemon=True)
    drain.start()
    duration_s = (duration_ms or 0) / 1000.0
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            if duration_s <= 0:
                continue
            if line.startswith("out_time="):
                seconds = parse_ffmpeg_out_time(line.split("=", 1)[1])
                if seconds is not None:
                    on_progress(min(1.0, seconds / duration_s))
            elif line.startswith("progress=") and "end" in line:
                on_progress(1.0)
    finally:
        code = proc.wait()
        drain.join(timeout=5)
    stderr = "".join(err_chunks)
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd, output=None, stderr=stderr)
    on_progress(1.0)


def extract_frames(
    source: Path,
    dest_dir: Path,
    interval_s: float = 2.0,
    *,
    duration_ms: int | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="extract_", dir=dest_dir.parent))
    try:
        pattern = work_dir / "%d.jpg"
        cmd = _ffmpeg_extract_cmd(source, pattern, interval_s, with_progress=on_progress is not None)
        if on_progress is None:
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            _run_ffmpeg_with_progress(cmd, duration_ms=duration_ms, on_progress=on_progress)
        raw = sorted(
            (p for p in work_dir.iterdir() if p.is_file() and _FFMPEG_SEQ_JPG.match(p.name)),
            key=lambda p: int(p.stem),
        )
        for old in dest_dir.glob("*.jpg"):
            old.unlink()
        renamed: list[Path] = []
        for p in raw:
            idx = int(p.stem)
            t_ms = int((idx - 1) * interval_s * 1000)
            target = dest_dir / f"{t_ms}.jpg"
            shutil.move(str(p), str(target))
            renamed.append(target)
        return renamed
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
