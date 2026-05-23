from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import GiteaConfig

logger = logging.getLogger(__name__)


class GiteaClientError(RuntimeError):
    """Raised when Gitea requests fail."""


class GiteaClient:
    def __init__(self, config: GiteaConfig, api_token: str) -> None:
        self._config = config
        self._api_token = api_token

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self._api_token}",
            "Accept": "application/json",
        }

    @staticmethod
    def _format_http_error(action: str, exc: httpx.HTTPError) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            snippet = response.text[:300].strip()
            return (
                f"{action} failed with status={response.status_code}"
                f", url={response.request.url!s}, body_snippet={snippet!r}"
            )
        if isinstance(exc, httpx.RequestError):
            return f"{action} failed for url={exc.request.url!s}: {exc!r}"
        return f"{action} failed: {exc!r}"

    async def fetch_pull_request_diff(self, owner: str, repo: str, index: int) -> str:
        url = f"{self._config.base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/pulls/{index}.diff"
        logger.info("Fetching PR diff from Gitea owner=%s repo=%s pr_index=%s url=%s", owner, repo, index, url)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception(self._format_http_error("fetch_pull_request_diff", exc))
            raise GiteaClientError("Failed to fetch pull request diff from Gitea") from exc
        logger.info(
            "Fetched PR diff from Gitea owner=%s repo=%s pr_index=%s diff_chars=%s",
            owner,
            repo,
            index,
            len(response.text),
        )
        return response.text

    async def post_general_comment(self, owner: str, repo: str, index: int, body: str) -> dict:
        url = f"{self._config.base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/issues/{index}/comments"
        payload = {"body": body}
        logger.info(
            "Posting PR comment to Gitea owner=%s repo=%s pr_index=%s url=%s comment_chars=%s",
            owner,
            repo,
            index,
            url,
            len(body),
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=self._headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception(self._format_http_error("post_general_comment", exc))
            raise GiteaClientError("Failed to post pull request comment to Gitea") from exc
        result: dict[str, Any] = response.json()
        logger.info(
            "Posted PR comment to Gitea owner=%s repo=%s pr_index=%s comment_id=%s",
            owner,
            repo,
            index,
            result.get("id"),
        )
        return result
