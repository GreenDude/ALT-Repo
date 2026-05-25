from __future__ import annotations

import httpx
import pytest

from app.config import LLMConfig
from app.llm_client import LLMClient, LLMClientError
import app.llm_client as llm_client_module


class FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class FakeAsyncClient:
    def __init__(self, responses: list[object], timeout: httpx.Timeout) -> None:
        self._responses = responses
        self.timeout = timeout
        self.calls = 0

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict) -> FakeResponse:
        self.calls += 1
        outcome = self._responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_generate_review_retries_transport_failures_then_succeeds(monkeypatch) -> None:
    request = httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
    responses: list[object] = [
        httpx.ReadTimeout("timed out", request=request),
        httpx.ReadTimeout("timed out again", request=request),
        FakeResponse("review text"),
    ]
    fake_clients: list[FakeAsyncClient] = []
    sleeps: list[int | float] = []

    def fake_async_client(*, timeout: httpx.Timeout) -> FakeAsyncClient:
        client = FakeAsyncClient(responses, timeout)
        fake_clients.append(client)
        return client

    async def fake_sleep(delay: int | float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", fake_async_client)
    monkeypatch.setattr(llm_client_module.asyncio, "sleep", fake_sleep)

    client = LLMClient(
        LLMConfig(
            connect_timeout_seconds=10,
            read_timeout_seconds=300,
            retry_count=10,
            retry_backoff_base_seconds=1.0,
            retry_backoff_max_seconds=30.0,
        )
    )
    result = await client.generate_review("prompt")

    assert result == "review text"
    assert len(fake_clients) == 1
    assert fake_clients[0].calls == 3
    assert fake_clients[0].timeout.connect == 10
    assert fake_clients[0].timeout.read == 300
    assert sleeps == [1.0, 2.0]


@pytest.mark.asyncio
async def test_generate_review_raises_after_exhausting_retries(monkeypatch) -> None:
    request = httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
    responses: list[object] = [
        httpx.ReadTimeout("timed out", request=request),
        httpx.ReadTimeout("timed out again", request=request),
        httpx.ReadTimeout("still timed out", request=request),
    ]
    sleeps: list[int | float] = []

    def fake_async_client(*, timeout: httpx.Timeout) -> FakeAsyncClient:
        return FakeAsyncClient(responses, timeout)

    async def fake_sleep(delay: int | float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(llm_client_module.httpx, "AsyncClient", fake_async_client)
    monkeypatch.setattr(llm_client_module.asyncio, "sleep", fake_sleep)

    client = LLMClient(
        LLMConfig(
            connect_timeout_seconds=10,
            read_timeout_seconds=300,
            retry_count=2,
            retry_backoff_base_seconds=1.0,
            retry_backoff_max_seconds=30.0,
        )
    )

    with pytest.raises(LLMClientError):
        await client.generate_review("prompt")

    assert sleeps == [1.0, 2.0]


def test_retry_delay_uses_capped_exponential_backoff() -> None:
    client = LLMClient(
        LLMConfig(
            retry_backoff_base_seconds=0.5,
            retry_backoff_max_seconds=3.0,
        )
    )

    assert client._retry_delay_seconds(1) == 0.5
    assert client._retry_delay_seconds(2) == 1.0
    assert client._retry_delay_seconds(3) == 2.0
    assert client._retry_delay_seconds(4) == 3.0
    assert client._retry_delay_seconds(5) == 3.0
