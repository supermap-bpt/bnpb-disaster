"""add stage tracking columns to landslide_jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("landslide_jobs", sa.Column("stage", sa.String(), nullable=True))
    op.add_column(
        "landslide_jobs",
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "landslide_jobs",
        sa.Column("total_stages", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("landslide_jobs", "total_stages")
    op.drop_column("landslide_jobs", "stage_index")
    op.drop_column("landslide_jobs", "stage")
