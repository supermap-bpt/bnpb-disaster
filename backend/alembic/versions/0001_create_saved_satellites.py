"""create saved_satellites

Revision ID: 0001
Revises:
Create Date: 2026-07-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')
    op.create_table(
        "saved_satellites",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("satellite_name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("directory_path", sa.String(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("product", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("instrument", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("platform", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("other", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("download_single_file", sa.String(), nullable=False),
        sa.Column("preview", sa.String(), nullable=True),
        sa.Column("footprint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mission", sa.String(), nullable=False),
        sa.Column("instrument_name", sa.String(), nullable=True),
        sa.Column("polarisation", sa.String(), nullable=False),
        sa.Column("sensing_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("size", sa.String(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
    )


def downgrade() -> None:
    op.drop_table("saved_satellites")
