from scraper_engine.config import Settings


def test_robots_txt_override_domains_defaults_empty(monkeypatch):
    monkeypatch.delenv("ROBOTS_TXT_OVERRIDE_DOMAINS", raising=False)
    assert Settings().robots_txt_override_domains == frozenset()


def test_robots_txt_override_domains_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv("ROBOTS_TXT_OVERRIDE_DOMAINS", "selfservice.adb.org, example.org ,,other.com")
    assert Settings().robots_txt_override_domains == frozenset({"selfservice.adb.org", "example.org", "other.com"})


def test_robots_txt_override_domains_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("ROBOTS_TXT_OVERRIDE_DOMAINS", "Selfservice.ADB.org")
    assert "selfservice.adb.org" in Settings().robots_txt_override_domains
