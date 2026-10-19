import hashlib
import math
from pathlib import Path


class FakeOcrAdapter:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self.mapping = mapping or {}

    def recognize(self, image_path: Path) -> str:
        return self.mapping.get(image_path.name, self.mapping.get(str(image_path), ""))


class FakeCaptionAdapter:
    def __init__(self, text: str = "执行了界面操作", fail: bool = False) -> None:
        self.text = text
        self.fail = fail

    def caption(self, frames: list[Path], ocr_text: str) -> str:
        if self.fail:
            raise RuntimeError("caption failed")
        if ocr_text:
            return f"{self.text}：{ocr_text}"
        return self.text


class FakeEmbedAdapter:
    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        seed = digest
        while len(values) < 1024:
            for b in seed:
                values.append((b / 127.5) - 1.0)
                if len(values) == 1024:
                    break
            seed = hashlib.sha256(seed).digest()
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
