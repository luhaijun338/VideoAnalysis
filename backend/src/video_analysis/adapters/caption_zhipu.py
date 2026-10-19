from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from video_analysis.config import settings

CAPTION_SYSTEM_PROMPT = (
    "你是软件操作录屏的标注器。只输出一句中文操作日志，不要 Markdown，不要时间戳。"
    "句式：在「页面或模块名」· 动作 · 关键对象或输入内容。"
    "必须写出操作意图：操作员在做什么、要达成什么（如测试网络连通、提交升级、导出名单），"
    "不要只写「点击了某个按钮」而不说明目的。"
    "必须优先使用 OCR 文本中的真实按钮/菜单/字段文案；不要空泛形容界面，不要罗列侧栏菜单。"
    "不要写「用户可能」「似乎」等推测套话。"
)
_SYSTEM_PROMPT = CAPTION_SYSTEM_PROMPT


def jpeg_bytes_for_caption(path: Path, max_side: int = 768, quality: int = 80) -> bytes:
    img = Image.open(path).convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


class ZhipuCaptionAdapter:
    model_name = settings.caption_model

    def caption(self, frames: list[Path], ocr_text: str) -> str:
        from openai import OpenAI

        if not settings.zhipu_api_key:
            raise RuntimeError("zhipu_api_key not configured")

        client = OpenAI(
            api_key=settings.zhipu_api_key,
            base_url=settings.caption_base_url,
        )
        content: list[dict] = []
        for frame in frames:
            b64 = base64.b64encode(jpeg_bytes_for_caption(frame)).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                }
            )
        text = "OCR文本：\n" + ocr_text if ocr_text.strip() else "请根据截图描述界面上的操作。"
        text += (
            "\n请用一句操作日志概括：操作员的意图 + 所在页面 + 动作 + 对象。"
            "忽略与当前操作无关的侧栏/导航菜单文字。"
        )
        content.append({"type": "text", "text": text})

        kwargs: dict = {
            "model": settings.caption_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
        }
        # Zhipu GLM thinking control; other OpenAI-compatible gateways reject it.
        if "bigmodel.cn" in settings.caption_base_url:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        resp = client.chat.completions.create(**kwargs)
        message = resp.choices[0].message.content or ""
        return message.strip()


class RaisingCaptionAdapter:
    """Used when Zhipu key is empty — skip retries and degrade immediately."""

    model_name = ""
    skip_caption = True

    def caption(self, frames: list[Path], ocr_text: str) -> str:
        raise RuntimeError("zhipu_api_key not configured")
