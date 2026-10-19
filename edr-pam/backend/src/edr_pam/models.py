from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AnalysisModel(Base):
    __tablename__ = "analysis_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hit7: Mapped[int] = mapped_column(Integer, default=0)
    fp_rate: Mapped[str] = mapped_column(String(16), default="0%")
    disposed_rate: Mapped[str] = mapped_column(String(16), default="0%")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    scene: Mapped[str] = mapped_column(Text, default="")
    edr_fields: Mapped[list] = mapped_column(JSON, default=list)
    pam_fields: Mapped[list] = mapped_column(JSON, default=list)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    model_id: Mapped[int] = mapped_column(ForeignKey("analysis_models.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    risk: Mapped[int] = mapped_column(Integer, nullable=False)
    account: Mapped[str] = mapped_column(String(64), nullable=False)
    asset: Mapped[str] = mapped_column(String(128), nullable=False)
    src_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    description: Mapped[str] = mapped_column(Text, default="")

    model: Mapped[AnalysisModel] = relationship()
    timeline: Mapped[list[AlertTimeline]] = relationship(back_populates="alert", cascade="all, delete-orphan")
    evidence: Mapped[list[AlertEvidence]] = relationship(back_populates="alert", cascade="all, delete-orphan")
    logs: Mapped[list[AlertLog]] = relationship(back_populates="alert", cascade="all, delete-orphan")


class AlertTimeline(Base):
    __tablename__ = "alert_timeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    src: Mapped[str] = mapped_column(String(16), nullable=False)
    time: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    badge: Mapped[str | None] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    alert: Mapped[Alert] = relationship(back_populates="timeline")


class AlertEvidence(Base):
    __tablename__ = "alert_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    src: Mapped[str] = mapped_column(String(16), nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    alert: Mapped[Alert] = relationship(back_populates="evidence")


class AlertLog(Base):
    __tablename__ = "alert_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    time: Mapped[str] = mapped_column(String(16), nullable=False)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    alert: Mapped[Alert] = relationship(back_populates="logs")


class TrendDay(Base):
    __tablename__ = "trend_days"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day_label: Mapped[str] = mapped_column(String(16), nullable=False)
    day_date: Mapped[date] = mapped_column(Date, nullable=False)
    alert_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    dispose_count: Mapped[int] = mapped_column(Integer, default=0)


class LinkageRule(Base):
    __tablename__ = "linkage_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    subtitle: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    triggers: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    recovery_condition: Mapped[str] = mapped_column(Text, default="")
    icon_color: Mapped[str] = mapped_column(String(16), default="blue")
    last_trigger_label: Mapped[str] = mapped_column(String(64), default="")


class DisposalRecord(Base):
    __tablename__ = "disposal_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disposed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    alert_id: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    operator: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)


class EvidenceChainItem(Base):
    __tablename__ = "evidence_chain"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src: Mapped[str] = mapped_column(String(16), nullable=False)
    time: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
