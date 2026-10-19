"""init schema

Revision ID: 001
Revises:
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("hit7", sa.Integer(), nullable=False),
        sa.Column("fp_rate", sa.String(length=16), nullable=False),
        sa.Column("disposed_rate", sa.String(length=16), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("scene", sa.Text(), nullable=False),
        sa.Column("edr_fields", postgresql.JSONB(), nullable=False),
        sa.Column("pam_fields", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("risk", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(length=64), nullable=False),
        sa.Column("asset", sa.String(length=128), nullable=False),
        sa.Column("src_ip", sa.String(length=64), nullable=False),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["analysis_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alert_timeline",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(length=32), nullable=False),
        sa.Column("src", sa.String(length=16), nullable=False),
        sa.Column("time", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("badge", sa.String(length=128), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alert_evidence",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(length=32), nullable=False),
        sa.Column("src", sa.String(length=16), nullable=False),
        sa.Column("field_name", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "alert_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(length=32), nullable=False),
        sa.Column("time", sa.String(length=16), nullable=False),
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trend_days",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("day_label", sa.String(length=16), nullable=False),
        sa.Column("day_date", sa.Date(), nullable=False),
        sa.Column("alert_count", sa.Integer(), nullable=False),
        sa.Column("high_count", sa.Integer(), nullable=False),
        sa.Column("dispose_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "linkage_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("triggers", postgresql.JSONB(), nullable=False),
        sa.Column("actions", postgresql.JSONB(), nullable=False),
        sa.Column("recovery_condition", sa.Text(), nullable=False),
        sa.Column("icon_color", sa.String(length=16), nullable=False),
        sa.Column("last_trigger_label", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "disposal_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("disposed_at", sa.DateTime(), nullable=False),
        sa.Column("alert_id", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("operator", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "evidence_chain",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("src", sa.String(length=16), nullable=False),
        sa.Column("time", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("evidence_chain")
    op.drop_table("disposal_records")
    op.drop_table("linkage_rules")
    op.drop_table("trend_days")
    op.drop_table("alert_logs")
    op.drop_table("alert_evidence")
    op.drop_table("alert_timeline")
    op.drop_table("alerts")
    op.drop_table("analysis_models")
