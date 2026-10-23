"""Run a deterministic, local-only ContextOS retrieval benchmark.

The script creates a disposable Git repository, indexes it through the real
repository-index service, runs saved evaluation cases through the production
retrieval/evaluation services, and writes a Markdown report. It does not call
TypeSafe, an embedding provider, Neo4j, or PostgreSQL.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from git import Repo
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("APP_ENV", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models import Base, Repository, RetrievalEvalCase  # noqa: E402
from app.services.evaluation import run_retrieval_benchmark  # noqa: E402
from app.services.repository_index import index_repository  # noqa: E402


FIXTURE_FILES = {
    "src/__init__.py": "",
    "src/auth.py": (
        "class AuthService:\n"
        "    def verify_access_token(self, token: str) -> bool:\n"
        "        return bool(token)\n"
    ),
    "src/routes.py": (
        "from src.auth import AuthService\n\n"
        "def login_route(token: str) -> bool:\n"
        "    return AuthService().verify_access_token(token)\n"
    ),
    "src/cache.py": (
        "class TokenCache:\n"
        "    def save_token(self, key: str, token: str) -> None:\n"
        "        return None\n"
    ),
    "src/ingest.py": (
        "def incremental_index_repository(changed_files: list[str]) -> int:\n"
        "    return len(changed_files)\n"
    ),
    "src/search.py": (
        "def search_symbols(query: str) -> list[str]:\n"
        "    return [query]\n"
    ),
}

CASES = [
    {
        "name": "access token validation",
        "query": "Where is access token validation implemented?",
        "expected_files": ["src/auth.py"],
        "expected_symbols": ["verify_access_token"],
    },
    {
        "name": "login route",
        "query": "Find the route handling login requests",
        "expected_files": ["src/routes.py"],
        "expected_symbols": ["login_route"],
    },
    {
        "name": "token cache",
        "query": "Where is the token cache save function used?",
        "expected_files": ["src/cache.py"],
        "expected_symbols": ["save_token"],
    },
    {
        "name": "incremental indexing",
        "query": "Where does incremental repository indexing happen?",
        "expected_files": ["src/ingest.py"],
        "expected_symbols": ["incremental_index_repository"],
    },
    {
        "name": "symbol search",
        "query": "Find the implementation that searches symbols",
        "expected_files": ["src/search.py"],
        "expected_symbols": ["search_symbols"],
    },
]


def create_fixture(root: Path) -> str:
    repository = Repo.init(root)
    with repository.config_writer() as config:
        config.set_value("user", "name", "ContextOS benchmark")
        config.set_value("user", "email", "benchmark@example.invalid")
    for relative_path, content in FIXTURE_FILES.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    repository.index.add(list(FIXTURE_FILES))
    repository.index.commit("Create deterministic ContextOS benchmark fixture")
    return repository.head.commit.hexsha


def markdown_report(run, commit_sha: str, verifications: list[str]) -> str:
    lines = [
        "# ContextOS test and benchmark results",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Benchmark fixture commit: `{commit_sha}`",
        f"- Runtime: Python {platform.python_version()}, SQLite in-memory database",
        "- Dataset: 5 hand-authored queries over 5 small Python source files (synthetic fixture, not a production corpus)",
        "- External services: TypeSafe/Jev disabled; embeddings and Neo4j disabled; no source was sent externally",
        "- Token accounting: estimates from source-text length, not a model tokenizer or billing measure",
        "",
        "## Verification performed",
        "",
    ]
    if verifications:
        lines.extend(f"- {item}" for item in verifications)
    else:
        lines.append("- No additional verification commands were supplied to the benchmark runner.")
    lines.extend(
        [
            "",
            "## Aggregate retrieval metrics",
            "",
            "| Profile | P@5 | Recall@5 | MRR | nDCG@5 | Correct file | Correct symbol | Provenance | Freshness | Jev used | Avg estimated tokens | Avg search latency (ms) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for profile in run.profiles:
        metrics = run.metrics[profile]
        lines.append(
            "| {profile} | {precision:.3f} | {recall:.3f} | {mrr:.3f} | {ndcg:.3f} | "
            "{file:.3f} | {symbol:.3f} | {prov:.3f} | {fresh:.3f} | {jev:.3f} | "
            "{tokens:.1f} | {latency:.2f} |".format(
                profile=profile,
                precision=metrics["precision_at_k"],
                recall=metrics["recall_at_k"],
                mrr=metrics["mrr"],
                ndcg=metrics["ndcg_at_k"],
                file=metrics["correct_file"],
                symbol=metrics["correct_symbol"],
                prov=metrics["provenance_coverage"],
                fresh=metrics["freshness_coverage"],
                jev=metrics["jev_used"],
                tokens=metrics["estimated_tokens"],
                latency=metrics["retrieval_latency_ms"],
            )
        )
    lines.extend(
        [
            "",
            "## Per-case retrieval",
            "",
            "| Case | Profile | First relevant rank | Retrieved files | Estimated tokens | Jev status |",
            "|---|---|---:|---|---:|---|",
        ]
    )
    for case_result in run.case_results:
        expected = next(case for case in CASES if case["name"] == case_result["case_name"])
        expected_files = {value.lower() for value in expected["expected_files"]}
        expected_symbols = {value.lower() for value in expected["expected_symbols"]}
        first_rank = next(
            (
                rank
                for rank, item in enumerate(case_result["retrieved"], start=1)
                if item["file_path"].lower() in expected_files
                or item["symbol"].lower() in expected_symbols
                or item["qualified_name"].lower() in expected_symbols
            ),
            None,
        )
        files = ", ".join(dict.fromkeys(item["file_path"] for item in case_result["retrieved"])) or "—"
        lines.append(
            f"| {case_result['case_name']} | {case_result['profile']} | "
            f"{first_rank if first_rank is not None else '—'} | {files} | "
            f"{case_result['metrics']['estimated_tokens']:.0f} | "
            f"{case_result['retrieval'].get('jev_status', 'not requested')} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "These results establish that the indexing and benchmark pipeline run end to end on a reproducible local fixture. They are not evidence of performance on a large or representative customer repository. The Jev row is a local hybrid fallback because the external scorer is intentionally disabled. Latency is a small SQLite-fixture measurement and is not comparable to production PostgreSQL/Neo4j latency.",
            "",
            f"- Cases: {run.case_count}; top-k: {run.top_k}; profiles: {', '.join(run.profiles)}.",
            f"- Benchmark run total: {run.latency_ms:.2f} ms across all cases and profiles.",
            f"- Total estimated retrieved source tokens: {run.estimated_tokens}.",
            "",
        ]
    )
    return "\n".join(lines)


async def run(output_path: Path, verifications: list[str]) -> dict:
    saved_settings = {
        "APP_ENV": settings.APP_ENV,
        "GRAPH_SYNC_ENABLED": settings.GRAPH_SYNC_ENABLED,
        "EMBEDDINGS_ALLOW_SOURCE_UPLOAD": settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD,
        "JEV_ALLOW_SOURCE_UPLOAD": settings.JEV_ALLOW_SOURCE_UPLOAD,
        "TYPESAFE_API_KEY": settings.TYPESAFE_API_KEY,
        "REPO_ALLOWED_ROOTS": settings.REPO_ALLOWED_ROOTS,
    }
    settings.APP_ENV = "test"
    settings.GRAPH_SYNC_ENABLED = False
    settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD = False
    settings.JEV_ALLOW_SOURCE_UPLOAD = False
    settings.TYPESAFE_API_KEY = ""

    try:
        with tempfile.TemporaryDirectory(prefix="contextos-benchmark-") as temp_dir:
            fixture_root = Path(temp_dir) / "fixture"
            fixture_root.mkdir()
            commit_sha = create_fixture(fixture_root)
            settings.REPO_ALLOWED_ROOTS = temp_dir

            engine = create_async_engine("sqlite+aiosqlite:///:memory:")
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                async with session_factory() as db:
                    repository = Repository(
                        name="contextos-benchmark-fixture",
                        owner_subject="benchmark",
                        local_path=str(fixture_root),
                        default_branch="main",
                    )
                    db.add(repository)
                    await db.commit()
                    await db.refresh(repository)
                    repository_id = repository.id
                    for case_data in CASES:
                        db.add(
                            RetrievalEvalCase(
                                repository_id=repository_id,
                                **case_data,
                            )
                        )
                    await db.commit()

                    index_summary = await index_repository(db, repository)
                    run_record = await run_retrieval_benchmark(
                        db, repository_id, ["lexical", "hybrid", "jev"], top_k=5
                    )
                    report = markdown_report(run_record, commit_sha, verifications)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(report, encoding="utf-8")
                    return {
                        "report": str(output_path),
                        "repository_id": repository_id,
                        "index": index_summary,
                        "run_id": run_record.id,
                        "metrics": run_record.metrics,
                        "cases": run_record.case_results,
                        "report_text": report,
                    }
            finally:
                await engine.dispose()
    finally:
        for key, value in saved_settings.items():
            setattr(settings, key, value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "test_results.md",
        help="Markdown file to write (default: contextos/test_results.md)",
    )
    parser.add_argument(
        "--verification",
        action="append",
        default=[],
        help="Already-run verification to record; repeat for multiple checks.",
    )
    args = parser.parse_args()
    result = asyncio.run(run(args.output, args.verification))
    print(json.dumps({key: value for key, value in result.items() if key != "report_text"}, indent=2))


if __name__ == "__main__":
    main()
