import sqlite3
from sqlalchemy import inspect as sa_inspect, text
from app.db import engine, Base
import app.models

def sync_columns():
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
                    print(f"Adding column: {stmt}")
                    conn.execute(text(stmt))

                    if col.index:
                        idx_name = f"ix_{table_name}_{col.name}"
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({col.name})"))

if __name__ == "__main__":
    sync_columns()
    inspector = sa_inspect(engine)
    cols = [c["name"] for c in inspector.get_columns("leads")]
    print(f"Successfully synced! Leads now has {len(cols)} columns.")
    print("Has dedupe_key:", "dedupe_key" in cols)
