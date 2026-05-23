from __future__ import annotations

import argparse
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request

from app.config import AppConfig, load_config
from app.gitea_client import GiteaClient, GiteaClientError
from app.llm_client import LLMClient, LLMClientError
from app.models import PullRequestRef
from app.report_writer import write_report
from app.review_service import ReviewService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

RELEVANT_PR_ACTIONS = {"opened", "synchronized", "reopened"}

app = FastAPI(title="local-ai-pr-reviewer")


def get_config() -> AppConfig:
    config = load_config()
    logger.debug(
        "Loaded config llm_provider=%s llm_base_url=%s gitea_base_url=%s review_mode=%s local_only=%s redact_secrets=%s",
        config.llm.provider,
        config.llm.base_url,
        config.gitea.base_url,
        config.review.mode,
        config.safety.local_only,
        config.safety.redact_secrets,
    )
    return config


def _is_local_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
    except ValueError:
        ip = None
    if ip is not None:
        return ip.is_loopback or ip.is_private
    if "." not in normalized:
        return True
    return normalized.endswith(".local")


def _verify_local_only(config: AppConfig) -> None:
    if not config.safety.local_only:
        return
    for endpoint in (config.llm.base_url, config.gitea.base_url):
        hostname = urlparse(endpoint).hostname
        if not _is_local_hostname(hostname):
            logger.error("local_only safety check failed endpoint=%s", endpoint)
            raise RuntimeError("Configuration violates local_only safety mode")


def _build_review_service(config: AppConfig) -> ReviewService:
    _verify_local_only(config)
    return ReviewService(config=config, llm_client=LLMClient(config.llm))


def _build_gitea_client(config: AppConfig) -> GiteaClient:
    token = os.getenv(config.gitea.api_token_env)
    if not token:
        logger.error("Missing required Gitea token environment variable env_name=%s", config.gitea.api_token_env)
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
        logger.warning("Webhook secret environment variable is not set; signature verification is disabled env_name=%s", secret_env)
        return

    signature = request.headers.get("X-Gitea-Signature")
    if not signature:
        logger.warning("Missing Gitea webhook signature header")
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, digest):
        logger.warning("Invalid Gitea webhook signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    logger.debug("Gitea webhook signature verified successfully")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhooks/gitea")
async def gitea_webhook(request: Request) -> dict[str, Any]:
    config = get_config()
    raw_body = await request.body()
    logger.info(
        "Received Gitea webhook method=%s path=%s content_length=%s event_header=%s",
        request.method,
        request.url.path,
        len(raw_body),
        request.headers.get("X-Gitea-Event"),
    )
    _verify_webhook_signature(raw_body, request, config)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        logger.exception("Failed to decode webhook payload as JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    logger.info(
        "Parsed Gitea webhook payload action=%s has_pull_request=%s repository=%s",
        payload.get("action"),
        "pull_request" in payload,
        (payload.get("repository") or {}).get("full_name") or (payload.get("repository") or {}).get("name"),
    )
    if not _is_relevant_pull_request_event(payload):
        logger.info("Ignoring webhook action=%s because it is not a relevant pull request event", payload.get("action"))
        return {"status": "ignored", "reason": "non_relevant_event"}

    try:
        pr_ref = _extract_pr_ref(payload)
    except ValueError as exc:
        logger.exception("Failed to extract pull request reference from webhook payload")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Processing pull request review owner=%s repo=%s pr_index=%s", pr_ref.owner, pr_ref.repo, pr_ref.index)

    try:
        gitea_client = _build_gitea_client(config)
        review_service = _build_review_service(config)
        diff_text = await gitea_client.fetch_pull_request_diff(pr_ref.owner, pr_ref.repo, pr_ref.index)
    except GiteaClientError as exc:
        logger.exception(
            "Gitea diff fetch failed owner=%s repo=%s pr_index=%s",
            pr_ref.owner,
            pr_ref.repo,
            pr_ref.index,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception(
            "Webhook setup/runtime check failed owner=%s repo=%s pr_index=%s",
            pr_ref.owner,
            pr_ref.repo,
            pr_ref.index,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        review = await review_service.review_diff(diff_text)
    except LLMClientError as exc:
        logger.exception(
            "LLM review generation failed owner=%s repo=%s pr_index=%s",
            pr_ref.owner,
            pr_ref.repo,
            pr_ref.index,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception(
            "Review pipeline failed owner=%s repo=%s pr_index=%s",
            pr_ref.owner,
            pr_ref.repo,
            pr_ref.index,
        )
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
        logger.exception(
            "Posting PR comment failed owner=%s repo=%s pr_index=%s",
            pr_ref.owner,
            pr_ref.repo,
            pr_ref.index,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    logger.info(
        "Completed pull request review owner=%s repo=%s pr_index=%s comment_id=%s",
        pr_ref.owner,
        pr_ref.repo,
        pr_ref.index,
        comment_response.get("id"),
    )

    return {
        "status": "processed",
        "owner": pr_ref.owner,
        "repo": pr_ref.repo,
        "pull_request_index": pr_ref.index,
        "comment_id": comment_response.get("id"),
    }


async def run_manual_review(diff_path: str, config_path: str = "config.yaml") -> Path:
    config = load_config(config_path)
    logger.info("Running manual review diff_path=%s config_path=%s", diff_path, config_path)
    review_service = _build_review_service(config)
    diff_text = Path(diff_path).read_text(encoding="utf-8")
    review = await review_service.review_diff(diff_text)
    output_path = write_report(config.review.output_report, review.markdown)
    logger.info("Manual review report written output_path=%s", output_path)
    return output_path


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
