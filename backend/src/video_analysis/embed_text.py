from __future__ import annotations

OPERATION_EMBED_PREFIX = "软件操作记录："


def operation_embed_text(text: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return ""
    return f"{OPERATION_EMBED_PREFIX}{compact}"
