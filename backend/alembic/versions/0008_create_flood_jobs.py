"""create flood_jobs table

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flood_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("satellite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_stages", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("threshold_sigma0", sa.String(), nullable=False, server_default="0.0137"),
        sa.Column("result_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("flood_jobs")
