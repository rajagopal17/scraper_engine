from __future__ import annotations

import json
import logging
from datetime import date
from urllib.parse import urlparse

import httpx
import yaml

from .config import Settings
from .llm import LLMClient
from .models import AuthConfig, FieldSpec, PaginationConfig, Skill
from .security import build_safe_user_prompt

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a web-scraping analyst. You are given:
1. A global context document describing what data to extract from ANY site in a \
collection of NGO-project-listing websites, including filter criteria.
2. The HTML (or rendered text) of one specific site that is part of that collection.

Decide, for THIS site only, how to extract each required field, and respond with
ONLY a single JSON object (no prose, no markdown fences) with this shape:

{
  "fetch_method": "static" | "rendered",
  "dedup_key_fields": ["field_name", ...] | null,
  "fields": {
    "<field_name>": {
      "method": "selector" | "ai_judged" | "rule" | "literal",
      "selector": "<CSS selector>" | null,
      "attribute": "<html attribute to read, or null for text>" ,
      "rule": "<short rule description, e.g. 'end_date < run_date -> false'>" | null,
      "ai_prompt": "<scoped instructions for an AI call to extract/judge this field from page text>" | null,
      "literal_value": "<e.g. the page URL itself>" | null
    }
  },
  "auth": {"login_type": "none" | "form", "login_url": null, "username_selector": null,
            "password_selector": null, "submit_selector": null},
  "pagination": {"type": "none" | "next_link" | "infinite_scroll", "selector": null}
}

Rules:
- Use "selector" when a field can be read directly and mechanically from the DOM.
- Use "rule" for fields that are a deterministic computation (e.g. "active" from end_date
  vs. today's date) — do not call AI for these at runtime.
- Use "ai_judged" ONLY when the field requires subjective judgment or free-text
  summarization that a selector cannot capture (e.g. summarizing project details,
  or judging whether a project is capital-intensive per the context document).
- Use "literal" for fields that don't need extraction (e.g. source_url is the given URL).
- Do not invent fields that are not requested in the context document.
"""


def _fetch_page_text(url: str, timeout: float) -> str:
    resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "scraper-engine-skill-builder/1.0"})
    resp.raise_for_status()
    return resp.text


def build_skill(url: str, context: str, settings: Settings, llm: LLMClient) -> Skill:
    domain = urlparse(url).netloc
    page_text = _fetch_page_text(url, settings.http_timeout_seconds)
    # Keep the prompt bounded; page text can be large.
    truncated_page = page_text[:20000]

    instructions = f"{_SYSTEM_PROMPT}\n\nCONTEXT DOCUMENT (applies to all sites):\n{context}\n\nTARGET URL: {url}"
    user_prompt = build_safe_user_prompt(instructions, truncated_page)

    raw = llm.complete(
        model=settings.ai_skill_build_model,
        system="Respond with ONLY the JSON object described. No other text.",
        user_content=user_prompt,
        max_tokens=4096,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("skill-builder returned non-JSON output for %s: %s", url, exc)
        today = date.today().isoformat()
        return Skill(
            url=url,
            domain=domain,
            created_at=today,
            last_verified_at=today,
            needs_review=True,
            needs_review_reason=f"LLM output was not valid JSON: {exc}",
        )

    today = date.today().isoformat()
    fields = {name: FieldSpec(**spec) for name, spec in parsed.get("fields", {}).items()}
    auth = AuthConfig(**parsed.get("auth", {})) if parsed.get("auth") else AuthConfig()
    pagination = PaginationConfig(**parsed.get("pagination", {})) if parsed.get("pagination") else PaginationConfig()

    return Skill(
        url=url,
        domain=domain,
        created_at=today,
        last_verified_at=today,
        fetch_method=parsed.get("fetch_method", "static"),
        fields=fields,
        dedup_key_fields=parsed.get("dedup_key_fields"),
        auth=auth,
        pagination=pagination,
    )


def save_skill(skill: Skill, skills_dir) -> None:
    skills_dir.mkdir(parents=True, exist_ok=True)
    path = skills_dir / f"{skill.domain}.yaml"
    path.write_text(yaml.safe_dump(json.loads(skill.model_dump_json()), sort_keys=False), encoding="utf-8")


def load_skill(domain: str, skills_dir) -> Skill | None:
    path = skills_dir / f"{domain}.yaml"
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Skill(**raw)
