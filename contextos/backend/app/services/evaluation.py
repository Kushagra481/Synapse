"""Deterministic metrics for comparing retrieval profiles on saved cases."""
from __future__ import annotations

import time
import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_index import RepositoryIndexState
from app.models.evaluation import RetrievalEvalCase, RetrievalEvalRun
from app.services.repository_index import search_code


def _normalized(values: list[str]) -> set[str]:
    return {value.strip().lower().replace("\\", "/") for value in values if value and value.strip()}


def _case_metrics(case: RetrievalEvalCase, results: list[dict[str, Any]], top_k: int) -> dict[str, float]:
    expected_files = _normalized(case.expected_files)
    expected_symbols = _normalized(case.expected_symbols)
    relevant: list[bool] = []
    for result in results[:top_k]:
        file_path = str(result.get("file_path", "")).lower().replace("\\", "/")
        symbol = str(result.get("symbol", "")).lower()
        qualified = str(result.get("qualified_name", "")).lower()
        relevant.append(
            file_path in expected_files
            or symbol in expected_symbols
            or qualified in expected_symbols
        )
    expected_count = max(len(expected_files), len(expected_symbols))
    relevant_count = sum(relevant)
    reciprocal_rank = next(
        (1.0 / rank for rank, is_relevant in enumerate(relevant, start=1) if is_relevant),
        0.0,
    )
    dcg = sum(1.0 / math.log2(rank + 1) for rank, hit in enumerate(relevant, start=1) if hit)
    ideal_count = min(expected_count, top_k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    has_provenance = sum(
        bool(row.get("file_path") and row.get("start_line") and row.get("end_line"))
        for row in results[:top_k]
    )
    verified_freshness = sum(
        row.get("freshness") in {"file_matches_working_tree", "file_matches_newer_commit"}
        for row in results[:top_k]
    )
    return {
        "precision_at_k": relevant_count / top_k,
        "recall_at_k": relevant_count / expected_count if expected_count else 0.0,
        "mrr": reciprocal_rank,
        "ndcg_at_k": dcg / idcg if idcg else 0.0,
        "correct_file": float(any(row.get("file_path", "").lower().replace("\\", "/") in expected_files for row in results[:top_k])),
        "correct_symbol": float(any(
            row.get("symbol", "").lower() in expected_symbols
            or row.get("qualified_name", "").lower() in expected_symbols
            for row in results[:top_k]
        )),
        "provenance_coverage": has_provenance / top_k,
        "freshness_coverage": verified_freshness / top_k,
        "jev_used": 0.0,
        "estimated_tokens": sum(max(1, (len(row.get("source_text", "")) + 3) // 4) for row in results[:top_k]),
    }


async def run_retrieval_benchmark(
    db: AsyncSession, repository_id: str, profiles: list[str], top_k: int
) -> RetrievalEvalRun:
    cases = (
        await db.scalars(
            select(RetrievalEvalCase)
            .where(RetrievalEvalCase.repository_id == repository_id, RetrievalEvalCase.enabled.is_(True))
            .order_by(RetrievalEvalCase.created_at.asc())
        )
    ).all()
    if not cases:
        raise ValueError("Add at least one enabled benchmark case before running an evaluation.")

    started = time.perf_counter()
    per_case: list[dict[str, Any]] = []
    metric_values: dict[str, list[dict[str, float]]] = {profile: [] for profile in profiles}
    for case in cases:
        for profile in profiles:
            result = await search_code(
                db,
                repository_id,
                case.query,
                limit=top_k,
                ranking_profile=profile,
            )
            metrics = _case_metrics(case, result["results"], top_k)
            metrics["retrieval_latency_ms"] = result["retrieval"]["latency_ms"]
            metrics["jev_used"] = float(result["retrieval"].get("jev_used", False))
            metric_values[profile].append(metrics)
            per_case.append(
                {
                    "case_id": case.id,
                    "case_name": case.name,
                    "query": case.query,
                    "profile": profile,
                    "metrics": metrics,
                    "retrieval": result["retrieval"],
                    "retrieved": [
                        {
                            "file_path": row["file_path"],
                            "symbol": row["symbol"],
                            "qualified_name": row["qualified_name"],
                            "start_line": row["start_line"],
                            "end_line": row["end_line"],
                            "relevance_score": row["relevance_score"],
                            "freshness": row["freshness"],
                        }
                        for row in result["results"][:top_k]
                    ],
                }
            )

    def average(items: list[dict[str, float]], key: str) -> float:
        return round(sum(item[key] for item in items) / max(len(items), 1), 4)

    aggregate = {
        profile: {
            key: average(values, key)
            for key in (
                "precision_at_k",
                "recall_at_k",
                "mrr",
                "ndcg_at_k",
                "correct_file",
                "correct_symbol",
                "provenance_coverage",
                "freshness_coverage",
                "jev_used",
                "estimated_tokens",
                "retrieval_latency_ms",
            )
        }
        for profile, values in metric_values.items()
    }
    index = await db.get(RepositoryIndexState, repository_id)
    run = RetrievalEvalRun(
        repository_id=repository_id,
        index_commit_sha=index.indexed_commit_sha if index else None,
        case_count=len(cases),
        top_k=top_k,
        profiles=profiles,
        metrics=aggregate,
        case_results=per_case,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        estimated_tokens=sum(row["metrics"]["estimated_tokens"] for row in per_case),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run
