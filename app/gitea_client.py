from __future__ import annotations

import logging

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

    async def fetch_pull_request_diff(self, owner: str, repo: str, index: int) -> str:
        url = f"{self._config.base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/pulls/{index}.diff"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Failed to fetch PR diff from Gitea")
            raise GiteaClientError("Failed to fetch pull request diff from Gitea") from exc
        return response.text

    async def post_general_comment(self, owner: str, repo: str, index: int, body: str) -> dict:
        url = f"{self._config.base_url.rstrip('/')}/api/v1/repos/{owner}/{repo}/issues/{index}/comments"
        payload = {"body": body}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(url, headers=self._headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.exception("Failed to post PR comment to Gitea")
            raise GiteaClientError("Failed to post pull request comment to Gitea") from exc
        return response.json()

