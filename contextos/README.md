# ContextOS

ContextOS keeps concise, structured project memory outside any one coding agent. It records a project's goal and architecture, active work, decisions, bugs, and session handoffs, then builds a task-specific Markdown packet that can be copied into any coding agent or requested through MCP.

## What works

- Repository, task, decision, memory, bug, session, and session-note APIs.
- A React workspace for repositories, tasks, persistent project memory, decisions, sessions, handoffs, retrieval evaluations, and an audit trail.
- Opt-in local repository indexing with Tree-sitter symbols for Python, JavaScript, TypeScript/TSX, Java, and C/C++; plain-text fallback chunks for supported documentation/config files.
- Incremental refresh by file content hash, explicit import edges, searchable code evidence with paths and line ranges, freshness checks against the current working tree, and inclusion of relevant indexed code in agent handoffs.
- Hybrid retrieval fuses lexical and exact-symbol matches with optional pgvector embeddings and Neo4j import neighbors. A lexical-only baseline is available for comparison.
- Persistent evaluation cases and runs compare lexical, hybrid, and optional Jev retrieval using Precision@k, Recall@k, MRR, nDCG, provenance/freshness coverage, estimated tokens, and measured latency.
- Provenance-aware memory facts keep source type, confidence, verification status, indexed file/commit/hash, conflict review, supersession history, and soft deletion. Conflicting or stale facts are excluded from new handoffs.
- Minimal append-only audit metadata records repository actions and login attempts without storing request bodies, prompts, or credentials.
- A metadata-only Git snapshot at session start and handoff records branch, commit, dirty state, and changed path names without storing a diff.
- A signed bearer-login gate enabled by default, plus per-repository owner scoping for the configured workspace account.
- A token-budgeted context endpoint: POST /repositories/{repository_id}/context accepts a task and a max_tokens budget and returns Markdown plus an estimated size.
- Optional TypeSafe Jev scoring to prioritize context items for a task or rerank repository-search candidates. ContextOS assembles the final packet deterministically; Jev only returns structured relevance probabilities. Local ranking remains available when the key is absent or the service is unavailable.
- An MCP stdio server with tools to fetch context, start/finish sessions, record decisions, search code, and create/list provenance-aware memory facts.

The saved records and generated context packet are not full chat logs. The handoff does not include Conversation.raw_content.

## Index a local repository

Indexing is read-only and only accepts Git repository roots inside `REPO_ALLOWED_ROOTS`. With Docker Compose, `REPOSITORY_ROOT` is mounted read-only at `/repos`; the example `.env` mounts the parent directory. For a repository at `../my-project`, register `/repos/my-project` in the UI, then choose **Index repository**. You can also call `POST /repositories/{repository_id}/ingest`; pass `?full_reindex=true` to force parsing unchanged files.

`GET /repositories/{repository_id}/index` reports the indexed commit, file/symbol/import counts, embedding and graph sync status, skipped files, and whether the working tree had changes. Search with `GET /repositories/{repository_id}/code/search?q=authentication&profile=hybrid`; choose `profile=lexical` for the baseline. Search results include a source path, line range, indexed/current commit information, freshness, and ranking signals. Handoff generation adds matching code evidence within its token budget.

Indexing follows `.gitignore`, the configured excluded-name patterns, file-size/count limits, and a secret-content filter; it skips binary and symlink files. It does not run project code or clone remote URLs. Code remains local by default. Embeddings are disabled unless `EMBEDDINGS_ALLOW_SOURCE_UPLOAD=true`; enabling this permits the configured OpenAI or Ollama embedding endpoint to receive bounded source snippets. The optional Jev search profile has a separate `JEV_ALLOW_SOURCE_UPLOAD=true` gate and sends only bounded snippets for the top 32 candidates to TypeSafe; its UI control is unchecked by default. Leave both flags false to keep source local. Graph projection stores symbol metadata/signatures and import relationships in Neo4j. Configure `REPO_ALLOWED_ROOTS` explicitly when running outside Docker; it is a comma-separated list of trusted roots.

## Run locally with Docker

1. Copy `.env.example` to `.env` and set unique database passwords and a random `SECRET_KEY` of at least 32 characters. Keep `.env` private; it is ignored by Git.
2. Set `AUTH_USERNAME`. Generate an `AUTH_PASSWORD_HASH` by running `cd backend && python -m app.auth_cli` after installing backend requirements; store the resulting verifier in the environment, not in chat. Authentication is enabled by default. Until all three auth settings are valid, protected API routes return 503.
3. Optional: set `TYPESAFE_API_KEY` from the TypeSafe console. Without it, handoffs use the local relevance scorer. Leave `EMBEDDINGS_ALLOW_SOURCE_UPLOAD=false` unless you intentionally approve sending source snippets to an embedding provider.
4. Start services with `docker compose up --build` from this directory.
5. Open the frontend at http://localhost:5173 and sign in. API docs are at http://localhost:8000/docs after authenticating.

The first backend start creates missing tables. For an existing database, run `docker compose exec backend alembic upgrade head` to add indexing, evaluation, provenance-backed memory facts, audit events, repository-owner, and session snapshot schema. For future schema changes, add and apply Alembic revisions instead of relying on `create_all` to alter existing tables.

## MCP setup

Start the backend first. Configure your coding agent's MCP server with the ContextOS backend folder as its working directory:

~~~json
{
  "mcpServers": {
    "contextos": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/contextos/backend",
      "env": {
        "CONTEXTOS_API_URL": "http://127.0.0.1:8000",
        "CONTEXTOS_API_TOKEN": "<short-lived bearer token from /auth/login>"
      }
    }
  }
}
~~~

The MCP tools let an agent index/search an allowed local repository, fetch a compact handoff at task start, and save a short session summary, decision, or provenance-aware fact before it exits. `record_memory_fact` uses a stable topic key so the API can flag collisions; pass `supersedes_fact_id` only when intentionally replacing prior state. Adjust the command and path to your agent's MCP config format.

## Jev configuration

TypeSafe Jev uses POST https://api.typesafe.ai/v1/systemone with `TYPESAFE_API_KEY`. ContextOS sends the incoming task and up to 32 candidate memory summaries as a state, asking one Noul relevance question per candidate. For repository code search, Jev receives candidate snippets only when `JEV_ALLOW_SOURCE_UPLOAD=true`; that setting is separate from embeddings and off by default. Repository-file-backed facts are excluded from memory-summary scoring. Jev does not receive raw conversation transcripts. API errors and missing keys fall back to local ranking, so core context packing remains available without TypeSafe.

## API and safety notes

Authentication is a single configured workspace account with repository-owner scoping; there is no account signup, invitation flow, or role-based sharing yet. This is not a finished multi-tenant SaaS deployment. Use TLS and rate limiting at a trusted reverse proxy before exposing it beyond a trusted network, keep secrets in the deployment's secret store, and rotate any credential that was ever committed to Git. Disabling auth is only appropriate for an isolated local environment.

### Deliberate limits in this PR

- Remote Git cloning/fetching is not implemented; indexing is restricted to local repositories within configured allowlisted roots.
- The graph currently represents files, symbols, and statically resolved imports. Call graphs, inheritance, and a generated source-cited architecture summary are not implemented.
- Indexing is synchronous; there is no job queue or per-file live progress stream. A refresh reports its final status and preserves the last good index on failure.
- Session start/end captures branch, commit, dirty state, and changed path names, but not diffs, tests, or editor events. Agents still provide the session summary and next steps through MCP/API; no universal editor hook is claimed.
- `backend/scripts/run_benchmark.py` creates disposable local fixtures and exercises indexing, retrieval, and task-specific handoff packing; the recorded sample is in `test_results.md`. Its offline fresh-consumer simulation checks whether a new agent could recover required context, but does not invoke an LLM or claim code-completion success. This is not representative-corpus performance data. A model-backed resume-success benchmark, token-savings baseline, and ranking ablation suite are not included.
- The account model is one configured workspace login, not user memberships/roles. Code below enforces this configured owner boundary; multi-user collaboration still needs a membership model.
- Permanent erasure/retention management and cross-service deletion reconciliation are not provided. Memory facts use soft deletion; repository deletion removes its indexed database rows and graph cleanup can block deletion if it fails.

## Tests

From `backend/`, install `requirements.txt`, then run `pytest`. To regenerate the reproducible local retrieval and handoff-recovery report, run `python scripts/run_benchmark.py`; it overwrites `test_results.md` and does not call external providers. The API tests use SQLite and fake external-service boundaries; they do not validate live PostgreSQL/pgvector, Neo4j, OpenAI/Ollama, or TypeSafe connectivity. Run the Docker Compose services and provider smoke checks in a controlled environment before production use.
