"""add unique content hash on videos

Revision ID: 003
Revises: 002
Create Date: 2026-08-25 16:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("content_sha256", sa.String(length=64), nullable=True))
    op.create_index("ix_videos_content_sha256", "videos", ["content_sha256"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_videos_content_sha256", table_name="videos")
    op.drop_column("videos", "content_sha256")
