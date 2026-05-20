from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    markdown: str


class PullRequestRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner: str
    repo: str
    index: int

