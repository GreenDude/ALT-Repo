from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from app.config import AppConfig, load_config
from app.gitea_client import GiteaClient, GiteaClientError
from app.llm_client import LLMClient, LLMClientError
from app.models import PullRequestRef
from app.report_writer import write_report
from app.review_service import ReviewService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RELEVANT_PR_ACTIONS = {"opened", "synchronized", "reopened"}

app = FastAPI(title="local-ai-pr-reviewer")


def get_config() -> AppConfig:
    return load_config()


def _verify_local_only(config: AppConfig) -> None:
    if not config.safety.local_only:
        return
    for endpoint in (config.llm.base_url, config.gitea.base_url):
        if "localhost" not in endpoint and "127.0.0.1" not in endpoint:
            raise RuntimeError("Configuration violates local_only safety mode")


def _build_review_service(config: AppConfig) -> ReviewService:
    _verify_local_only(config)
    return ReviewService(config=config, llm_client=LLMClient(config.llm))


def _build_gitea_client(config: AppConfig) -> GiteaClient:
    token = os.getenv(config.gitea.api_token_env)
    if not token:
        raise RuntimeError(f"Missing required environment variable: {config.gitea.api_token_env}")
    return GiteaClient(config=config.gitea, api_token=token)


def _extract_pr_ref(payload: dict[str, Any]) -> PullRequestRef:
    repository = payload.get("repository") or {}
    owner_info = repository.get("owner") or {}
    pull_request = payload.get("pull_request") or {}
    owner = owner_info.get("username") or owner_info.get("login")
    repo = repository.get("name")
    index = pull_request.get("number") or pull_request.get("index")
    if not owner or not repo or not index:
        raise ValueError("Webhook payload is missing repository owner, repository name, or pull request index")
    return PullRequestRef(owner=owner, repo=repo, index=int(index))


def _is_relevant_pull_request_event(payload: dict[str, Any]) -> bool:
    if "pull_request" not in payload:
        return False
    action = payload.get("action")
    return action in RELEVANT_PR_ACTIONS


def _verify_webhook_signature(raw_body: bytes, request: Request, config: AppConfig) -> None:
    secret_env = config.gitea.webhook_secret_env
    secret = os.getenv(secret_env)
    if not secret:
        return

    signature = request.headers.get("X-Gitea-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/gitea")
async def gitea_webhook(request: Request) -> dict[str, Any]:
    config = get_config()
    raw_body = await request.body()
    _verify_webhook_signature(raw_body, request, config)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not _is_relevant_pull_request_event(payload):
        return {"status": "ignored", "reason": "non_relevant_event"}

    try:
        pr_ref = _extract_pr_ref(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        gitea_client = _build_gitea_client(config)
        review_service = _build_review_service(config)
        diff_text = await gitea_client.fetch_pull_request_diff(pr_ref.owner, pr_ref.repo, pr_ref.index)
    except GiteaClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        review = await review_service.review_diff(diff_text)
    except LLMClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Review pipeline failed")
        raise HTTPException(status_code=500, detail="Review pipeline failed") from exc

    comment_body = f"{config.gitea.bot_marker}\n\n{review.markdown}"
    try:
        comment_response = await gitea_client.post_general_comment(
            pr_ref.owner,
            pr_ref.repo,
            pr_ref.index,
            comment_body,
        )
    except GiteaClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "status": "processed",
        "owner": pr_ref.owner,
        "repo": pr_ref.repo,
        "pull_request_index": pr_ref.index,
        "comment_id": comment_response.get("id"),
    }


async def run_manual_review(diff_path: str, config_path: str = "config.yaml") -> Path:
    config = load_config(config_path)
    review_service = _build_review_service(config)
    diff_text = Path(diff_path).read_text(encoding="utf-8")
    review = await review_service.review_diff(diff_text)
    return write_report(config.review.output_report, review.markdown)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local-ai-pr-reviewer in manual CLI mode.")
    parser.add_argument("--diff", help="Path to a diff file for manual review mode.")
    parser.add_argument("--config", default="config.yaml", help="Path to config file.")
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    if not args.diff:
        parser.print_help()
        return

    import asyncio

    output_path = asyncio.run(run_manual_review(args.diff, args.config))
    print(output_path)


if __name__ == "__main__":
    main()
