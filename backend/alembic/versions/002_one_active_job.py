"""one active analysis job per video

Revision ID: 002
Revises: 001
Create Date: 2026-08-25 13:50:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX uq_analysis_jobs_one_active_per_video
        ON analysis_jobs (video_id)
        WHERE status IN ('queued', 'processing')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_analysis_jobs_one_active_per_video")
