"""landslide_jobs.total_stages default: 2 -> 7 (preprocessing split into 6
per-operator stages instead of 1 combined parallel stage)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-12

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("landslide_jobs", "total_stages", server_default="7")


def downgrade() -> None:
    op.alter_column("landslide_jobs", "total_stages", server_default="2")
