from pathlib import Path

from scraper_engine.config import Settings
from scraper_engine.extract import AiCallBudget, _clean_ai_field_value, extract_record
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
        self.last_kwargs: dict = {}

    def complete(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
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


def test_ai_judged_field_recovers_from_echoed_field_list():
    """The model sometimes ignores 'answer only this field' and echoes the
    context document's numbered field list back (a real failure seen in
    production); the extracted value must still be the real answer, or None,
    never the echoed template."""
    skill = _skill()
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    echoed = (
        "1. project_details: A community nutrition program.\n"
        "2. source_url: NONE\n"
        "3. region: NONE\n"
        "4. active: NONE\n"
        "5. start_date: NONE\n"
        "6. end_date: NONE"
    )
    llm = _FakeLLM(echoed)
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), llm, budget)

    assert data["project_details"] == "A community nutrition program."


def test_ai_judged_field_recovers_from_all_none_echo():
    skill = _skill()
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    echoed = "1. project_details: NONE\n2. source_url: NONE\n3. region: NONE"
    llm = _FakeLLM(echoed)
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), llm, budget)

    assert data["project_details"] is None


def test_clean_ai_field_value_strips_leading_label():
    assert _clean_ai_field_value("project_details: A nutrition program.", "project_details") == "A nutrition program."


def test_clean_ai_field_value_plain_answer_passthrough():
    assert _clean_ai_field_value("A nutrition program.", "project_details") == "A nutrition program."


def test_clean_ai_field_value_none_cases():
    assert _clean_ai_field_value("NONE", "project_details") is None
    assert _clean_ai_field_value("  ", "project_details") is None


def test_active_rule_computed_correctly_even_when_listed_before_end_date_in_skill():
    """context.txt enumerates 'active' before 'end_date', so AI-generated
    skills consistently order the fields the same way — active must not
    silently depend on end_date not having been extracted yet."""
    skill = Skill(
        url="https://ngo-example.org/projects/1",
        domain="ngo-example.org",
        created_at="2026-01-01",
        last_verified_at="2026-01-01",
        fetch_method="static",
        fields={
            "source_url": FieldSpec(method="literal", literal_value="$url"),
            "region": FieldSpec(method="selector", selector=".region"),
            "active": FieldSpec(method="rule", rule="end_date < run_date -> false"),
            "start_date": FieldSpec(method="selector", selector=".start"),
            "end_date": FieldSpec(method="selector", selector=".end"),
        },
        dedup_key_fields=["source_url"],
    )
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    data = extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), _FakeLLM("x"), budget)

    assert data["end_date"] == "2099-12-31"
    assert data["active"] is True  # must not be None just because active was listed first


def test_ai_judged_field_uses_low_temperature():
    """A near-zero temperature is required for this prompt to answer
    consistently rather than flip-flopping between a real value and NONE
    across identical calls (observed directly against a live site)."""
    skill = _skill()
    budget = AiCallBudget(per_site_limit=10, per_run_limit=10)
    llm = _FakeLLM("A community nutrition program.")
    extract_record(FIXTURE, "https://ngo-example.org/projects/1", skill, "context", Settings(), llm, budget)

    assert llm.last_kwargs.get("temperature") == 0.1
