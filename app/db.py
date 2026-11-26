import time
from contextlib import contextmanager

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
