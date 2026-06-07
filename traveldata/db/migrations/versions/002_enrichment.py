"""enrichment columns

Revision ID: 0002_enrichment
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_enrichment"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("poi", sa.Column("pageviews_30d", sa.Integer()))
    op.add_column("poi", sa.Column("sitelink_count", sa.Integer()))
    op.add_column("poi", sa.Column("wikipedia_title", sa.Text()))
    op.add_column("poi", sa.Column("enriched_at", sa.TIMESTAMP()))


def downgrade() -> None:
    for c in ("enriched_at", "wikipedia_title", "sitelink_count", "pageviews_30d"):
        op.drop_column("poi", c)