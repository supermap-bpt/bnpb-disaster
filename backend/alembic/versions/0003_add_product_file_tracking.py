"""add product_file_status and product_file_path to saved_satellites

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("saved_satellites", sa.Column("product_file_status", sa.String(), nullable=True))
    op.add_column("saved_satellites", sa.Column("product_file_path", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("saved_satellites", "product_file_path")
    op.drop_column("saved_satellites", "product_file_status")
