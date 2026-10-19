from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from edr_pam.config import settings
from edr_pam.db import get_session
from edr_pam.models import (
    Alert,
    AlertLog,
    AnalysisModel,
    DisposalRecord,
    EvidenceChainItem,
    LinkageRule,
    TrendDay,
)
from edr_pam.schemas import (
    AlertDetailOut,
    AlertListOut,
    AlertOut,
    ChainItemOut,
    DisposeBody,
    DisposalOut,
    EvidenceOut,
    LevelDistributionOut,
    LinkageOut,
    LogOut,
    ModelHitOut,
    ModelOut,
    OverviewOut,
    ReportOut,
    ReportRequest,
    TimelineOut,
    ToggleBody,
    TopAccountOut,
    TrendPointOut,
)
from edr_pam.pdf_export import render_report_pdf
from edr_pam.report_service import generate_audit_report
from edr_pam.seed import seed_if_empty

app = FastAPI(title="EDR-PAM 关联分析")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _alert_out(alert: Alert) -> AlertOut:
    return AlertOut(
        id=alert.id,
        name=alert.name,
        model_id=alert.model_id,
        model_name=alert.model.name if alert.model else None,
        level=alert.level,
        risk=alert.risk,
        account=alert.account,
        asset=alert.asset,
        src_ip=alert.src_ip,
        discovered_at=alert.discovered_at,
        status=alert.status,
        description=alert.description,
    )


@app.on_event("startup")
def on_startup() -> None:
    from edr_pam.db import SessionLocal
    from edr_pam.models import Base
    from edr_pam.db import engine

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_if_empty(session)
        session.commit()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "edr-pam"}


@app.get("/api/overview", response_model=OverviewOut)
def get_overview(session: Annotated[Session, Depends(get_session)]) -> OverviewOut:
    today = date(2026, 8, 27)
    yesterday = date(2026, 8, 26)

    today_alerts = session.scalar(
        select(func.count()).select_from(Alert).where(func.date(Alert.discovered_at) == today)
    ) or 0
    yesterday_alerts = session.scalar(
        select(func.count()).select_from(Alert).where(func.date(Alert.discovered_at) == yesterday)
    ) or 0

    high_risk_accounts = session.scalar(
        select(func.count(func.distinct(Alert.account))).where(Alert.risk >= 80)
    ) or 0
    high_risk_pending = session.scalar(
        select(func.count(func.distinct(Alert.account))).where(
            Alert.risk >= 80, Alert.status == "pending"
        )
    ) or 0

    today_disposals = session.scalar(
        select(func.count())
        .select_from(DisposalRecord)
        .where(func.date(DisposalRecord.disposed_at) == today)
    ) or 0
    auto_disposals = session.scalar(
        select(func.count())
        .select_from(DisposalRecord)
        .where(func.date(DisposalRecord.disposed_at) == today, DisposalRecord.operator == "系统自动")
    ) or 0

    models = session.scalars(select(AnalysisModel)).all()
    models_running = sum(1 for m in models if m.enabled)

    trend_rows = session.scalars(select(TrendDay).order_by(TrendDay.day_date)).all()
    trend = [
        TrendPointOut(
            day_label=r.day_label,
            alert_count=r.alert_count,
            high_count=r.high_count,
            dispose_count=r.dispose_count,
        )
        for r in trend_rows
    ]

    level_counts = {"high": 0, "mid": 0, "low": 0}
    for level, cnt in session.execute(
        select(Alert.level, func.count())
        .where(func.date(Alert.discovered_at) == today)
        .group_by(Alert.level)
    ):
        level_counts[level] = cnt

    total_hits = sum(m.hit7 for m in models)
    model_hits = [
        ModelHitOut(
            id=m.id,
            name=m.name,
            hit7=m.hit7,
            pct=round(m.hit7 / total_hits * 100) if total_hits else 0,
        )
        for m in models
    ]

    top_rows = session.scalars(
        select(Alert)
        .options(joinedload(Alert.model))
        .order_by(Alert.risk.desc())
        .limit(5)
    ).unique().all()
    top_accounts = [
        TopAccountOut(
            account=a.account,
            risk=a.risk,
            model_label=f"模型{a.model_id}",
            status=a.status,
        )
        for a in top_rows
    ]

    latest = session.scalars(
        select(Alert)
        .options(joinedload(Alert.model))
        .order_by(Alert.discovered_at.desc())
        .limit(5)
    ).unique().all()

    return OverviewOut(
        today_alerts=today_alerts,
        today_alerts_delta=today_alerts - yesterday_alerts,
        high_risk_accounts=high_risk_accounts,
        high_risk_pending=high_risk_pending,
        today_disposals=today_disposals,
        auto_disposals=auto_disposals,
        models_running=models_running,
        models_total=len(models),
        false_positive_rate="8.2%",
        trend=trend,
        level_distribution=LevelDistributionOut(
            high=level_counts["high"],
            mid=level_counts["mid"],
            low=level_counts["low"],
            total=today_alerts,
        ),
        model_hits=model_hits,
        top_accounts=top_accounts,
        latest_alerts=[_alert_out(a) for a in latest],
    )


@app.get("/api/alerts", response_model=AlertListOut)
def list_alerts(
    session: Annotated[Session, Depends(get_session)],
    date_from: date | None = None,
    date_to: date | None = None,
    model_id: int | None = None,
    level: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> AlertListOut:
    stmt = select(Alert).options(joinedload(Alert.model)).order_by(Alert.discovered_at.desc())
    if date_from:
        stmt = stmt.where(func.date(Alert.discovered_at) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(Alert.discovered_at) <= date_to)
    if model_id:
        stmt = stmt.where(Alert.model_id == model_id)
    if level:
        stmt = stmt.where(Alert.level == level)
    if status:
        stmt = stmt.where(Alert.status == status)
    if q:
        kw = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Alert.account).like(kw),
                func.lower(Alert.asset).like(kw),
                func.lower(Alert.src_ip).like(kw),
                func.lower(Alert.name).like(kw),
            )
        )

    alerts = session.scalars(stmt).unique().all()
    total = session.scalar(select(func.count()).select_from(Alert)) or 0
    pending = session.scalar(
        select(func.count()).select_from(Alert).where(Alert.status == "pending")
    ) or 0
    return AlertListOut(
        total=total,
        pending=pending,
        items=[_alert_out(a) for a in alerts],
    )


@app.get("/api/alerts/{alert_id}", response_model=AlertDetailOut)
def get_alert(alert_id: str, session: Annotated[Session, Depends(get_session)]) -> AlertDetailOut:
    alert = session.scalar(
        select(Alert)
        .options(
            joinedload(Alert.model),
            joinedload(Alert.timeline),
            joinedload(Alert.evidence),
            joinedload(Alert.logs),
        )
        .where(Alert.id == alert_id)
    )
    if not alert:
        raise HTTPException(404, "告警不存在")

    base = _alert_out(alert)
    fallback_id = "A-20260827-017"
    if not alert.timeline and alert_id != fallback_id:
        fallback = session.scalar(
            select(Alert)
            .options(
                joinedload(Alert.timeline),
                joinedload(Alert.evidence),
                joinedload(Alert.logs),
            )
            .where(Alert.id == fallback_id)
        )
        if fallback:
            alert.timeline = fallback.timeline
            alert.evidence = fallback.evidence
            if not alert.logs:
                alert.logs = fallback.logs

    timeline = sorted(alert.timeline, key=lambda x: x.sort_order)
    evidence = sorted(alert.evidence, key=lambda x: x.sort_order)
    logs = sorted(alert.logs, key=lambda x: x.sort_order)

    return AlertDetailOut(
        **base.model_dump(),
        timeline=[
            TimelineOut(
                src=t.src,
                time=t.time,
                title=t.title,
                description=t.description,
                badge=t.badge,
            )
            for t in timeline
        ],
        evidence=[
            EvidenceOut(src=e.src, field_name=e.field_name, value=e.value) for e in evidence
        ],
        logs=[LogOut(time=l.time, operator=l.operator, operation=l.operation) for l in logs],
    )


@app.post("/api/alerts/{alert_id}/dispose", response_model=AlertDetailOut)
def dispose_alert(
    alert_id: str,
    body: DisposeBody,
    session: Annotated[Session, Depends(get_session)],
) -> AlertDetailOut:
    alert = session.scalar(
        select(Alert)
        .options(joinedload(Alert.model))
        .where(Alert.id == alert_id)
    )
    if not alert:
        raise HTTPException(404, "告警不存在")
    if alert.status not in ("pending", "processing"):
        raise HTTPException(400, "该告警已处置或已忽略")

    if body.action == "标记忽略":
        alert.status = "ignored"
    else:
        alert.status = "processing"

    now = datetime.now()
    tm = now.strftime("%H:%M")
    session.add(
        AlertLog(
            alert_id=alert_id,
            time=tm,
            operator="admin（当前操作人）",
            operation=f"触发联动「{body.action}」：对 {alert.account} 执行处置",
            sort_order=999,
        )
    )
    session.flush()
    return get_alert(alert_id, session)


@app.get("/api/models", response_model=list[ModelOut])
def list_models(session: Annotated[Session, Depends(get_session)]) -> list[ModelOut]:
    models = session.scalars(select(AnalysisModel).order_by(AnalysisModel.id)).all()
    return [
        ModelOut(
            id=m.id,
            name=m.name,
            description=m.description,
            enabled=m.enabled,
            hit7=m.hit7,
            fp_rate=m.fp_rate,
            disposed_rate=m.disposed_rate,
            steps=m.steps,
            scene=m.scene,
            edr_fields=m.edr_fields,
            pam_fields=m.pam_fields,
        )
        for m in models
    ]


@app.patch("/api/models/{model_id}", response_model=ModelOut)
def toggle_model(
    model_id: int,
    body: ToggleBody,
    session: Annotated[Session, Depends(get_session)],
) -> ModelOut:
    model = session.get(AnalysisModel, model_id)
    if not model:
        raise HTTPException(404, "模型不存在")
    model.enabled = body.enabled
    session.flush()
    return ModelOut(
        id=model.id,
        name=model.name,
        description=model.description,
        enabled=model.enabled,
        hit7=model.hit7,
        fp_rate=model.fp_rate,
        disposed_rate=model.disposed_rate,
        steps=model.steps,
        scene=model.scene,
        edr_fields=model.edr_fields,
        pam_fields=model.pam_fields,
    )


@app.get("/api/linkages", response_model=list[LinkageOut])
def list_linkages(session: Annotated[Session, Depends(get_session)]) -> list[LinkageOut]:
    rules = session.scalars(select(LinkageRule).order_by(LinkageRule.id)).all()
    return [
        LinkageOut(
            id=r.id,
            name=r.name,
            slug=r.slug,
            severity=r.severity,
            subtitle=r.subtitle,
            enabled=r.enabled,
            triggers=r.triggers,
            actions=r.actions,
            recovery_condition=r.recovery_condition,
            icon_color=r.icon_color,
            last_trigger_label=r.last_trigger_label,
        )
        for r in rules
    ]


@app.patch("/api/linkages/{linkage_id}", response_model=LinkageOut)
def toggle_linkage(
    linkage_id: int,
    body: ToggleBody,
    session: Annotated[Session, Depends(get_session)],
) -> LinkageOut:
    rule = session.get(LinkageRule, linkage_id)
    if not rule:
        raise HTTPException(404, "联动规则不存在")
    rule.enabled = body.enabled
    session.flush()
    return LinkageOut(
        id=rule.id,
        name=rule.name,
        slug=rule.slug,
        severity=rule.severity,
        subtitle=rule.subtitle,
        enabled=rule.enabled,
        triggers=rule.triggers,
        actions=rule.actions,
        recovery_condition=rule.recovery_condition,
        icon_color=rule.icon_color,
        last_trigger_label=rule.last_trigger_label,
    )


@app.get("/api/disposals", response_model=list[DisposalOut])
def list_disposals(session: Annotated[Session, Depends(get_session)]) -> list[DisposalOut]:
    rows = session.scalars(
        select(DisposalRecord).order_by(DisposalRecord.disposed_at.desc())
    ).all()
    return [
        DisposalOut(
            id=r.id,
            disposed_at=r.disposed_at,
            alert_id=r.alert_id,
            action=r.action,
            target=r.target,
            operator=r.operator,
            result=r.result,
        )
        for r in rows
    ]


@app.get("/api/evidence/chain", response_model=list[ChainItemOut])
def get_evidence_chain(session: Annotated[Session, Depends(get_session)]) -> list[ChainItemOut]:
    items = session.scalars(
        select(EvidenceChainItem).order_by(EvidenceChainItem.sort_order)
    ).all()
    return [
        ChainItemOut(src=i.src, time=i.time, title=i.title, description=i.description)
        for i in items
    ]


@app.post("/api/evidence/report", response_model=ReportOut)
def generate_report(
    body: ReportRequest,
    session: Annotated[Session, Depends(get_session)],
) -> ReportOut:
    return generate_audit_report(session, body)


@app.post("/api/evidence/report/pdf")
def export_report_pdf(
    body: ReportRequest,
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    report = generate_audit_report(session, body)
    pdf_bytes = render_report_pdf(report)
    filename = f"{report.report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def main() -> None:
    import uvicorn

    uvicorn.run("edr_pam.api:app", host=settings.api_host, port=settings.api_port, reload=True)


if __name__ == "__main__":
    main()
