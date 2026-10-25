# ContextOS test and benchmark results

- Generated: 2026-10-25T17:12:38+00:00
- Benchmark fixture commit: `ec75fcec062b1547a7c0e573eeb5fb59b086b226`
- Runtime: Python 3.11.17, SQLite in-memory database
- Dataset: 5 hand-authored queries over 5 small Python source files (synthetic fixture, not a production corpus)
- External services: TypeSafe/Jev disabled; embeddings and Neo4j disabled; no source was sent externally
- Token accounting: estimates from source-text length, not a model tokenizer or billing measure
- Resume benchmark mode: deterministic_simulation; raw runner output and command are not written to this report

## Verification performed

- Backend Docker image build: passed with production Uvicorn command
- pytest -q: 38 passed in 6.08 seconds; includes auth test-mode guard, optional graph startup, config defaults, and project-role authorization
- npm run build: passed (Vite production build)
- MCP server import: passed
- Benchmark CLI help: passed
- Alembic upgrade head: passed from legacy schema and create_all bootstrap; owners backfilled
- alembic check: no new upgrade operations detected on both SQLite paths

## Aggregate retrieval metrics

| Profile | P@5 | Recall@5 | MRR | nDCG@5 | Correct file | Correct symbol | Provenance | Freshness | Jev used | Avg estimated tokens | Avg search latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lexical | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 13.27 |
| hybrid | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 13.87 |
| jev | 0.280 | 1.000 | 1.000 | 0.814 | 1.000 | 1.000 | 0.520 | 0.520 | 0.000 | 56.0 | 13.33 |

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

## Fresh-agent resume evaluation

Each fresh consumer receives only the incoming task and generated handoff packet; it does not receive saved database records or the prior conversation. Resume success requires recovery of task state, recorded decisions, changed/target files, and next actions. The default deterministic mode checks packet sufficiency only. An optional command adapter accepts a model/agent runner that reads the JSON input contract and returns structured fields; this evaluates actual agent recall but still does not execute code changes or tests.

| Handoff budget (tokens) | Resume checks passed | Success rate | Required-context coverage | Avg packet tokens | Avg agent runtime (ms) |
|---:|---:|---:|---:|---:|---:|
| 128 | 0/3 | 0.000 | 0.000 | 119.0 | — |
| 512 | 3/3 | 1.000 | 1.000 | 445.7 | — |
| 1200 | 3/3 | 1.000 | 1.000 | 484.3 | — |

| Case | Budget | Context items recovered | Coverage | Resume check | Agent status |
|---|---:|---:|---:|---|---|
| access-token expiry | 128 | 0/6 | 0.000 | incomplete | simulation |
| access-token expiry | 512 | 6/6 | 1.000 | pass | simulation |
| access-token expiry | 1200 | 6/6 | 1.000 | pass | simulation |
| index rollback safety | 128 | 0/6 | 0.000 | incomplete | simulation |
| index rollback safety | 512 | 6/6 | 1.000 | pass | simulation |
| index rollback safety | 1200 | 6/6 | 1.000 | pass | simulation |
| private-source policy | 128 | 0/6 | 0.000 | incomplete | simulation |
| private-source policy | 512 | 6/6 | 1.000 | pass | simulation |
| private-source policy | 1200 | 6/6 | 1.000 | pass | simulation |

- Task-only baseline (no handoff packet): 0.000 required-context coverage; 0/3 complete resume checks.
- No external agent command was configured. Treat this as deterministic saved-context recovery, not model-based coding-agent accuracy.
- Configuring a real runner requires both --agent-command and --allow-agent-command. The command receives only JSON task/context input and inherits this process's environment for its own runtime credentials.

## Interpretation

These results establish that indexing, retrieval evaluation, and task-specific context packing run end to end on reproducible local fixtures. They are not evidence of performance on a large or representative customer repository. The Jev row is a local hybrid fallback because the external scorer is intentionally disabled. Latency is a small SQLite-fixture measurement and is not comparable to production PostgreSQL/Neo4j latency.

- Cases: 5; top-k: 5; profiles: lexical, hybrid, jev.
- Benchmark run total: 204.11 ms across all cases and profiles.
- Total estimated retrieved source tokens: 840.
