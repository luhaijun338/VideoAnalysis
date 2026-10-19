from pathlib import Path
from typing import Protocol


class OcrAdapter(Protocol):
    def recognize(self, image_path: Path) -> str: ...


class CaptionAdapter(Protocol):
    def caption(self, frames: list[Path], ocr_text: str) -> str: ...


class EmbedAdapter(Protocol):
    def embed(self, text: str) -> list[float]: ...
