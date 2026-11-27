import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import DATABASE_URL


def open_connection():
    return psycopg.connect(DATABASE_URL, prepare_threshold=None, row_factory=dict_row)


pool = ConnectionPool(
    conninfo=DATABASE_URL,
    kwargs={"prepare_threshold": None, "row_factory": dict_row},
    min_size=1,
    max_size=10,
    open=True,
)


def wait_for_database(retries=30, delay=2):
    for attempt in range(retries):
        try:
            with pool.connection() as conn:
                conn.execute("SELECT 1")
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(delay)


def initialize_schema_if_empty():
    with pool.connection() as conn:
        table_count = conn.execute(
            "SELECT COUNT(*) AS count FROM pg_tables WHERE schemaname = 'public'"
        ).fetchone()["count"]
        if table_count:
            required_tables = {
                "customer",
                "vehicle",
                "employee",
                "receptionist",
                "manager",
                "mechanic",
                "appointment",
                "repair",
                "invoice",
                "spare_part",
                "repair_part",
                "app_user",
            }
            existing_tables = {
                row["tablename"]
                for row in conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                ).fetchall()
            }
            missing_tables = required_tables - existing_tables
            if missing_tables:
                missing = ", ".join(sorted(missing_tables))
                raise RuntimeError(
                    f"Database schema is incomplete; missing tables: {missing}"
                )
            return

        schema_path = Path(__file__).resolve().parent.parent / "db" / "init.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        with conn.transaction():
            conn.execute(schema_sql, prepare=False)


@contextmanager
def transaction():
    with pool.connection() as conn:
        with conn.transaction():
            yield conn


def fetch_all(sql, params=None):
    with pool.connection() as conn:
        return conn.execute(sql, params or()).fetchall()


def fetch_one(sql, params=None):
    with pool.connection() as conn:
        return conn.execute(sql, params or()).fetchone()
