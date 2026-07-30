from logging.config import fileConfig

from alembic import context

from app.config import settings
from app.db import Base, engine
from app import models  # noqa: F401 - enregistre les tables sur Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:
    """Ignore les tables PostGIS (tiger, topology…) et la colonne tsv
    (générée en SQL brut, volontairement non mappée dans l'ORM)."""
    if type_ == "table":
        return name in target_metadata.tables
    if type_ == "column" and name == "tsv":
        return False
    if type_ == "index" and name == "ix_document_tsv":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
