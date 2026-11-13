from __future__ import annotations

import logging
import re
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


_LEADING_LABEL_RE = re.compile(r"^\s*\d*\.?\s*[\w ]+:\s*", re.IGNORECASE)


def _clean_ai_field_value(result: str, field_name: str) -> str | None:
    """Defend against the model echoing the enumerated field list (e.g.
    "1. project_details: NONE\\n2. source_url: NONE...") instead of answering
    with just this field's value: if the response spans multiple lines or
    carries a leading "<label>: " prefix, take only the line for this field
    and strip its label."""
    value = result.strip()
    if "\n" in value:
        for line in value.splitlines():
            line = line.strip()
            if field_name.lower() in line.lower():
                value = line
                break
        else:
            value = value.splitlines()[0].strip()
    value = _LEADING_LABEL_RE.sub("", value).strip()
    return None if not value or value.upper() == "NONE" else value


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

    # "rule" fields (currently just "active") depend on other fields' values
    # (e.g. end_date), which may be ordered later in the skill's field list
    # (context.txt itself lists "active" before "end_date") — so rules are
    # deferred to a second pass, run only once every other field is in data.
    rule_fields: list[tuple[str, object]] = []

    for name, spec in skill.fields.items():
        if spec.method == "literal":
            data[name] = url if name == "source_url" or spec.literal_value == "$url" else spec.literal_value
        elif spec.method == "selector":
            data[name] = _selector_value(soup, spec.selector, spec.attribute) if spec.selector else None
        elif spec.method == "rule":
            rule_fields.append((name, spec))
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
                f"{context}\n\n"
                "When judging fit against the criteria above: only exclude items that clearly "
                "involve heavy physical construction/infrastructure (roads, buildings, hospitals). "
                "Training, consultancy, M&E, research, and capacity-building work should be treated "
                "as fitting, not excluded. When genuinely unsure, prefer extracting over NONE.\n\n"
                f"Now answer only the field '{name}' for the page content below.\n"
                f"Instructions for this field: {spec.ai_prompt}\n"
                "If multiple items are listed on the page, pick the one that best fits the criteria.\n"
                f"Respond with ONLY the raw value of '{name}', as plain text — no field name, number, "
                "label, or any other field's value, and do not restate these instructions.\n"
                "If truly nothing on the page fits even loosely, respond with exactly: NONE.",
                page_text[:20000],
            )
            # Low temperature: this prompt otherwise flip-flops between a real
            # answer and NONE across identical calls (observed directly).
            result = llm.complete(
                model=settings.ai_runtime_model, system="Answer concisely.", user_content=prompt, max_tokens=512, temperature=0.1
            )
            data[name] = _clean_ai_field_value(result, name)
        else:
            data[name] = None

    for name, spec in rule_fields:
        # Only the well-known "active" rule is implemented generically; others
        # fall back to None and should be reviewed if they appear.
        if name == "active":
            data[name] = compute_active(data.get("end_date") or data.get("deadline"), date.today())
        else:
            data[name] = None

    return data
