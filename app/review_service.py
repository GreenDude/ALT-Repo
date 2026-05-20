from __future__ import annotations

from app.config import AppConfig
from app.diff_utils import redact_secrets, trim_diff
from app.models import ReviewResult
from app.prompt_builder import build_review_prompt


class ReviewService:
    def __init__(self, config: AppConfig, llm_client) -> None:
        self._config = config
        self._llm_client = llm_client

    async def review_diff(self, diff_text: str) -> ReviewResult:
        prepared_diff = diff_text
        if self._config.safety.redact_secrets:
            prepared_diff = redact_secrets(prepared_diff)
        prepared_diff = trim_diff(prepared_diff, self._config.review.max_diff_chars)
        prompt = build_review_prompt(self._config.review.prompt_template, prepared_diff)
        markdown = await self._llm_client.generate_review(prompt)
        return ReviewResult(markdown=markdown)

