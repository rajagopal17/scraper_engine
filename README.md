# scraper_engine

AI-enabled web scraper engine: build a reusable "skill" per website (AI-assisted,
one-time), then run a deterministic scheduled pipeline that extracts the fields
described in `context.txt`, validates and dedupes them, and merges them into
PostgreSQL (plus a JSON/CSV export).

## Architecture

- **Skill-build (manual, AI-assisted):** `python -m scraper_engine build-skill <url>`
  fetches the page, sends it + `context.txt` to the AI, and writes
  `skills/<domain>.yaml` describing how to extract each field for that site
  (CSS selector, a deterministic rule, or an `ai_judged` prompt for fields that
  need subjective judgment/summarization).
- **Run (scheduled, deterministic):** `python -m scraper_engine run` reads
  `urls.txt`, applies each URL's existing skill, validates, dedupes
  (natural key if the skill defines one, else a content hash), upserts into
  Postgres (`last_updated_at` tracks changes to existing records), and exports
  JSON/CSV. It never creates or edits skills, and only calls the AI for fields
  explicitly tagged `ai_judged` (budget-capped).
- **Status:** `python -m scraper_engine status` shows domain health (circuit
  breaker state, consecutive failures) and recent run history.

See the inline docstrings/comments in `scraper_engine/` for the reasoning behind
specific decisions (dedup, validation, AI-call budgeting, prompt-injection
handling).

## Inputs

- `urls.txt` — one URL per line.
- `context.txt` — **one global document, shared by every URL**: what data to
  extract, filter/relevance criteria, and the desired output fields. The
  skill-builder figures out per-site *how* to satisfy it.

## Setup

```bash
cp .env.example .env   # fill in AI_API_KEY, POSTGRES_PASSWORD, any per-site SITE*_USER/PASS
docker compose up -d postgres
docker compose run --rm scraper python -m scraper_engine init-db
```

## Usage

```bash
# one-time per new URL in urls.txt:
docker compose run --rm scraper python -m scraper_engine build-skill https://example.org/ngo-projects

# scheduled job (wire this into Windows Task Scheduler / cron):
docker compose run --rm scraper python -m scraper_engine run

docker compose run --rm scraper python -m scraper_engine status
```

## Tests

```bash
pip install -r requirements.txt
pytest tests/unit                 # fast, no network/DB/AI required
docker compose up -d postgres
POSTGRES_HOST=localhost pytest tests/integration   # needs live Postgres
```
