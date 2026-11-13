import httpx
import pytest

from scraper_engine import skill_builder
from scraper_engine.config import Settings


class _UnusedLLM:
    def complete(self, **kwargs):
        raise AssertionError("LLM should not be called when the page can't be fetched")


def test_build_skill_flags_needs_review_on_http_error(monkeypatch):
    def _raise(url, timeout):
        request = httpx.Request("GET", url)
        response = httpx.Response(403, request=request)
        raise httpx.HTTPStatusError("blocked", request=request, response=response)

    monkeypatch.setattr(skill_builder, "_fetch_page_text", _raise)

    skill = skill_builder.build_skill("https://blocked.example/path", "context", Settings(), _UnusedLLM())

    assert skill.needs_review is True
    assert "403" in skill.needs_review_reason
    assert skill.domain == "blocked.example"


def test_build_skill_flags_needs_review_on_connection_error(monkeypatch):
    def _raise(url, timeout):
        raise httpx.ConnectError("connection refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(skill_builder, "_fetch_page_text", _raise)

    skill = skill_builder.build_skill("https://unreachable.example", "context", Settings(), _UnusedLLM())

    assert skill.needs_review is True
    assert "unreachable.example" == skill.domain


def test_build_skill_never_sends_empty_static_content_to_the_llm(monkeypatch):
    """Static fetch returns an empty body (e.g. a JS-rendered SPA); the rendered
    fallback also comes back empty -> flag for review, never call the LLM on
    nothing and trust whatever it invents."""
    monkeypatch.setattr(skill_builder, "_fetch_page_text", lambda url, timeout: "")
    monkeypatch.setattr("scraper_engine.fetch.fetch_rendered", lambda url, settings: "<html><body></body></html>")

    skill = skill_builder.build_skill("https://spa.example/jobs", "context", Settings(), _UnusedLLM())

    assert skill.needs_review is True
    assert "no usable content" in skill.needs_review_reason


def test_build_skill_falls_back_to_rendered_fetch_when_static_is_too_thin(monkeypatch):
    monkeypatch.setattr(skill_builder, "_fetch_page_text", lambda url, timeout: "")
    rendered_html = "<html><body>" + ("Real project content. " * 50) + "</body></html>"
    monkeypatch.setattr("scraper_engine.fetch.fetch_rendered", lambda url, settings: rendered_html)

    class _RecordingLLM:
        def complete(self, **kwargs):
            assert "Real project content" in kwargs["user_content"]
            return '{"fields": {}}'

    skill = skill_builder.build_skill("https://spa.example/jobs", "context", Settings(), _RecordingLLM())

    assert skill.needs_review is False
    assert skill.fetch_method == "rendered"
