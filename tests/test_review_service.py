from pathlib import Path

import pytest

from app.config import AppConfig
from app.review_service import ReviewService


class FakeLLMClient:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate_review(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "# AI-assisted PR Review"


@pytest.mark.asyncio
async def test_review_service_calls_llm_with_built_prompt(tmp_path: Path) -> None:
    template = tmp_path / "prompt.md"
    template.write_text("DIFF HERE\n{{DIFF}}", encoding="utf-8")
    config = AppConfig.model_validate(
        {
            "review": {
                "prompt_template": str(template),
                "max_diff_chars": 1000,
                "output_report": "output/review.md",
                "mode": "general_pr_comment",
            }
        }
    )
    fake_client = FakeLLMClient()
    service = ReviewService(config=config, llm_client=fake_client)

    result = await service.review_diff("diff body")

    assert result.markdown == "# AI-assisted PR Review"
    assert fake_client.prompts == ["DIFF HERE\ndiff body"]
