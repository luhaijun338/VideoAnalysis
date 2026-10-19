from pathlib import Path

from video_analysis.adapters.fake import FakeCaptionAdapter, FakeEmbedAdapter, FakeOcrAdapter
from video_analysis.fts import tokenize_fts


def test_tokenize_keeps_export_keywords() -> None:
    tokens = tokenize_fts("点击导出", "客户名单.xlsx")
    assert "客户" in tokens or "客户名单" in tokens
    assert "导出" in tokens


def test_fake_embed_is_1024_and_deterministic() -> None:
    emb = FakeEmbedAdapter()
    a = emb.embed("导出 客户名单")
    b = emb.embed("导出 客户名单")
    assert len(a) == 1024
    assert a == b


def test_fake_embed_different_texts_have_lower_cosine() -> None:
    emb = FakeEmbedAdapter()
    a = emb.embed("导出 客户名单")
    b = emb.embed("导入 供应商目录")
    dot = sum(x * y for x, y in zip(a, b))
    assert dot < 0.99


def test_fake_ocr_mapping() -> None:
    adapter = FakeOcrAdapter({"frame.jpg": "导出按钮"})
    assert adapter.recognize(Path("frame.jpg")) == "导出按钮"
    assert adapter.recognize(Path("other.jpg")) == ""


def test_fake_caption_with_ocr() -> None:
    adapter = FakeCaptionAdapter(text="执行了界面操作")
    result = adapter.caption([Path("a.jpg")], "客户名单")
    assert result == "执行了界面操作：客户名单"


def test_fake_caption_fail_raises() -> None:
    adapter = FakeCaptionAdapter(fail=True)
    try:
        adapter.caption([], "")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
