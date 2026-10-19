from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ModelOut(BaseModel):
    id: int
    name: str
    description: str
    enabled: bool
    hit7: int
    fp_rate: str
    disposed_rate: str
    steps: list[str]
    scene: str
    edr_fields: list[str]
    pam_fields: list[str]


class AlertOut(BaseModel):
    id: str
    name: str
    model_id: int
    model_name: str | None = None
    level: str
    risk: int
    account: str
    asset: str
    src_ip: str
    discovered_at: datetime
    status: str
    description: str


class TimelineOut(BaseModel):
    src: str
    time: str
    title: str
    description: str
    badge: str | None = None


class EvidenceOut(BaseModel):
    src: str
    field_name: str
    value: str


class LogOut(BaseModel):
    time: str
    operator: str
    operation: str


class AlertDetailOut(AlertOut):
    timeline: list[TimelineOut]
    evidence: list[EvidenceOut]
    logs: list[LogOut]


class TrendPointOut(BaseModel):
    day_label: str
    alert_count: int
    high_count: int
    dispose_count: int


class LevelDistributionOut(BaseModel):
    high: int
    mid: int
    low: int
    total: int


class ModelHitOut(BaseModel):
    id: int
    name: str
    hit7: int
    pct: int


class TopAccountOut(BaseModel):
    account: str
    risk: int
    model_label: str
    status: str


class OverviewOut(BaseModel):
    today_alerts: int
    today_alerts_delta: int
    high_risk_accounts: int
    high_risk_pending: int
    today_disposals: int
    auto_disposals: int
    models_running: int
    models_total: int
    false_positive_rate: str
    trend: list[TrendPointOut]
    level_distribution: LevelDistributionOut
    model_hits: list[ModelHitOut]
    top_accounts: list[TopAccountOut]
    latest_alerts: list[AlertOut]


class LinkageOut(BaseModel):
    id: int
    name: str
    slug: str
    severity: str
    subtitle: str
    enabled: bool
    triggers: list[str]
    actions: list[str]
    recovery_condition: str
    icon_color: str
    last_trigger_label: str


class DisposalOut(BaseModel):
    id: int
    disposed_at: datetime
    alert_id: str
    action: str
    target: str
    operator: str
    result: str


class ChainItemOut(BaseModel):
    src: str
    time: str
    title: str
    description: str


class ReportRequest(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    account: str = "zhang_wj"
    asset: str = "BSS-DB-01"


class ReportOut(BaseModel):
    report_id: str
    generated_at: str
    account: str
    asset: str
    alert_id: str
    alert_name: str
    risk: int
    level: str
    summary: str
    impact: str
    recommendations: str
    timeline: list[ChainItemOut]
    matched_alert_count: int = 1


class DisposeBody(BaseModel):
    action: Literal["账号即时冻结", "密码自动轮换", "增强认证", "标记忽略"]


class ToggleBody(BaseModel):
    enabled: bool


class AlertListOut(BaseModel):
    total: int
    pending: int
    items: list[AlertOut]
