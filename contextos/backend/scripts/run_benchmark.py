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
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path

from git import Repo
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("APP_ENV", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Decision,
    DecisionCategory,
    DecisionStatus,
    Repository,
    RetrievalEvalCase,
    Session,
    SessionStatus,
    Task,
    TaskPriority,
    TaskStatus,
)
from app.services.context_pack import build_context_pack  # noqa: E402
from app.services.evaluation import run_retrieval_benchmark  # noqa: E402
from app.services.repository_index import index_repository, search_code  # noqa: E402


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

RESUME_CASES = [
    {
        "name": "access-token expiry",
        "task": "Resume the unfinished access-token expiry work and its regression coverage.",
        "summary": "Access-token verification currently rejects empty tokens but does not check expiry.",
        "decision": "Keep the verifier's boolean return contract; expired tokens must be rejected.",
        "next_step": "Add expiry_seconds validation in verify_access_token and test expired plus valid tokens.",
        "file": "src/auth.py",
        "markers": ["boolean return contract", "expired tokens must be rejected", "expiry_seconds"],
    },
    {
        "name": "index rollback safety",
        "task": "Continue the incremental indexing work without losing the previous good snapshot.",
        "summary": "Incremental refresh parses changed files; a failed refresh must retain the last-good index.",
        "decision": "Do not replace the last-good index until every changed file has parsed successfully.",
        "next_step": "Add a failed-refresh regression test in src/ingest.py for last-good index preservation.",
        "file": "src/ingest.py",
        "markers": ["last-good index", "parsed successfully", "failed-refresh regression test"],
    },
    {
        "name": "private-source policy",
        "task": "Resume the privacy review for optional code reranking and keep source local by default.",
        "summary": "Jev code reranking is optional and the default policy keeps source snippets local.",
        "decision": "Only send source when JEV_ALLOW_SOURCE_UPLOAD is explicitly enabled.",
        "next_step": "Add a test for the default source-upload policy in backend/tests/api/test_repository_index.py.",
        "file": "backend/tests/api/test_repository_index.py",
        "markers": ["JEV_ALLOW_SOURCE_UPLOAD", "source snippets local", "default source-upload policy"],
    },
]

RESUME_BUDGETS = [128, 512, 1200]


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


def markdown_report(
    run, resume_results: list[dict], resume_summary: dict, commit_sha: str, verifications: list[str]
) -> str:
    lines = [
        "# ContextOS test and benchmark results",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Benchmark fixture commit: `{commit_sha}`",
        f"- Runtime: Python {platform.python_version()}, SQLite in-memory database",
        "- Dataset: 5 hand-authored queries over 5 small Python source files (synthetic fixture, not a production corpus)",
        "- External services: TypeSafe/Jev disabled; embeddings and Neo4j disabled; no source was sent externally",
        "- Token accounting: estimates from source-text length, not a model tokenizer or billing measure",
            "- Resume benchmark mode: deterministic fresh-consumer simulation; no LLM or code-writing agent is invoked",
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
            "## Fresh-agent resume simulation",
            "",
            "A clean consumer receives only the incoming task and the generated handoff packet; it does not receive the saved database records or prior conversation. In this offline benchmark, a resume counts as successful only when the packet contains the case's required decision/continuity markers, target path, and next action. This measures handoff sufficiency, not an LLM's ability to make code changes or pass tests.",
            "",
            "| Handoff budget (tokens) | Resume checks passed | Success rate | Required-context coverage | Avg estimated packet tokens |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for budget in RESUME_BUDGETS:
        summary = resume_summary[str(budget)]
        lines.append(
            f"| {budget} | {summary['success_count']}/{summary['case_count']} | "
            f"{summary['resume_success_rate']:.3f} | {summary['context_coverage']:.3f} | "
            f"{summary['estimated_tokens']:.1f} |"
        )
    lines.extend(
        [
            "",
            "| Case | Budget | Context items recovered | Coverage | Resume check |",
            "|---|---:|---:|---:|---|",
        ]
    )
    for result in resume_results:
        lines.append(
            f"| {result['case_name']} | {result['budget_tokens']} | "
            f"{result['recovered_items']}/{result['required_items']} | "
            f"{result['context_coverage']:.3f} | "
            f"{'pass' if result['resume_success'] else 'incomplete'} |"
        )
    baseline = resume_summary["task_only_baseline"]
    lines.extend(
        [
            "",
            f"- Task-only baseline (no handoff packet): {baseline['context_coverage']:.3f} required-context coverage; "
            f"{baseline['success_count']}/{baseline['case_count']} complete resume checks.",
            "- No actual agent/model was invoked. Treat this as a deterministic test of saved-context retrieval and packet budgets, not as measured coding-agent completion accuracy.",
        ]
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "These results establish that indexing, retrieval evaluation, and task-specific context packing run end to end on reproducible local fixtures. They are not evidence of performance on a large or representative customer repository. The Jev row is a local hybrid fallback because the external scorer is intentionally disabled. Latency is a small SQLite-fixture measurement and is not comparable to production PostgreSQL/Neo4j latency.",
            "",
            f"- Cases: {run.case_count}; top-k: {run.top_k}; profiles: {', '.join(run.profiles)}.",
            f"- Benchmark run total: {run.latency_ms:.2f} ms across all cases and profiles.",
            f"- Total estimated retrieved source tokens: {run.estimated_tokens}.",
            "",
        ]
    )
    return "\n".join(lines)


async def run_resume_benchmark(db, repository: Repository) -> tuple[list[dict], dict]:
    """Measure whether a clean consumer can recover required state from a handoff packet."""
    await db.refresh(repository)
    repository_id = repository.id
    repository_context = SimpleNamespace(
        name=repository.name,
        description=repository.description,
        local_path=repository.local_path,
        default_branch=repository.default_branch,
        language=repository.language,
        updated_at=repository.updated_at,
    )
    results: list[dict] = []
    baseline_coverages: list[float] = []

    for case in RESUME_CASES:
        task_row = Task(
            repository_id=repository_id,
            title=f"Resume: {case['name']}",
            description=case["task"],
            status=TaskStatus.ACTIVE,
            priority=TaskPriority.HIGH,
        )
        decision_row = Decision(
            repository_id=repository_id,
            title=f"Constraint: {case['name']}",
            context=case["summary"],
            decision=case["decision"],
            rationale="Preserve the previously agreed behavior while completing the open task.",
            status=DecisionStatus.ACCEPTED,
            category=DecisionCategory.PROCESS,
        )
        session_row = Session(
            repository_id=repository_id,
            llm_provider="benchmark-fixture",
            llm_model="deterministic-handoff-probe",
            status=SessionStatus.COMPLETED,
            objective=case["task"],
            summary=case["summary"],
            conversation_summary=case["summary"],
            files_modified=[case["file"]],
            decisions_made=[case["decision"]],
            next_steps=[case["next_step"]],
        )
        db.add_all([task_row, decision_row, session_row])
        await db.flush()

        code_search = await search_code(db, repository_id, case["task"], limit=3)
        task_only_text = f"# Incoming task\n{case['task']}"
        required_items = case["markers"] + [case["file"], case["next_step"]]
        baseline_found = sum(
            item.lower() in task_only_text.lower() for item in required_items
        )
        baseline_coverages.append(baseline_found / len(required_items))
        for budget in RESUME_BUDGETS:
            packet = await build_context_pack(
                repo=repository_context,
                memory=None,
                tasks=[task_row],
                decisions=[decision_row],
                sessions=[session_row],
                task=case["task"],
                max_tokens=budget,
                code_results=code_search["results"],
                retrieval_metadata=code_search["retrieval"],
            )
            # The simulated fresh consumer gets only these two strings. Expected
            # markers remain evaluator-side and are not part of its input.
            fresh_consumer_input = {
                "task": case["task"],
                "handoff_packet": packet["text"],
            }
            visible_context = (
                fresh_consumer_input["task"] + "\n" + fresh_consumer_input["handoff_packet"]
            ).lower()
            recovered = sum(item.lower() in visible_context for item in required_items)
            coverage = recovered / len(required_items)
            results.append(
                {
                    "case_name": case["name"],
                    "budget_tokens": budget,
                    "required_items": len(required_items),
                    "recovered_items": recovered,
                    "context_coverage": coverage,
                    "resume_success": recovered == len(required_items),
                    "estimated_tokens": packet["estimated_tokens"],
                    "included_items": packet["included_items"],
                }
            )

    summary = {}
    for budget in RESUME_BUDGETS:
        batch = [row for row in results if row["budget_tokens"] == budget]
        summary[str(budget)] = {
            "case_count": len(batch),
            "success_count": sum(row["resume_success"] for row in batch),
            "resume_success_rate": (
                sum(row["resume_success"] for row in batch) / len(batch) if batch else 0.0
            ),
            "context_coverage": (
                sum(row["context_coverage"] for row in batch) / len(batch) if batch else 0.0
            ),
            "estimated_tokens": (
                sum(row["estimated_tokens"] for row in batch) / len(batch) if batch else 0.0
            ),
        }
    summary["task_only_baseline"] = {
        "case_count": len(baseline_coverages),
        "success_count": sum(score == 1.0 for score in baseline_coverages),
        "context_coverage": (
            sum(baseline_coverages) / len(baseline_coverages) if baseline_coverages else 0.0
        ),
    }
    return results, summary


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
                    resume_results, resume_summary = await run_resume_benchmark(db, repository)
                    run_record = await run_retrieval_benchmark(
                        db, repository_id, ["lexical", "hybrid", "jev"], top_k=5
                    )
                    report = markdown_report(
                        run_record, resume_results, resume_summary, commit_sha, verifications
                    )
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(report, encoding="utf-8")
                    return {
                        "report": str(output_path),
                        "repository_id": repository_id,
                        "index": index_summary,
                        "run_id": run_record.id,
                        "metrics": run_record.metrics,
                        "resume_summary": resume_summary,
                        "resume_results": resume_results,
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
    print(json.dumps(
        {key: value for key, value in result.items() if key not in {"report_text", "cases", "resume_results"}},
        indent=2,
    ))


if __name__ == "__main__":
    main()
