from __future__ import annotations

from pathlib import Path
from threading import Lock


class RapidOcrAdapter:
    def __init__(self) -> None:
        self._ocr = None
        self._lock = Lock()

    def _engine(self):
        if self._ocr is None:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr = RapidOCR()
        return self._ocr

    def recognize(self, image_path: Path) -> str:
        with self._lock:
            result, _ = self._engine()(str(image_path))
        if not result:
            return ""
        lines: list[str] = []
        for item in result:
            # RapidOCR: [box, text, score]
            if len(item) >= 2 and item[1]:
                lines.append(str(item[1]))
        return "\n".join(lines)
