from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _video_dir(self, video_id: str) -> Path:
        return self.root / video_id

    def source_path(self, video_id: str) -> Path:
        return self._video_dir(video_id) / "source.mp4"

    def frame_path(self, video_id: str, t_start_ms: int) -> Path:
        return self._video_dir(video_id) / "frames" / f"{t_start_ms}.jpg"

    def save_source(self, video_id: str, data: BinaryIO) -> Path:
        path = self.source_path(video_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            shutil.copyfileobj(data, f)
        return path

    def delete_video(self, video_id: str) -> None:
        shutil.rmtree(self._video_dir(video_id), ignore_errors=True)

    def save_frame(self, video_id: str, t_start_ms: int, image: bytes) -> Path:
        path = self.frame_path(video_id, t_start_ms)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image)
        return path
