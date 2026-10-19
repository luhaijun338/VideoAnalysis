from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from edr_pam.models import (
    Alert,
    AlertEvidence,
    AlertLog,
    AlertTimeline,
    AnalysisModel,
    DisposalRecord,
    EvidenceChainItem,
    LinkageRule,
    TrendDay,
)
from edr_pam.seed_data import (
    ALERTS,
    CHAIN_DEMO,
    DETAIL,
    DISPOSALS,
    LINKAGE_RULES,
    MODELS,
    TREND,
)


def seed_if_empty(session: Session) -> bool:
    if session.scalar(select(AnalysisModel.id).limit(1)):
        return False

    for m in MODELS:
        session.add(
            AnalysisModel(
                id=m["id"],
                name=m["name"],
                description=m["description"],
                enabled=m["enabled"],
                hit7=m["hit7"],
                fp_rate=m["fp_rate"],
                disposed_rate=m["disposed_rate"],
                steps=m["steps"],
                scene=m["scene"],
                edr_fields=m["edr_fields"],
                pam_fields=m["pam_fields"],
            )
        )

    for a in ALERTS:
        session.add(Alert(**a))

    for alert_id, detail in DETAIL.items():
        for i, t in enumerate(detail["timeline"]):
            session.add(
                AlertTimeline(
                    alert_id=alert_id,
                    src=t["src"],
                    time=t["time"],
                    title=t["title"],
                    description=t["description"],
                    badge=t.get("badge"),
                    sort_order=i,
                )
            )
        for i, e in enumerate(detail["evidence"]):
            session.add(
                AlertEvidence(
                    alert_id=alert_id,
                    src=e["src"],
                    field_name=e["field_name"],
                    value=e["value"],
                    sort_order=i,
                )
            )
        for i, log in enumerate(detail["logs"]):
            session.add(
                AlertLog(
                    alert_id=alert_id,
                    time=log["time"],
                    operator=log["operator"],
                    operation=log["operation"],
                    sort_order=i,
                )
            )

    for t in TREND:
        session.add(TrendDay(**t))

    for d in DISPOSALS:
        session.add(DisposalRecord(**d))

    for rule in LINKAGE_RULES:
        session.add(LinkageRule(**rule))

    for i, c in enumerate(CHAIN_DEMO):
        session.add(EvidenceChainItem(**c, sort_order=i))

    session.flush()
    return True
