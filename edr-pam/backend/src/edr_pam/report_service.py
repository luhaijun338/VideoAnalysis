from __future__ import annotations

from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from edr_pam.models import Alert, EvidenceChainItem
from edr_pam.schemas import ChainItemOut, ReportOut, ReportRequest

_LEVEL_LABEL = {"high": "高", "mid": "中", "low": "低"}


def _timeline_from_alert(alert: Alert) -> list[ChainItemOut]:
    rows = sorted(alert.timeline, key=lambda x: x.sort_order)
    return [
        ChainItemOut(src=t.src, time=t.time, title=t.title, description=t.description)
        for t in rows
        if t.src in ("pam", "edr")
    ]


def _timeline_from_chain_items(items: list[EvidenceChainItem]) -> list[ChainItemOut]:
    return [
        ChainItemOut(src=i.src, time=i.time, title=i.title, description=i.description)
        for i in items
    ]


def _build_summary(alert: Alert) -> str:
    discovered = alert.discovered_at.strftime("%Y-%m-%d %H:%M:%S")
    level = _LEVEL_LABEL.get(alert.level, alert.level)
    return (
        f"{discovered}，账号 {alert.account}（来源 {alert.src_ip}）触发告警「{alert.name}」。"
        f"目标资产 {alert.asset}，风险分 {alert.risk}，等级：{level}。"
        f"{alert.description}"
    )


def _build_impact(alert: Alert) -> str:
    status_map = {
        "pending": "待处置",
        "processing": "处置中",
        "done": "已处置",
        "ignored": "已忽略",
    }
    status = status_map.get(alert.status, alert.status)
    model_name = alert.model.name if alert.model else f"模型{alert.model_id}"
    return (
        f"涉及资产：{alert.asset}；涉及账号：{alert.account}；"
        f"分析模型：{model_name}；告警编号：{alert.id}；"
        f"发现时间：{alert.discovered_at.strftime('%Y-%m-%d %H:%M:%S')}；"
        f"当前状态：{status}；关联告警共检索到同条件记录。"
    )


def _build_recommendations(alert: Alert) -> list[str]:
    recs: list[str] = []
    if alert.risk >= 80:
        recs.append(f"对 {alert.account} 账号执行账号即时冻结联动，强制中断 {alert.asset} 活跃会话")
    elif alert.risk >= 60:
        recs.append(f"对 {alert.account} 触发增强认证并临时降权")
    recs.append(f"核查来源 IP {alert.src_ip} 是否被攻陷或存在隧道直连")
    recs.append(f"对该账号近 30 天登录与操作行为进行基线比对")
    if alert.model_id == 1:
        recs.append("将 RDP/SSH 直连策略收敛至 PAM 单点入口")
    elif alert.model_id == 2:
        recs.append("轮换涉事资产本地管理员密码并标记为已泄露待核查")
    elif alert.model_id == 3:
        recs.append("排查跨资产横向移动路径并收紧跨机跳转授权")
    else:
        recs.append("复核特权账号行为基线并更新异常阈值")
    return recs


def generate_audit_report(session: Session, body: ReportRequest) -> ReportOut:
    stmt = (
        select(Alert)
        .options(
            joinedload(Alert.model),
            joinedload(Alert.timeline),
        )
        .order_by(Alert.risk.desc(), Alert.discovered_at.desc())
    )

    if body.account.strip():
        stmt = stmt.where(Alert.account == body.account.strip())
    if body.asset.strip():
        asset = body.asset.strip()
        stmt = stmt.where(or_(Alert.asset == asset, Alert.asset.contains(asset)))
    if body.date_from:
        stmt = stmt.where(func.date(Alert.discovered_at) >= body.date_from)
    if body.date_to:
        stmt = stmt.where(func.date(Alert.discovered_at) <= body.date_to)

    alerts = session.scalars(stmt).unique().all()
    if not alerts:
        raise HTTPException(404, "未找到符合筛选条件的告警记录，请调整时间范围、账号或资产后重试")

    primary = alerts[0]
    timeline = _timeline_from_alert(primary)
    if not timeline:
        fallback = session.scalars(
            select(EvidenceChainItem).order_by(EvidenceChainItem.sort_order)
        ).all()
        timeline = _timeline_from_chain_items(fallback)

    now = datetime.now()
    report_id = f"RPT-{now.strftime('%Y-%m%d')}-{primary.id.split('-')[-1]}"

    recommendations = _build_recommendations(primary)
    if len(alerts) > 1:
        recommendations.append(f"同条件共命中 {len(alerts)} 条告警，建议一并复核关联账号与资产")

    return ReportOut(
        report_id=report_id,
        generated_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        account=primary.account,
        asset=primary.asset,
        alert_id=primary.id,
        alert_name=primary.name,
        risk=primary.risk,
        level=primary.level,
        summary=_build_summary(primary),
        impact=_build_impact(primary),
        recommendations="\n".join(f"{i + 1}. {text}" for i, text in enumerate(recommendations)),
        timeline=timeline,
        matched_alert_count=len(alerts),
    )
