from __future__ import annotations

import logging

from app.config import AppConfig
from app.diff_utils import redact_secrets, trim_diff
from app.models import ReviewResult
from app.prompt_builder import build_review_prompt

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, config: AppConfig, llm_client) -> None:
        self._config = config
        self._llm_client = llm_client

    async def review_diff(self, diff_text: str) -> ReviewResult:
        logger.info(
            "Preparing diff for review original_diff_chars=%s redact_secrets=%s max_diff_chars=%s",
            len(diff_text),
            self._config.safety.redact_secrets,
            self._config.review.max_diff_chars,
        )
        prepared_diff = diff_text
        if self._config.safety.redact_secrets:
            prepared_diff = redact_secrets(prepared_diff)
        prepared_diff = trim_diff(prepared_diff, self._config.review.max_diff_chars)
        logger.info(
            "Prepared diff for review prepared_diff_chars=%s prompt_template=%s",
            len(prepared_diff),
            self._config.review.prompt_template,
        )
        prompt = build_review_prompt(self._config.review.prompt_template, prepared_diff)
        logger.info("Built review prompt prompt_chars=%s", len(prompt))
        markdown = await self._llm_client.generate_review(prompt)
        logger.info("Review generation completed markdown_chars=%s", len(markdown))
        return ReviewResult(markdown=markdown)
