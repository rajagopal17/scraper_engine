-- Core storage: one generic table per the design (jsonb payload), plus a run audit log.

CREATE TABLE IF NOT EXISTS scraped_data (
    id              BIGSERIAL PRIMARY KEY,
    source_url      TEXT NOT NULL,
    domain          TEXT NOT NULL,
    record_key      TEXT NOT NULL,          -- natural key if the skill defines one, else content hash
    key_type        TEXT NOT NULL CHECK (key_type IN ('natural', 'hash')),
    data            JSONB NOT NULL,         -- extracted fields, same schema across all sites (nulls allowed)
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (domain, record_key)
);

CREATE INDEX IF NOT EXISTS idx_scraped_data_domain ON scraped_data (domain);
CREATE INDEX IF NOT EXISTS idx_scraped_data_data_gin ON scraped_data USING GIN (data);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id              BIGSERIAL PRIMARY KEY,
    url             TEXT NOT NULL,
    domain          TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'failed', 'skipped', 'circuit_open')),
    rows_found      INTEGER NOT NULL DEFAULT 0,
    rows_new        INTEGER NOT NULL DEFAULT 0,
    rows_updated    INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    ai_calls_used   INTEGER NOT NULL DEFAULT 0,
    error_summary   TEXT
);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_domain ON scrape_runs (domain, started_at DESC);

CREATE TABLE IF NOT EXISTS domain_health (
    domain                      TEXT PRIMARY KEY,
    consecutive_failures        INTEGER NOT NULL DEFAULT 0,
    circuit_open                BOOLEAN NOT NULL DEFAULT false,
    last_failure_at             TIMESTAMPTZ,
    needs_review                BOOLEAN NOT NULL DEFAULT false,
    needs_review_reason         TEXT
);
