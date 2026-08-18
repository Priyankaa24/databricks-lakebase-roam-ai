"""
Lakebase (Databricks-managed Postgres) connection helper.

Uses psycopg v3 for compatibility with restricted environments.
Same code as root lakebase.py — copied here so mcp_server/ deploys
as a self-contained Databricks App.
"""

import base64
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import create_engine

_SCOPE = os.environ.get("LAKEBASE_SECRET_SCOPE", "database")
_KEY = os.environ.get("LAKEBASE_SECRET_KEY", "lakebase-url")

_w = None


def _get_workspace_client():
    """Lazy-init WorkspaceClient to avoid auth issues at module import time."""
    global _w
    if _w is None:
        from databricks.sdk import WorkspaceClient
        _w = WorkspaceClient()
    return _w


def _lakebase_url() -> str:
    """Fetch and decode the Lakebase URL from the Databricks secret scope."""
    secret = _get_workspace_client().secrets.get_secret(scope=_SCOPE, key=_KEY)
    return base64.b64decode(secret.value).decode("utf-8")


@contextmanager
def get_connection():
    """Yield a psycopg connection with dict_row factory."""
    conn = psycopg.connect(_lakebase_url(), row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def get_engine():
    """SQLAlchemy engine for Lakebase (uses psycopg v3 dialect)."""
    url = _lakebase_url()
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url)


def run_query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """Run a read query, return rows as list[dict]."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def run_write(sql: str, params: tuple | dict | None = None) -> int:
    """Run INSERT/UPDATE/DELETE, return affected row count."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
