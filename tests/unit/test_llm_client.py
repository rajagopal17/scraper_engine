import httpx
import pytest

from scraper_engine.config import Settings
from scraper_engine.llm.client import LLMClient, OpenAIStatusError


def test_provider_inferred_as_openai_from_base_url(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "x")
    monkeypatch.setenv("AI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    assert Settings().ai_provider == "openai"


def test_provider_defaults_to_anthropic(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "x")
    monkeypatch.setenv("AI_BASE_URL", "https://api.anthropic.com")
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    assert Settings().ai_provider == "anthropic"


def test_base_url_whitespace_is_stripped(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "x")
    monkeypatch.setenv("AI_BASE_URL", "  https://api.openai.com/v1  ")
    assert Settings().ai_base_url == "https://api.openai.com/v1"


def test_openai_complete_returns_message_content(monkeypatch):
    client = LLMClient(api_key="k", base_url="https://api.openai.com/v1", provider="openai")

    def fake_post(url, json, timeout):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]}, request=request)

    monkeypatch.setattr(client._http, "post", fake_post)
    assert client.complete(model="gpt-4o", system="s", user_content="u") == "hello"


def test_openai_401_is_not_retried(monkeypatch):
    client = LLMClient(api_key="bad", base_url="https://api.openai.com/v1", provider="openai")
    calls = {"n": 0}

    def fake_post(url, json, timeout):
        calls["n"] += 1
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(401, json={"error": "invalid key"}, request=request)

    monkeypatch.setattr(client._http, "post", fake_post)
    with pytest.raises(OpenAIStatusError):
        client.complete(model="gpt-4o", system="s", user_content="u")
    assert calls["n"] == 1  # non-retryable: only one attempt


def test_openai_temperature_omitted_by_default(monkeypatch):
    client = LLMClient(api_key="k", base_url="https://api.openai.com/v1", provider="openai")
    seen = {}

    def fake_post(url, json, timeout):
        seen["payload"] = json
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]}, request=request)

    monkeypatch.setattr(client._http, "post", fake_post)
    client.complete(model="gpt-4o", system="s", user_content="u")
    assert "temperature" not in seen["payload"]


def test_openai_temperature_passed_through_when_given(monkeypatch):
    client = LLMClient(api_key="k", base_url="https://api.openai.com/v1", provider="openai")
    seen = {}

    def fake_post(url, json, timeout):
        seen["payload"] = json
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]}, request=request)

    monkeypatch.setattr(client._http, "post", fake_post)
    client.complete(model="gpt-4o", system="s", user_content="u", temperature=0.1)
    assert seen["payload"]["temperature"] == 0.1


def test_openai_500_is_retried(monkeypatch):
    client = LLMClient(api_key="k", base_url="https://api.openai.com/v1", provider="openai")
    calls = {"n": 0}

    def fake_post(url, json, timeout):
        calls["n"] += 1
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return httpx.Response(500, json={"error": "boom"}, request=request)

    monkeypatch.setattr(client._http, "post", fake_post)
    with pytest.raises(OpenAIStatusError):
        client.complete(model="gpt-4o", system="s", user_content="u")
    assert calls["n"] == 3  # retried up to stop_after_attempt(3)
