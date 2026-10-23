"""Opt-in code embedding provider adapter.

Repository text is never sent to a provider unless the operator explicitly sets
EMBEDDINGS_ALLOW_SOURCE_UPLOAD=true. Missing credentials or provider failures
degrade to lexical retrieval instead of failing indexing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings


@dataclass
class EmbeddingBatch:
    vectors: list[list[float] | None]
    status: str
    model: str | None


async def embed_code_items(texts: list[str]) -> EmbeddingBatch:
    if not texts:
        return EmbeddingBatch([], "empty", None)
    provider = settings.EMBEDDING_PROVIDER.strip().lower()
    if provider in {"", "none"}:
        return EmbeddingBatch([None] * len(texts), "disabled", None)
    if not settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD:
        return EmbeddingBatch([None] * len(texts), "disabled_by_policy", None)
    if provider == "openai" and not settings.OPENAI_API_KEY.strip():
        return EmbeddingBatch([None] * len(texts), "missing_credentials", settings.EMBEDDING_MODEL)
    if provider not in {"openai", "ollama"}:
        return EmbeddingBatch([None] * len(texts), "unsupported_provider", settings.EMBEDDING_MODEL)

    batch_size = min(max(settings.EMBEDDING_BATCH_SIZE, 1), 128)
    vectors: list[list[float] | None] = []
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                if provider == "openai":
                    response = await client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                        json={
                            "model": settings.EMBEDDING_MODEL,
                            "input": batch,
                            "dimensions": settings.EMBEDDING_DIMENSION,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()["data"]
                    data.sort(key=lambda row: row.get("index", 0))
                    vectors.extend([row["embedding"] for row in data])
                else:
                    response = await client.post(
                        settings.OLLAMA_BASE_URL.rstrip("/") + "/api/embed",
                        json={"model": settings.EMBEDDING_MODEL, "input": batch},
                    )
                    response.raise_for_status()
                    vectors.extend(response.json()["embeddings"])
        if len(vectors) != len(texts) or any(
            len(vector) != settings.EMBEDDING_DIMENSION for vector in vectors
        ):
            return EmbeddingBatch([None] * len(texts), "dimension_mismatch", settings.EMBEDDING_MODEL)
        return EmbeddingBatch(vectors, "ready", settings.EMBEDDING_MODEL)
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        # Never include request/response bodies in logs or errors; they can
        # contain source-derived text or provider metadata.
        return EmbeddingBatch([None] * len(texts), "provider_error", settings.EMBEDDING_MODEL)


def embedding_text(file_path: str, symbol: dict[str, Any]) -> str:
    """Build a bounded embedding input with enough identifying context."""
    return (
        f"File: {file_path}\n"
        f"Symbol: {symbol.get('qualified_name', '')}\n"
        f"Kind: {symbol.get('kind', '')}\n"
        f"Signature: {symbol.get('signature', '')}\n"
        f"Source:\n{symbol.get('source_text', '')}"
    )[:8000]
