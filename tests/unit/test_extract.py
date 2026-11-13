from pathlib import Path

from scraper_engine.config import Settings
from scraper_engine.extract import AiCallBudget, extract_record
from scraper_engine.models import FieldSpec, Skill

FIXTURE = (Path(__file__).resolve().parent.parent / "fixtures" / "sample_ngo_page.html").read_text(encoding="utf-8")


def _skill() -> Skill:
    return Skill(
        url="https://ngo-example.org/projects/1",
        domain="ngo-example.org",
        created_at="2026-01-01",
        last_verified_at="2026-01-01",
        fetch_method="static",
        fields={
            "source_url": FieldSpec(method="literal", literal_value="$url"),
            "region": FieldSpec(method="selector", selector=".region"),
            "start_date": FieldSpec(method="selector", selector=".start"),
            "end_date": FieldSpec(method="selector", selector=".end"),
            "active": FieldSpec(method="rule", rule="end_date < run_date -> false"),
            "project_details": FieldSpec(method="ai_judged", ai_prompt="Summarize the project in <=1000 words."),
        },
        dedup_key_fields=["source_url"],
    )


class _FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete(self, **kwargs):
        self.calls += 1
        return self.response


def test_selector_and_literal_and_rule_fields_extracted_without_ai():
    skill = _skill()
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    llm = _FakeLLM("A community nutrition program.")
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), llm, budget)

    assert data["source_url"] == "https://ngo-example.org/projects/1"
    assert data["region"] == "Kenya, Nakuru County"
    assert data["start_date"] == "2026-01-10"
    assert data["end_date"] == "2099-12-31"
    assert data["active"] is True  # far-future end date, rule-computed, no AI call for this field


def test_ai_judged_field_uses_llm_and_respects_budget():
    skill = _skill()
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    llm = _FakeLLM("A community nutrition program.")
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), llm, budget)

    assert data["project_details"] == "A community nutrition program."
    assert llm.calls == 1
    assert budget.run_total == 1


def test_ai_judged_field_skipped_once_budget_exhausted():
    skill = _skill()
    budget = AiCallBudget(per_site_limit=0, per_run_limit=10)
    llm = _FakeLLM("should not be used")
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), llm, budget)

    assert data["project_details"] is None
    assert llm.calls == 0


def test_missing_selector_match_is_none_not_error():
    skill = _skill()
    skill.fields["region"] = FieldSpec(method="selector", selector=".does-not-exist")
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), _FakeLLM("x"), budget)
    assert data["region"] is None
