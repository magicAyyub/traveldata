"""is_destination flag

Revision ID: 0003_destination_flag
Revises: 0002_enrichment
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_destination_flag"
down_revision = "0002_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("poi", sa.Column("is_destination", sa.Boolean(),
                                   server_default=sa.true(), nullable=False))


def downgrade() -> None:
    op.drop_column("poi", "is_destination")