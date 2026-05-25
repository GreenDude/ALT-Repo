from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import app
import app.main as main_module


class FakeGiteaClient:
    def __init__(self) -> None:
        self.posted_comments: list[tuple[str, str, int, str]] = []

    async def fetch_pull_request_diff(self, owner: str, repo: str, index: int) -> str:
        assert owner == "octo"
        assert repo == "demo"
        assert index == 7
        return "diff --git a/foo.py b/foo.py"

    async def post_general_comment(self, owner: str, repo: str, index: int, body: str) -> dict:
        self.posted_comments.append((owner, repo, index, body))
        return {"id": 123}


class FakeReviewService:
    async def review_diff(self, diff_text: str):
        assert "diff --git" in diff_text
        return type("Review", (), {"markdown": "# AI-assisted PR Review"})()


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_gitea_webhook_processes_relevant_pull_request(monkeypatch) -> None:
    fake_gitea = FakeGiteaClient()
    config = AppConfig()
    captured_coroutines: list[object] = []
    payload = {
        "action": "opened",
        "repository": {"name": "demo", "owner": {"username": "octo"}},
        "pull_request": {"number": 7},
    }

    def fake_create_task(coro):
        captured_coroutines.append(coro)
        return type("FakeTask", (), {"done": lambda self: False})()

    monkeypatch.setattr(main_module, "get_config", lambda: config)
    monkeypatch.setattr(main_module, "_verify_webhook_signature", lambda raw_body, request, cfg: None)
    monkeypatch.setattr(main_module, "_build_gitea_client", lambda cfg: fake_gitea)
    monkeypatch.setattr(main_module, "_build_review_service", lambda cfg: FakeReviewService())
    monkeypatch.setattr(main_module.asyncio, "create_task", fake_create_task)

    client = TestClient(app)
    response = client.post("/webhooks/gitea", content=json.dumps(payload))

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert not fake_gitea.posted_comments
    assert len(captured_coroutines) == 1

    asyncio.run(captured_coroutines[0])

    assert fake_gitea.posted_comments
    _, _, _, body = fake_gitea.posted_comments[0]
    assert body.startswith(config.gitea.bot_marker)
    assert "# AI-assisted PR Review" in body


def test_gitea_webhook_ignores_non_relevant_action(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "get_config", lambda: AppConfig())
    monkeypatch.setattr(main_module, "_verify_webhook_signature", lambda raw_body, request, cfg: None)
    client = TestClient(app)

    response = client.post(
        "/webhooks/gitea",
        content=json.dumps(
            {
                "action": "closed",
                "repository": {"name": "demo", "owner": {"username": "octo"}},
                "pull_request": {"number": 7},
            }
        ),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "non_relevant_event"}


def test_is_local_hostname_accepts_docker_local_hosts() -> None:
    assert main_module._is_local_hostname("localhost") is True
    assert main_module._is_local_hostname("host.docker.internal") is True
    assert main_module._is_local_hostname("gitea") is True
    assert main_module._is_local_hostname("192.168.1.15") is True


def test_is_local_hostname_rejects_public_hosts() -> None:
    assert main_module._is_local_hostname("api.openai.com") is False
