from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime

import psycopg

from .config import Settings

logger = logging.getLogger(__name__)


@contextmanager
def connect(settings: Settings):
    conn = psycopg.connect(settings.pg_dsn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def apply_schema(conn, schema_sql: str) -> None:
    with conn.cursor() as cur:
        cur.execute(schema_sql)


def upsert_record(conn, source_url: str, domain: str, record_key: str, key_type: str, data: dict) -> str:
    """Insert new, or update existing row + last_updated_at. Returns 'new' or 'updated'."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scraped_data (source_url, domain, record_key, key_type, data)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (domain, record_key) DO UPDATE
                SET data = EXCLUDED.data,
                    last_updated_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            (source_url, domain, record_key, key_type, json.dumps(data, default=str)),
        )
        inserted = cur.fetchone()[0]
        return "new" if inserted else "updated"


def record_run(
    conn,
    url: str,
    domain: str,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    rows_found: int,
    rows_new: int,
    rows_updated: int,
    rows_rejected: int,
    ai_calls_used: int,
    error_summary: str | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scrape_runs (url, domain, started_at, finished_at, status,
                                      rows_found, rows_new, rows_updated, rows_rejected,
                                      ai_calls_used, error_summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (url, domain, started_at, finished_at, status, rows_found, rows_new, rows_updated, rows_rejected, ai_calls_used, error_summary),
        )


def get_domain_health(conn, domain: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT consecutive_failures, circuit_open, needs_review, needs_review_reason FROM domain_health WHERE domain = %s", (domain,))
        row = cur.fetchone()
        if row is None:
            return {"consecutive_failures": 0, "circuit_open": False, "needs_review": False, "needs_review_reason": None}
        return {"consecutive_failures": row[0], "circuit_open": row[1], "needs_review": row[2], "needs_review_reason": row[3]}


def record_domain_result(conn, domain: str, success: bool, circuit_breaker_threshold: int, reason: str | None = None) -> None:
    with conn.cursor() as cur:
        if success:
            cur.execute(
                """
                INSERT INTO domain_health (domain, consecutive_failures, circuit_open)
                VALUES (%s, 0, false)
                ON CONFLICT (domain) DO UPDATE SET consecutive_failures = 0, circuit_open = false
                """,
                (domain,),
            )
        else:
            cur.execute(
                """
                INSERT INTO domain_health (domain, consecutive_failures, circuit_open, last_failure_at, needs_review, needs_review_reason)
                VALUES (%s, 1, false, now(), false, %s)
                ON CONFLICT (domain) DO UPDATE SET
                    consecutive_failures = domain_health.consecutive_failures + 1,
                    circuit_open = (domain_health.consecutive_failures + 1) >= %s,
                    last_failure_at = now(),
                    needs_review = (domain_health.consecutive_failures + 1) >= %s,
                    needs_review_reason = %s
                """,
                (domain, reason, circuit_breaker_threshold, circuit_breaker_threshold, reason),
            )
