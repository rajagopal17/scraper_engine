from __future__ import annotations

from . import db
from .config import Settings


def print_status(settings: Settings) -> None:
    with db.connect(settings) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT domain, consecutive_failures, circuit_open, needs_review, needs_review_reason "
                "FROM domain_health ORDER BY domain"
            )
            rows = cur.fetchall()
            print("Domain health:")
            if not rows:
                print("  (no data yet)")
            for domain, failures, circuit_open, needs_review, reason in rows:
                flags = []
                if circuit_open:
                    flags.append("CIRCUIT_OPEN")
                if needs_review:
                    flags.append(f"NEEDS_REVIEW: {reason}")
                print(f"  {domain}: consecutive_failures={failures} {' '.join(flags)}")

            cur.execute(
                "SELECT url, status, started_at, rows_found, rows_new, rows_updated, rows_rejected, error_summary "
                "FROM scrape_runs ORDER BY started_at DESC LIMIT 20"
            )
            print("\nRecent runs:")
            for url, status, started_at, found, new, updated, rejected, error in cur.fetchall():
                line = f"  [{started_at}] {status:10s} {url} found={found} new={new} updated={updated} rejected={rejected}"
                if error:
                    line += f" error={error}"
                print(line)
