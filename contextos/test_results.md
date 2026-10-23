# ContextOS test and benchmark results

- Generated: 2026-10-23T09:26:18+00:00
- Benchmark fixture commit: `60c92fb4bc997956b6ee70540458123274702788`
- Runtime: Python 3.11.17, SQLite in-memory database
- Dataset: 5 hand-authored queries over 5 small Python source files (synthetic fixture, not a production corpus)
- External services: TypeSafe/Jev disabled; embeddings and Neo4j disabled; no source was sent externally
- Token accounting: estimates from source-text length, not a model tokenizer or billing measure
- Resume benchmark mode: deterministic fresh-consumer simulation; no LLM or code-writing agent is invoked

## Verification performed

- Backend Docker image build: passed
- pytest -q: 32 passed in 4.00 seconds (SQLite and temporary Git fixtures)
- MCP server import: passed
- npm run build: passed (Vite production build)
- Alembic upgrade head from legacy-shaped SQLite schema: passed
- alembic check: no new upgrade operations detected

## Aggregate retrieval metrics

| Profile | P@5 | Recall@5 | MRR | nDCG@5 | Correct file | Correct symbol | Provenance | Freshness | Jev used | Avg estimated tokens | Avg search latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 16.30 |
| hybrid | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 15.50 |
| jev | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 13.87 |

## Per-case retrieval

| Case | Profile | First relevant rank | Retrieved files | Estimated tokens | Jev status |
|---|---|---:|---|---:|---|
| access token validation | lexical | 1 | src/auth.py, src/routes.py, src/cache.py | 109 | not_requested |
| access token validation | hybrid | 1 | src/auth.py, src/routes.py, src/cache.py | 109 | not_requested |
| access token validation | jev | 1 | src/auth.py, src/routes.py, src/cache.py | 109 | disabled_by_policy |
| login route | lexical | 1 | src/routes.py | 22 | not_requested |
| login route | hybrid | 1 | src/routes.py | 22 | not_requested |
| login route | jev | 1 | src/routes.py | 22 | disabled_by_policy |
| token cache | lexical | 1 | src/cache.py, src/auth.py, src/routes.py | 109 | not_requested |
| token cache | hybrid | 1 | src/cache.py, src/auth.py, src/routes.py | 109 | not_requested |
| token cache | jev | 1 | src/cache.py, src/auth.py, src/routes.py | 109 | disabled_by_policy |
| incremental indexing | lexical | 1 | src/ingest.py | 24 | not_requested |
| incremental indexing | hybrid | 1 | src/ingest.py | 24 | not_requested |
| incremental indexing | jev | 1 | src/ingest.py | 24 | disabled_by_policy |
| symbol search | lexical | 1 | src/search.py | 16 | not_requested |
| symbol search | hybrid | 1 | src/search.py | 16 | not_requested |
| symbol search | jev | 1 | src/search.py | 16 | disabled_by_policy |

## Fresh-agent resume simulation

A clean consumer receives only the incoming task and the generated handoff packet; it does not receive the saved database records or prior conversation. In this offline benchmark, a resume counts as successful only when the packet contains the case's required decision/continuity markers, target path, and next action. This measures handoff sufficiency, not an LLM's ability to make code changes or pass tests.

| Handoff budget (tokens) | Resume checks passed | Success rate | Required-context coverage | Avg estimated packet tokens |
|---:|---:|---:|---:|---:|
| 128 | 0/3 | 0.000 | 0.000 | 119.0 |
| 512 | 3/3 | 1.000 | 1.000 | 445.7 |
| 1200 | 3/3 | 1.000 | 1.000 | 484.3 |

| Case | Budget | Context items recovered | Coverage | Resume check |
|---|---:|---:|---:|---|
| access-token expiry | 128 | 0/5 | 0.000 | incomplete |
| access-token expiry | 512 | 5/5 | 1.000 | pass |
| access-token expiry | 1200 | 5/5 | 1.000 | pass |
| index rollback safety | 128 | 0/5 | 0.000 | incomplete |
| index rollback safety | 512 | 5/5 | 1.000 | pass |
| index rollback safety | 1200 | 5/5 | 1.000 | pass |
| private-source policy | 128 | 0/5 | 0.000 | incomplete |
| private-source policy | 512 | 5/5 | 1.000 | pass |
| private-source policy | 1200 | 5/5 | 1.000 | pass |

- Task-only baseline (no handoff packet): 0.000 required-context coverage; 0/3 complete resume checks.
- No actual agent/model was invoked. Treat this as a deterministic test of saved-context retrieval and packet budgets, not as measured coding-agent completion accuracy.

## Interpretation

These results establish that indexing, retrieval evaluation, and task-specific context packing run end to end on reproducible local fixtures. They are not evidence of performance on a large or representative customer repository. The Jev row is a local hybrid fallback because the external scorer is intentionally disabled. Latency is a small SQLite-fixture measurement and is not comparable to production PostgreSQL/Neo4j latency.

- Cases: 5; top-k: 5; profiles: lexical, hybrid, jev.
- Benchmark run total: 230.30 ms across all cases and profiles.
- Total estimated retrieved source tokens: 840.
