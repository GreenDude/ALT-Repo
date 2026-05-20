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
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Local LLM request failed")
            raise LLMClientError("Failed to call local LLM server") from exc

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.exception("Local LLM response parsing failed")
            raise LLMClientError("Local LLM response was missing review content") from exc

