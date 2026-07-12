"""landslide_jobs.total_stages default: 3 -> 2 (pre/post preprocessing now run
as one concurrent stage instead of two sequential ones)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-12

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("landslide_jobs", "total_stages", server_default="2")


def downgrade() -> None:
    op.alter_column("landslide_jobs", "total_stages", server_default="3")
