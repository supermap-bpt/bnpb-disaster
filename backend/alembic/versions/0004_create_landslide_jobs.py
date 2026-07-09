"""create landslide_jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "landslide_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pre_satellite_id", UUID(as_uuid=True), nullable=False),
        sa.Column("post_satellite_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("threshold_db", sa.String(), nullable=False, server_default="-2.0"),
        sa.Column("result_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("landslide_jobs")
