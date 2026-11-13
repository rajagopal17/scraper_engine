from __future__ import annotations

import logging

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_RETRYABLE = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)


class LLMClient:
    """Thin native-Python wrapper around the Anthropic API.

    Any API key / base_url can be supplied (e.g. a proxy or alternate deployment
    that speaks the Anthropic Messages API), and the model used per call is a
    plain parameter so skill-build and runtime calls can use different models.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        if not api_key:
            raise ValueError("AI_API_KEY is not set")
        self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type(_RETRYABLE),
    )
    def complete(
        self,
        model: str,
        system: str,
        user_content: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        """Single-shot completion. No tool use, no multi-step agent loop by design."""
        response = self._client.messages.create(
            model=model,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": user_content}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
