from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "lm_studio"
    base_url: str = "http://localhost:1234/v1"
    model: str = "gemma-3-4b-it"
    temperature: float = 0.2
    connect_timeout_seconds: int = 10
    read_timeout_seconds: int = 300
    retry_count: int = 10
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_max_seconds: float = 30.0


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


ENV_OVERRIDE_MAP: dict[str, tuple[str, ...]] = {
    "LOCAL_AI_PR_REVIEWER_LLM_BASE_URL": ("llm", "base_url"),
    "LOCAL_AI_PR_REVIEWER_LLM_MODEL": ("llm", "model"),
    "LOCAL_AI_PR_REVIEWER_LLM_TEMPERATURE": ("llm", "temperature"),
    "LOCAL_AI_PR_REVIEWER_LLM_CONNECT_TIMEOUT_SECONDS": ("llm", "connect_timeout_seconds"),
    "LOCAL_AI_PR_REVIEWER_LLM_READ_TIMEOUT_SECONDS": ("llm", "read_timeout_seconds"),
    "LOCAL_AI_PR_REVIEWER_LLM_RETRY_COUNT": ("llm", "retry_count"),
    "LOCAL_AI_PR_REVIEWER_LLM_RETRY_BACKOFF_BASE_SECONDS": ("llm", "retry_backoff_base_seconds"),
    "LOCAL_AI_PR_REVIEWER_LLM_RETRY_BACKOFF_MAX_SECONDS": ("llm", "retry_backoff_max_seconds"),
    "LOCAL_AI_PR_REVIEWER_GITEA_BASE_URL": ("gitea", "base_url"),
    "LOCAL_AI_PR_REVIEWER_REVIEW_MAX_DIFF_CHARS": ("review", "max_diff_chars"),
    "LOCAL_AI_PR_REVIEWER_SAFETY_LOCAL_ONLY": ("safety", "local_only"),
}


def _parse_env_override(raw_value: str) -> Any:
    lowered = raw_value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered.isdigit():
        return int(lowered)
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def _apply_env_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(payload)
    for env_name, path in ENV_OVERRIDE_MAP.items():
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        target = merged
        for key in path[:-1]:
            nested = target.get(key)
            if not isinstance(nested, dict):
                nested = {}
                target[key] = nested
            target = nested
        target[path[-1]] = _parse_env_override(raw_value)
    return merged


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path)
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    payload = _apply_env_overrides(payload)
    return AppConfig.model_validate(payload)
