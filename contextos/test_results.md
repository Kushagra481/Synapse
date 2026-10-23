# ContextOS test and benchmark results

- Generated: 2026-10-23T09:09:31+00:00
- Benchmark fixture commit: `805c0d052e6276548c90baa5852e9d4b7f4b0e10`
- Runtime: Python 3.11.17, SQLite in-memory database
- Dataset: 5 hand-authored queries over 5 small Python source files (synthetic fixture, not a production corpus)
- External services: TypeSafe/Jev disabled; embeddings and Neo4j disabled; no source was sent externally
- Token accounting: estimates from source-text length, not a model tokenizer or billing measure

## Verification performed

- Backend Docker image build: passed
- pytest -q: 32 passed in 4.02 seconds (SQLite and temporary local Git repositories)
- MCP server import: passed
- npm run build: passed (Vite production build)
- Alembic upgrade head from legacy-shaped SQLite schema: passed
- alembic check: no new upgrade operations detected

## Aggregate retrieval metrics

| Profile | P@5 | Recall@5 | MRR | nDCG@5 | Correct file | Correct symbol | Provenance | Freshness | Jev used | Avg estimated tokens | Avg search latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 14.30 |
| hybrid | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 15.50 |
| jev | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 14.73 |

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

## Interpretation

These results establish that the indexing and benchmark pipeline run end to end on a reproducible local fixture. They are not evidence of performance on a large or representative customer repository. The Jev row is a local hybrid fallback because the external scorer is intentionally disabled. Latency is a small SQLite-fixture measurement and is not comparable to production PostgreSQL/Neo4j latency.

- Cases: 5; top-k: 5; profiles: lexical, hybrid, jev.
- Benchmark run total: 224.49 ms across all cases and profiles.
- Total estimated retrieved source tokens: 840.
