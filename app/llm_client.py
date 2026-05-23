from __future__ import annotations

import logging

import httpx

from app.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """Raised when the local LLM request fails."""


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    async def generate_review(self, prompt: str) -> str:
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._config.temperature,
        }
        logger.info(
            "Sending review request to local LLM provider=%s model=%s url=%s prompt_chars=%s temperature=%s timeout_seconds=%s",
            self._config.provider,
            self._config.model,
            url,
            len(prompt),
            self._config.temperature,
            self._config.timeout_seconds,
        )
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                snippet = exc.response.text[:300].strip()
                logger.exception(
                    "Local LLM request failed status=%s url=%s body_snippet=%r",
                    exc.response.status_code,
                    exc.request.url,
                    snippet,
                )
            elif isinstance(exc, httpx.RequestError):
                logger.exception("Local LLM request transport failure url=%s error=%r", exc.request.url, exc)
            else:
                logger.exception("Local LLM request failed error=%r", exc)
            raise LLMClientError("Failed to call local LLM server") from exc

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.exception("Local LLM response parsing failed response_keys=%s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
            raise LLMClientError("Local LLM response was missing review content") from exc
        logger.info(
            "Received review from local LLM model=%s response_chars=%s",
            self._config.model,
            len(content),
        )
        return content
