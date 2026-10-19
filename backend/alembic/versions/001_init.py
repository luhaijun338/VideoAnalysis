"""init schema with pgvector segments

Revision ID: 001
Revises:
Create Date: 2026-03-25 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_segments", sa.Integer(), nullable=True),
        sa.Column("done_segments", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("last_segment_index", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analysis_jobs_video_id", "analysis_jobs", ["video_id"])

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("t_start_ms", sa.Integer(), nullable=False),
        sa.Column("t_end_ms", sa.Integer(), nullable=False),
        sa.Column("keyframe_path", sa.String(1024), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("caption_degraded", sa.Boolean(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("fts", postgresql.TSVECTOR(), nullable=True),
        sa.Column("model_caption", sa.String(128), nullable=False),
        sa.Column("model_embed", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_segments_video_id", "segments", ["video_id"])
    op.create_index("ix_segments_video_t_start", "segments", ["video_id", "t_start_ms"])
    op.execute(
        "CREATE INDEX ix_segments_embedding ON segments USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_segments_fts ON segments USING gin (fts)")


def downgrade() -> None:
    op.drop_index("ix_segments_fts", table_name="segments")
    op.drop_index("ix_segments_embedding", table_name="segments")
    op.drop_index("ix_segments_video_t_start", table_name="segments")
    op.drop_index("ix_segments_video_id", table_name="segments")
    op.drop_table("segments")
    op.drop_index("ix_analysis_jobs_video_id", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")
    op.drop_table("videos")
