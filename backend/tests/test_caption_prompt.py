from video_analysis.adapters.caption_zhipu import CAPTION_SYSTEM_PROMPT


def test_caption_prompt_requires_operation_log_style() -> None:
    p = CAPTION_SYSTEM_PROMPT
    assert "操作" in p or "动作" in p
    assert "OCR" in p or "界面" in p
    assert "时间" in p or "时间戳" in p  # ban timestamps
    assert "Markdown" in p or "markdown" in p.lower()
    assert "意图" in p
