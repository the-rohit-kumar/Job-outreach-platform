"""Engine, session factory and declarative base."""
from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" not in url and "mode=memory" not in url:
            db_path = url.split("///", 1)[-1]
            if db_path and db_path != ":memory:":
                Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sync_columns() -> None:
    """Ensure any newly added model columns exist in existing database tables."""
    from sqlalchemy import inspect as sa_inspect, text

    try:
        inspector = sa_inspect(engine)
        with engine.begin() as conn:
            for table_name, table in Base.metadata.tables.items():
                if not inspector.has_table(table_name):
                    continue
                existing_cols = {c["name"] for c in inspector.get_columns(table_name)}
                for col in table.columns:
                    if col.name not in existing_cols:
                        col_type = col.type.compile(engine.dialect)
                        default_clause = ""
                        if col.default is not None and getattr(col.default, "is_scalar", False):
                            val = col.default.arg
                            if isinstance(val, str):
                                escaped = val.replace("'", "''")
                                default_clause = f" DEFAULT '{escaped}'"
                            elif isinstance(val, bool):
                                default_clause = f" DEFAULT {1 if val else 0}"
                            elif isinstance(val, (int, float)):
                                default_clause = f" DEFAULT {val}"
                            else:
                                default_clause = " DEFAULT ''"
                        elif col.nullable:
                            default_clause = " DEFAULT NULL"
                        else:
                            default_clause = " DEFAULT ''"

                        stmt = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}{default_clause}"
                        conn.execute(text(stmt))

                        if col.index:
                            idx_name = f"ix_{table_name}_{col.name}"
                            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({col.name})"))
    except Exception:
        pass


def init_models() -> None:
    """Create tables if they do not exist yet (alembic owns real migrations).

    If the schema was created by create_all (no alembic_version yet), stamp the
    head revision so a later `alembic upgrade head` is a no-op instead of an error.
    """
    from . import models  # noqa: F401  (register mappings)

    Base.metadata.create_all(bind=engine)
    sync_columns()
    _stamp_alembic_head_if_needed()



def _stamp_alembic_head_if_needed() -> None:
    from sqlalchemy import inspect as sa_inspect

    try:
        if sa_inspect(engine).has_table("alembic_version"):
            return
        from alembic import command
        from alembic.config import Config

        backend_dir = Path(__file__).resolve().parents[1]
        cfg = Config(str(backend_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.stamp(cfg, "head")
    except Exception:  # never let bookkeeping break startup
        pass
