import pytest
from app.services import context_pack
from app.services.context_pack import estimate_tokens


def test_token_estimator_is_positive_and_monotonic():
    assert estimate_tokens("x") >= 1
    assert estimate_tokens("abcdefgh") < estimate_tokens("abcdefghabcdefgh")


@pytest.mark.asyncio
async def test_code_source_is_not_sent_to_jev(monkeypatch):
    seen = []

    async def fake_score(task, items):
        seen.extend(items)
        return None

    monkeypatch.setattr(context_pack, "score_relevance", fake_score)
    pack = await context_pack.build_context_pack(
        repo=None,
        memory=None,
        tasks=[],
        decisions=[],
        sessions=[],
        task="update auth behavior",
        max_tokens=1000,
        code_results=[
            {
                "file_path": "src/auth.py",
                "start_line": 1,
                "end_line": 2,
                "qualified_name": "login",
                "source_text": "def login(): return 'sensitive source example'",
                "relevance_score": 1.0,
            }
        ],
    )

    assert seen == []
    assert "sensitive source example" in pack["text"]
    assert pack["items"][0]["source"]["file_path"] == "src/auth.py"
