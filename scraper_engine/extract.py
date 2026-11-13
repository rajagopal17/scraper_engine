from __future__ import annotations

import logging
from datetime import date

from bs4 import BeautifulSoup

from .config import Settings
from .llm import LLMClient
from .models import Skill
from .security import build_safe_user_prompt
from .validate import compute_active

logger = logging.getLogger(__name__)


class AiCallBudgetExceeded(Exception):
    pass


class AiCallBudget:
    """Bounds AI spend per run and per site (req #11)."""

    def __init__(self, per_site_limit: int, per_run_limit: int):
        self.per_site_limit = per_site_limit
        self.per_run_limit = per_run_limit
        self.run_total = 0
        self._per_site: dict[str, int] = {}

    def consume(self, domain: str) -> None:
        if self.run_total >= self.per_run_limit:
            raise AiCallBudgetExceeded(f"run-wide AI call budget ({self.per_run_limit}) exceeded")
        used = self._per_site.get(domain, 0)
        if used >= self.per_site_limit:
            raise AiCallBudgetExceeded(f"per-site AI call budget ({self.per_site_limit}) exceeded for {domain}")
        self._per_site[domain] = used + 1
        self.run_total += 1


def _selector_value(soup: BeautifulSoup, selector: str, attribute: str | None) -> str | None:
    el = soup.select_one(selector)
    if el is None:
        return None
    if attribute:
        return el.get(attribute)
    return el.get_text(strip=True)


def extract_record(
    html: str,
    url: str,
    skill: Skill,
    context: str,
    settings: Settings,
    llm: LLMClient | None,
    budget: AiCallBudget,
) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(separator="\n", strip=True)
    data: dict[str, object] = {}

    for name, spec in skill.fields.items():
        if spec.method == "literal":
            data[name] = url if name == "source_url" or spec.literal_value == "$url" else spec.literal_value
        elif spec.method == "selector":
            data[name] = _selector_value(soup, spec.selector, spec.attribute) if spec.selector else None
        elif spec.method == "rule":
            # Only the well-known "active" rule is implemented generically; others
            # fall back to None and should be reviewed if they appear.
            if name == "active":
                data[name] = compute_active(data.get("end_date") or data.get("deadline"), date.today())
            else:
                data[name] = None
        elif spec.method == "ai_judged":
            if llm is None or not spec.ai_prompt:
                data[name] = None
                continue
            try:
                budget.consume(skill.domain)
            except AiCallBudgetExceeded as exc:
                logger.warning("skipping ai_judged field %r for %s: %s", name, url, exc)
                data[name] = None
                continue
            prompt = build_safe_user_prompt(
                f"{context}\n\nField-specific instructions: {spec.ai_prompt}\n"
                "Respond with only the extracted value for this field, nothing else. "
                "If the value is not present or doesn't apply, respond with exactly: NONE.",
                page_text[:20000],
            )
            result = llm.complete(model=settings.ai_runtime_model, system="Answer concisely.", user_content=prompt, max_tokens=512)
            data[name] = None if result.strip().upper() == "NONE" else result.strip()
        else:
            data[name] = None

    return data
