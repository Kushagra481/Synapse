"""Optional TypeSafe Jev adapter used for relevance scoring, never text generation."""
from __future__ import annotations
import os
from typing import Any
import httpx
from app.core.config import settings

API_URL = "https://api.typesafe.ai/v1/systemone"


async def score_relevance(task: str, items: list[dict[str, Any]]) -> list[float] | None:
    """Return per-item 0..1 relevance probabilities, or None to use local ranking."""
    key = (settings.TYPESAFE_API_KEY or os.getenv("TYPESAFE_API_KEY", "")).strip()
    if not key or not items:
        return None
    safe_items = items[:32]
    state = "Coding task:\n" + task[:3000] + "\n\nCandidate context items:\n"
    questions = {}
    for index, item in enumerate(safe_items):
        name = f"item_{index}"
        content = str(item.get("content", ""))[:1800]
        state += f"\n[{name}] {item.get('kind', 'memory')}: {content}"
        questions[name] = {
            "type": "noul",
            "instructions": "This saved project context is materially useful for completing the coding task. Judge relevance, not whether the text is generally important.",
        }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(API_URL, headers={"Authorization": f"Bearer {key}"}, json={"model": "jev-latest", "state": state, "questions": questions})
            response.raise_for_status()
            answers = response.json().get("answers", {})
            return [float(answers.get(f"item_{i}", {}).get("noul", 0.0)) for i in range(len(safe_items))]
    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
        return None
