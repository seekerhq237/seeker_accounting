from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from seeker_accounting.config.paths import ensure_runtime_directories
from seeker_accounting.config.settings import load_settings
from seeker_accounting.db.model_registry import target_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = config.attributes.get("seeker_database_url")
if database_url is None:
    settings = load_settings()
    ensure_runtime_directories(settings.runtime_paths)
    database_url = settings.database_url
config.set_main_option("sqlalchemy.url", str(database_url))

_IGNORED_COLUMN_DIFFS = {
    ("purchase_order_lines", "discount_amount"),
    ("tax_returns", "credit_brought_forward"),
    ("tax_returns", "withholding_vat_amount"),
    ("vat_capital_goods_register", "created_at"),
    ("vat_capital_goods_register", "updated_at"),
    ("vat_period_locks", "created_at"),
    ("vat_period_locks", "updated_at"),
}


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    if type_ in {"index", "unique_constraint", "foreign_key_constraint"}:
        return False
    if type_ == "column":
        table = getattr(object_, "table", None)
        table_name = getattr(table, "name", None)
        if table_name is not None and name is not None:
            return (table_name, name) not in _IGNORED_COLUMN_DIFFS
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=False,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=False,
            include_object=include_object,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
