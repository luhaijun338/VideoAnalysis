from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from edr_pam.schemas import ReportOut

pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

_FONT = "STSong-Light"
_LEVEL_LABEL = {"high": "高风险", "mid": "中风险", "low": "低风险"}


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    safe = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
    return Paragraph(safe, style)


def render_report_pdf(report: ReportOut) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=report.report_id,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CnTitle",
        parent=styles["Title"],
        fontName=_FONT,
        fontSize=16,
        leading=22,
        spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "CnMeta",
        parent=styles["Normal"],
        fontName=_FONT,
        fontSize=9,
        textColor=colors.HexColor("#606266"),
        spaceAfter=12,
    )
    h_style = ParagraphStyle(
        "CnH",
        parent=styles["Heading2"],
        fontName=_FONT,
        fontSize=12,
        leading=18,
        spaceBefore=10,
        spaceAfter=6,
        textColor=colors.HexColor("#303133"),
    )
    body_style = ParagraphStyle(
        "CnBody",
        parent=styles["Normal"],
        fontName=_FONT,
        fontSize=10,
        leading=16,
        spaceAfter=8,
    )

    story: list = []
    story.append(_p("特权访问行为审计报告", title_style))
    story.append(
        _p(
            f"Report ID: {report.report_id} · 生成时间 {report.generated_at}",
            meta_style,
        )
    )
    story.append(
        _p(
            f"涉事账号：{report.account} · 目标资产：{report.asset} · "
            f"告警：{report.alert_id} · 风险分 {report.risk}（{_LEVEL_LABEL.get(report.level, report.level)}）",
            meta_style,
        )
    )

    story.append(_p("一、事件概述", h_style))
    story.append(_p(report.summary, body_style))

    story.append(_p("二、攻击链时间线", h_style))
    rows = [["时间", "来源", "事件", "详情"]]
    for item in report.timeline:
        src = "系统事件" if item.src == "edr" else "PAM"
        rows.append([item.time, src, item.title, item.description])

    table = Table(rows, colWidths=[22 * mm, 22 * mm, 48 * mm, 78 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f7fa")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#606266")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ebeef5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 8))

    story.append(_p("三、影响范围", h_style))
    story.append(_p(report.impact, body_style))

    story.append(_p("四、处置建议", h_style))
    story.append(_p(report.recommendations, body_style))

    doc.build(story)
    return buf.getvalue()
