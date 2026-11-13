from __future__ import annotations

import logging

import anthropic
import httpx
from tenacity import retry, retry_if_exception, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_ANTHROPIC_RETRYABLE = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)
_HTTPX_RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)


class OpenAIStatusError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"{status_code}: {message}")
        self.status_code = status_code


def _is_retryable_openai_error(exc: BaseException) -> bool:
    if isinstance(exc, _HTTPX_RETRYABLE):
        return True
    if isinstance(exc, OpenAIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


class LLMClient:
    """Thin native-Python wrapper around either the Anthropic Messages API or the
    OpenAI-compatible Chat Completions API. Provider is picked via Settings
    (AI_PROVIDER, or inferred from AI_BASE_URL) so any API key/base_url for
    either provider (including proxies) can be plugged in without code changes.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com", provider: str = "anthropic"):
        if not api_key:
            raise ValueError("AI_API_KEY is not set")
        self.provider = provider
        if provider == "openai":
            self._http = httpx.Client(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}"})
        else:
            self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    def complete(self, model: str, system: str, user_content: str, max_tokens: int = 1024, temperature: float | None = None) -> str:
        """Single-shot completion. No tool use, no multi-step agent loop by design.

        temperature is left unset by default (provider default applies) since
        the Anthropic SDK in use here rejects the kwarg outright; pass it
        explicitly for extraction/judgment calls, where low temperature avoids
        the same prompt flip-flopping between a real answer and a refusal.
        """
        if self.provider == "openai":
            return self._complete_openai(model, system, user_content, max_tokens, temperature)
        return self._complete_anthropic(model, system, user_content, max_tokens)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(_ANTHROPIC_RETRYABLE),
    )
    def _complete_anthropic(self, model: str, system: str, user_content: str, max_tokens: int) -> str:
        response = self._client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception(_is_retryable_openai_error),
    )
    def _complete_openai(self, model: str, system: str, user_content: str, max_tokens: int, temperature: float | None) -> str:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        }
        if temperature is not None:
            payload["temperature"] = temperature
        resp = self._http.post("/chat/completions", json=payload, timeout=60)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise OpenAIStatusError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            # Non-retryable (bad key, bad request, etc.) - surface immediately.
            raise OpenAIStatusError(resp.status_code, resp.text)
        return resp.json()["choices"][0]["message"]["content"]
