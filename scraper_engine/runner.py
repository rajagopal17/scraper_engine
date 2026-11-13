from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import urlparse

from . import db
from .config import Settings, CONTEXT_FILE, OUTPUT_DIR, SKILLS_DIR, URLS_FILE
from .dedup import compute_record_key
from .export import export_run
from .extract import AiCallBudget, extract_record
from .fetch import NonRetryableFetchError, fetch
from .inputs import load_context, load_urls
from .llm import LLMClient
from .security import DomainRateLimiter, RobotsChecker
from .skill_builder import load_skill
from .validate import validate_record

logger = logging.getLogger(__name__)


def run_all(settings: Settings, only_url: str | None = None) -> None:
    urls = [only_url] if only_url else load_urls(URLS_FILE)
    context = load_context(CONTEXT_FILE)
    robots = RobotsChecker(settings.http_timeout_seconds)
    rate_limiter = DomainRateLimiter(settings.rate_limit_seconds_per_domain)
    budget = AiCallBudget(settings.max_ai_calls_per_site_per_run, settings.max_ai_calls_per_run)
    llm = LLMClient(settings.ai_api_key, settings.ai_base_url, settings.ai_provider) if settings.ai_api_key else None

    all_merged_records: list[dict] = []

    with db.connect(settings) as conn:
        for url in urls:
            domain = urlparse(url).netloc
            started_at = datetime.utcnow()
            rows_found = rows_new = rows_updated = rows_rejected = 0
            status = "ok"
            error_summary = None

            health = db.get_domain_health(conn, domain)
            if health["circuit_open"]:
                logger.warning("skipping %s: circuit breaker open (too many consecutive failures)", domain)
                db.record_run(conn, url, domain, started_at, datetime.utcnow(), "circuit_open", 0, 0, 0, 0, 0, "circuit breaker open")
                continue

            skill = load_skill(domain, SKILLS_DIR)
            if skill is None:
                logger.warning("skipping %s: no skill found, run `build-skill %s` first", url, url)
                db.record_run(conn, url, domain, started_at, datetime.utcnow(), "skipped", 0, 0, 0, 0, 0, "no skill file")
                continue

            try:
                if settings.respect_robots_txt and not robots.is_allowed(url):
                    raise NonRetryableFetchError(f"disallowed by robots.txt: {url}")

                rate_limiter.wait(domain)
                html = fetch(url, settings, skill.fetch_method, skill.auth)

                data = extract_record(html, url, skill, context, settings, llm, budget)
                rows_found = 1
                validation = validate_record(data)
                if not validation.ok:
                    rows_rejected = 1
                    logger.warning("rejected record from %s: %s", url, validation.reasons)
                else:
                    record_key, key_type = compute_record_key(data, skill.dedup_key_fields)
                    result = db.upsert_record(conn, url, domain, record_key, key_type, data)
                    rows_new += result == "new"
                    rows_updated += result == "updated"
                    all_merged_records.append(data)

                db.record_domain_result(conn, domain, success=True, circuit_breaker_threshold=settings.circuit_breaker_consecutive_failures)

            except NonRetryableFetchError as exc:
                status, error_summary = "failed", str(exc)
                logger.error("non-retryable failure for %s: %s", url, exc)
                db.record_domain_result(conn, domain, success=False, circuit_breaker_threshold=settings.circuit_breaker_consecutive_failures, reason=str(exc))
            except Exception as exc:  # noqa: BLE001 - isolate per-URL failures from the rest of the run
                status, error_summary = "failed", str(exc)
                logger.exception("failed to process %s", url)
                db.record_domain_result(conn, domain, success=False, circuit_breaker_threshold=settings.circuit_breaker_consecutive_failures, reason=str(exc))

            db.record_run(
                conn, url, domain, started_at, datetime.utcnow(), status,
                rows_found, rows_new, rows_updated, rows_rejected, budget.run_total, error_summary,
            )

    if all_merged_records:
        json_path, csv_path = export_run(all_merged_records, OUTPUT_DIR)
        logger.info("exported %d records to %s and %s", len(all_merged_records), json_path, csv_path)
