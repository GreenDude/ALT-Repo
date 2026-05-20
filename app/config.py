from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "lm_studio"
    base_url: str = "http://localhost:1234/v1"
    model: str = "gemma-3-4b-it"
    temperature: float = 0.2
    timeout_seconds: int = 120


class GiteaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://localhost:3000"
    api_token_env: str = "GITEA_TOKEN"
    webhook_secret_env: str = "GITEA_WEBHOOK_SECRET"
    bot_marker: str = "<!-- local-ai-pr-reviewer -->"


class ReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_diff_chars: int = 12000
    output_report: str = "output/review.md"
    prompt_template: str = "prompts/code_review.md"
    mode: str = "general_pr_comment"


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_only: bool = True
    redact_secrets: bool = True


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMConfig = Field(default_factory=LLMConfig)
    gitea: GiteaConfig = Field(default_factory=GiteaConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(payload)
