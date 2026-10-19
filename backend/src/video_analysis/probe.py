from __future__ import annotations

import subprocess
from pathlib import Path

from video_analysis.config import settings


class ProbeError(ValueError):
    pass


def validate_upload(filename: str, size_bytes: int) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in settings.allowed_suffixes:
        raise ProbeError("unsupported format")
    if size_bytes > settings.max_upload_bytes:
        raise ProbeError("file exceeds size limit")


def probe_video(path: Path) -> int:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ProbeError("cannot read duration") from exc
    if result.returncode != 0:
        raise ProbeError("cannot read duration")
    try:
        seconds = float(result.stdout.strip())
    except ValueError as exc:
        raise ProbeError("cannot read duration") from exc
    if seconds <= 0:
        raise ProbeError("cannot read duration")
    return int(seconds * 1000)
