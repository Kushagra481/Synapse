import pytest
from app.core.config import settings
from app.services import jev


@pytest.mark.asyncio
async def test_jev_relevance_scores_parse_without_network(monkeypatch):
    monkeypatch.setattr(settings, "TYPESAFE_API_KEY", "local-test-only")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "answers": {
                    "item_0": {"noul": 0.91},
                    "item_1": {"noul": 0.23},
                }
            }

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers, json):
            captured.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setattr(jev.httpx, "AsyncClient", FakeClient)
    result = await jev.score_relevance(
        "Fix the auth flow",
        [
            {"kind": "decision", "content": "Use OAuth"},
            {"kind": "task", "content": "Update the login screen"},
        ],
    )

    assert result == [0.91, 0.23]
    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["payload"]["model"] == "jev-latest"
    assert captured["payload"]["questions"]["item_0"]["type"] == "noul"
