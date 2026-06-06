"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def _geom():
    # spatial_index=False: we create the GIST index explicitly below.
    return geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "place",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("wikidata_qid", sa.Text(), unique=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("names", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("geom", _geom()),
        sa.Column("parent_place_id", UUID, sa.ForeignKey("place.id")),
        sa.Column("wikivoyage_title", sa.Text()),
        sa.Column("descriptions", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("practical_info", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_place_geom", "place", ["geom"], postgresql_using="gist")

    op.create_table(
        "poi",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("wikidata_qid", sa.Text()),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("names", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("geom", _geom(), nullable=False),
        sa.Column("geohash", sa.String(12)),
        sa.Column("place_id", UUID, sa.ForeignKey("place.id")),
        sa.Column("country_code", sa.String(2)),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("raw_kinds", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("short_description", sa.Text()),
        sa.Column("descriptions", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("images", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_xids", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("field_provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("first_seen_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_poi_geom", "poi", ["geom"], postgresql_using="gist")
    op.create_index("ix_poi_wikidata_qid", "poi", ["wikidata_qid"])
    op.create_index("ix_poi_geohash", "poi", ["geohash"])

    op.create_table(
        "source_record",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("poi_id", UUID, sa.ForeignKey("poi.id")),
        sa.Column("place_id", UUID, sa.ForeignKey("place.id")),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(8)),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("fetched_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source", "source_id", "lang", name="uq_source_record_natural_key"),
    )

    op.create_table(
        "poi_link",
        sa.Column("poi_id", UUID, sa.ForeignKey("poi.id"), primary_key=True),
        sa.Column("source_record_id", UUID, sa.ForeignKey("source_record.id"), primary_key=True),
        sa.Column("match_method", sa.String(32)),
        sa.Column("match_score", sa.Float()),
    )

    op.create_table(
        "poi_score",
        sa.Column("poi_id", UUID, sa.ForeignKey("poi.id"), primary_key=True),
        sa.Column("model_version", sa.String(32), primary_key=True),
        sa.Column("popularity", sa.Float()),
        sa.Column("content_richness", sa.Float()),
        sa.Column("activity_score", sa.Float()),
        sa.Column("hidden_gem_score", sa.Float()),
        sa.Column("components", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("scored_at", sa.TIMESTAMP(), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("poi_score")
    op.drop_table("poi_link")
    op.drop_table("source_record")
    op.drop_index("ix_poi_geohash", table_name="poi")
    op.drop_index("ix_poi_wikidata_qid", table_name="poi")
    op.drop_index("idx_poi_geom", table_name="poi")
    op.drop_table("poi")
    op.drop_index("idx_place_geom", table_name="place")
    op.drop_table("place")