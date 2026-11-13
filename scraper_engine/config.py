from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT_DIR / "skills"
OUTPUT_DIR = ROOT_DIR / "output"
URLS_FILE = ROOT_DIR / "urls.txt"
CONTEXT_FILE = ROOT_DIR / "context.txt"


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _float_env(name: str, default: float) -> float:
    val = os.environ.get(name)
    return float(val) if val else default


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


@dataclass(frozen=True)
class Settings:
    # AI
    ai_api_key: str | None = os.environ.get("AI_API_KEY")
    ai_base_url: str = os.environ.get("AI_BASE_URL", "https://api.anthropic.com")
    ai_skill_build_model: str = os.environ.get("AI_SKILL_BUILD_MODEL", "claude-opus-4-20250514")
    ai_runtime_model: str = os.environ.get("AI_RUNTIME_MODEL", "claude-haiku-4-20250514")

    # Postgres
    pg_host: str = os.environ.get("POSTGRES_HOST", "localhost")
    pg_port: int = _int_env("POSTGRES_PORT", 5432)
    pg_db: str = os.environ.get("POSTGRES_DB", "scraper_engine")
    pg_user: str = os.environ.get("POSTGRES_USER", "scraper")
    pg_password: str = os.environ.get("POSTGRES_PASSWORD", "")

    # Runtime defaults (all overridable via env)
    http_timeout_seconds: float = _float_env("HTTP_TIMEOUT_SECONDS", 20)
    rate_limit_seconds_per_domain: float = _float_env("RATE_LIMIT_SECONDS_PER_DOMAIN", 2.0)
    max_retries: int = _int_env("MAX_RETRIES", 3)
    retry_backoff_base_seconds: float = _float_env("RETRY_BACKOFF_BASE_SECONDS", 1.0)
    retry_backoff_max_seconds: float = _float_env("RETRY_BACKOFF_MAX_SECONDS", 30)
    circuit_breaker_consecutive_failures: int = _int_env("CIRCUIT_BREAKER_CONSECUTIVE_FAILURES", 5)
    max_ai_calls_per_site_per_run: int = _int_env("MAX_AI_CALLS_PER_SITE_PER_RUN", 10)
    max_ai_calls_per_run: int = _int_env("MAX_AI_CALLS_PER_RUN", 100)
    respect_robots_txt: bool = _bool_env("RESPECT_ROBOTS_TXT", True)

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
            f"user={self.pg_user} password={self.pg_password}"
        )


def get_settings() -> Settings:
    return Settings()
