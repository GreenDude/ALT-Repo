from __future__ import annotations

import asyncio
import logging

import httpx

from app.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClientError(RuntimeError):
    """Raised when the local LLM request fails."""


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    def _retry_delay_seconds(self, attempt: int) -> float:
        base_delay = self._config.retry_backoff_base_seconds
        max_delay = self._config.retry_backoff_max_seconds
        return min(base_delay * (2 ** max(attempt - 1, 0)), max_delay)

    async def generate_review(self, prompt: str) -> str:
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self._config.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._config.temperature,
        }
        logger.info(
            "Sending review request to local LLM provider=%s model=%s url=%s prompt_chars=%s temperature=%s connect_timeout_seconds=%s read_timeout_seconds=%s retry_count=%s",
            self._config.provider,
            self._config.model,
            url,
            len(prompt),
            self._config.temperature,
            self._config.connect_timeout_seconds,
            self._config.read_timeout_seconds,
            self._config.retry_count,
        )
        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_seconds,
            read=self._config.read_timeout_seconds,
            write=self._config.read_timeout_seconds,
            pool=self._config.connect_timeout_seconds,
        )
        total_attempts = self._config.retry_count + 1

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for attempt in range(1, total_attempts + 1):
                    try:
                        response = await client.post(url, json=payload)
                        response.raise_for_status()
                        break
                    except httpx.HTTPStatusError as exc:
                        snippet = exc.response.text[:300].strip()
                        logger.exception(
                            "Local LLM request failed status=%s url=%s body_snippet=%r attempt=%s total_attempts=%s",
                            exc.response.status_code,
                            exc.request.url,
                            snippet,
                            attempt,
                            total_attempts,
                        )
                        raise LLMClientError("Failed to call local LLM server") from exc
                    except httpx.RequestError as exc:
                        if attempt >= total_attempts:
                            logger.exception(
                                "Local LLM request transport failure url=%s error=%r attempt=%s total_attempts=%s",
                                exc.request.url,
                                exc,
                                attempt,
                                total_attempts,
                            )
                            raise LLMClientError("Failed to call local LLM server") from exc
                        delay = self._retry_delay_seconds(attempt)
                        logger.warning(
                            "Retrying local LLM request after transport failure url=%s error=%r attempt=%s total_attempts=%s retry_delay_seconds=%s",
                            exc.request.url,
                            exc,
                            attempt,
                            total_attempts,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    except httpx.HTTPError as exc:
                        logger.exception("Local LLM request failed error=%r attempt=%s total_attempts=%s", exc, attempt, total_attempts)
                        raise LLMClientError("Failed to call local LLM server") from exc
        except LLMClientError:
            raise

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
