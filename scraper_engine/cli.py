from __future__ import annotations

import argparse
import logging
import sys

from . import db
from .config import CONTEXT_FILE, SKILLS_DIR, get_settings
from .inputs import load_context
from .llm import LLMClient
from .skill_builder import build_skill, save_skill


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("scraper_engine.log")],
    )


def main(argv: list[str] | None = None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="scraper_engine")
    sub = parser.add_subparsers(dest="command", required=True)

    build_p = sub.add_parser("build-skill", help="Build/update the skill file for one URL (one-time/manual, uses AI)")
    build_p.add_argument("url")

    run_p = sub.add_parser("run", help="Run the scheduled scrape pass over all URLs (deterministic, no skill creation)")
    run_p.add_argument("--url", default=None, help="Run only this single URL instead of all of urls.txt")

    sub.add_parser("status", help="Show domain health and recent run history")

    sub.add_parser("init-db", help="Apply the Postgres schema")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.command == "build-skill":
        if not settings.ai_api_key:
            print("AI_API_KEY is not set; cannot build a skill.", file=sys.stderr)
            return 1
        llm = LLMClient(settings.ai_api_key, settings.ai_base_url)
        context = load_context(CONTEXT_FILE)
        skill = build_skill(args.url, context, settings, llm)
        save_skill(skill, SKILLS_DIR)
        print(f"skill written to {SKILLS_DIR / (skill.domain + '.yaml')}")
        if skill.needs_review:
            print(f"WARNING: needs_review: {skill.needs_review_reason}", file=sys.stderr)
        return 0

    if args.command == "run":
        from .runner import run_all

        run_all(settings, only_url=args.url)
        return 0

    if args.command == "status":
        from .status import print_status

        print_status(settings)
        return 0

    if args.command == "init-db":
        from pathlib import Path

        schema_sql = (Path(__file__).resolve().parent.parent / "sql" / "schema.sql").read_text(encoding="utf-8")
        with db.connect(settings) as conn:
            db.apply_schema(conn, schema_sql)
        print("schema applied")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
