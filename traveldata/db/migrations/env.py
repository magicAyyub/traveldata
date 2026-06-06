from __future__ import annotations

from logging.config import fileConfig

import geoalchemy2  # noqa: F401  (register spatial types)
from alembic import context
from sqlalchemy import engine_from_config, pool

from traveldata.config import settings
from traveldata.db.base import Base
from traveldata.db import models  # noqa: F401  (register tables on metadata)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# GeoAlchemy2 hooks so future --autogenerate handles geography columns cleanly.
# Guarded: upgrade/downgrade don't need them, only autogenerate does.
_geo_kw: dict = {}
try:
    from geoalchemy2 import alembic_helpers

    _geo_kw.update(
        include_object=alembic_helpers.include_object,
        render_item=alembic_helpers.render_item,
        process_revision_directives=alembic_helpers.writer,
    )
except Exception:
    pass


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_geo_kw,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, **_geo_kw)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()