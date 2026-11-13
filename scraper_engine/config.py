from __future__ import annotations

import os
from dataclasses import dataclass, field
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


def _str_env(name: str, default: str | None = None) -> str | None:
    """Env values are stripped: a stray leading/trailing space in .env (easy to
    introduce by hand) would otherwise silently break the URL/key/host."""
    val = os.environ.get(name)
    if val is None:
        return default
    val = val.strip()
    return val or default


def _provider_env() -> str:
    explicit = _str_env("AI_PROVIDER", "")
    if explicit:
        return explicit
    base_url = _str_env("AI_BASE_URL", "") or ""
    return "openai" if "openai.com" in base_url else "anthropic"


# Field defaults use default_factory (evaluated per-instance, at Settings()
# call time) rather than plain `= os.environ.get(...)` (which a dataclass
# would evaluate exactly once, at class-definition/import time, so later
# changes to the environment within the same process would be invisible).
@dataclass(frozen=True)
class Settings:
    # AI. Provider is inferred from AI_BASE_URL unless AI_PROVIDER is set explicitly.
    ai_api_key: str | None = field(default_factory=lambda: _str_env("AI_API_KEY"))
    ai_base_url: str = field(default_factory=lambda: _str_env("AI_BASE_URL", "https://api.anthropic.com"))
    ai_provider: str = field(default_factory=_provider_env)
    ai_skill_build_model: str = field(default_factory=lambda: os.environ.get("AI_SKILL_BUILD_MODEL", "claude-opus-4-20250514"))
    ai_runtime_model: str = field(default_factory=lambda: os.environ.get("AI_RUNTIME_MODEL", "claude-haiku-4-20250514"))

    # Postgres
    pg_host: str = field(default_factory=lambda: os.environ.get("POSTGRES_HOST", "localhost"))
    pg_port: int = field(default_factory=lambda: _int_env("POSTGRES_PORT", 5432))
    pg_db: str = field(default_factory=lambda: os.environ.get("POSTGRES_DB", "scraper_engine"))
    pg_user: str = field(default_factory=lambda: os.environ.get("POSTGRES_USER", "scraper"))
    pg_password: str = field(default_factory=lambda: os.environ.get("POSTGRES_PASSWORD", ""))

    # Runtime defaults (all overridable via env)
    http_timeout_seconds: float = field(default_factory=lambda: _float_env("HTTP_TIMEOUT_SECONDS", 20))
    rate_limit_seconds_per_domain: float = field(default_factory=lambda: _float_env("RATE_LIMIT_SECONDS_PER_DOMAIN", 2.0))
    max_retries: int = field(default_factory=lambda: _int_env("MAX_RETRIES", 3))
    retry_backoff_base_seconds: float = field(default_factory=lambda: _float_env("RETRY_BACKOFF_BASE_SECONDS", 1.0))
    retry_backoff_max_seconds: float = field(default_factory=lambda: _float_env("RETRY_BACKOFF_MAX_SECONDS", 30))
    circuit_breaker_consecutive_failures: int = field(default_factory=lambda: _int_env("CIRCUIT_BREAKER_CONSECUTIVE_FAILURES", 5))
    max_ai_calls_per_site_per_run: int = field(default_factory=lambda: _int_env("MAX_AI_CALLS_PER_SITE_PER_RUN", 10))
    max_ai_calls_per_run: int = field(default_factory=lambda: _int_env("MAX_AI_CALLS_PER_RUN", 100))
    respect_robots_txt: bool = field(default_factory=lambda: _bool_env("RESPECT_ROBOTS_TXT", True))

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
            f"user={self.pg_user} password={self.pg_password}"
        )


def get_settings() -> Settings:
    return Settings()
