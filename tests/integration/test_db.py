"""Integration tests against a real Postgres instance.

Run via the Docker Compose postgres service:
  docker compose up -d postgres
  POSTGRES_HOST=localhost pytest tests/integration

Skipped automatically if no Postgres is reachable, so the unit suite (and CI by
default) never needs a live database.
"""

from datetime import datetime
from pathlib import Path

import psycopg
import pytest

from scraper_engine import db
from scraper_engine.config import Settings

SCHEMA_SQL = (Path(__file__).resolve().parent.parent.parent / "sql" / "schema.sql").read_text(encoding="utf-8")


def _settings() -> Settings:
    return Settings()


def _postgres_available() -> bool:
    try:
        with psycopg.connect(_settings().pg_dsn, connect_timeout=2):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="no reachable Postgres instance")


@pytest.fixture()
def conn():
    settings = _settings()
    with db.connect(settings) as c:
        db.apply_schema(c, SCHEMA_SQL)
        with c.cursor() as cur:
            cur.execute("TRUNCATE scraped_data, scrape_runs, domain_health")
        yield c


def test_upsert_inserts_new_then_updates_existing(conn):
    result1 = db.upsert_record(conn, "https://x.org/a", "x.org", "key1", "natural", {"v": 1})
    assert result1 == "new"

    result2 = db.upsert_record(conn, "https://x.org/a", "x.org", "key1", "natural", {"v": 2})
    assert result2 == "updated"

    with conn.cursor() as cur:
        cur.execute("SELECT data, first_seen_at, last_updated_at FROM scraped_data WHERE record_key = 'key1'")
        data, first_seen, last_updated = cur.fetchone()
        assert data == {"v": 2}
        assert last_updated >= first_seen


def test_circuit_breaker_opens_after_threshold(conn):
    for _ in range(5):
        db.record_domain_result(conn, "flaky.org", success=False, circuit_breaker_threshold=5, reason="timeout")
    health = db.get_domain_health(conn, "flaky.org")
    assert health["circuit_open"] is True
    assert health["needs_review"] is True


def test_success_resets_consecutive_failures(conn):
    db.record_domain_result(conn, "y.org", success=False, circuit_breaker_threshold=5, reason="x")
    db.record_domain_result(conn, "y.org", success=True, circuit_breaker_threshold=5)
    health = db.get_domain_health(conn, "y.org")
    assert health["consecutive_failures"] == 0
    assert health["circuit_open"] is False


def test_record_run_is_queryable(conn):
    now = datetime.utcnow()
    db.record_run(conn, "https://x.org", "x.org", now, now, "ok", 1, 1, 0, 0, 2, None)
    with conn.cursor() as cur:
        cur.execute("SELECT status, ai_calls_used FROM scrape_runs WHERE domain = 'x.org'")
        status, ai_calls = cur.fetchone()
        assert status == "ok"
        assert ai_calls == 2
