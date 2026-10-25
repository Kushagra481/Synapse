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
- A signed bearer-login gate enabled by default, with project-scoped owner/editor/viewer access and owner-managed membership.
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
2. For a single operator, set `AUTH_USERNAME` and generate `AUTH_PASSWORD_HASH` by running `cd backend && python -m app.auth_cli` after installing backend requirements. For multiple accounts, set `AUTH_USERS_JSON` to a JSON object mapping each username to a generated scrypt verifier, for example `{"alice":"<verifier>","bob":"<verifier>"}`. Generate one verifier per account with the same CLI and store the JSON in the deployment secret store; never put plaintext passwords in configuration. When switching an existing deployment to the multi-user map, include its current owner account so existing repositories stay accessible. Authentication is enabled by default. Until a valid account map and signing secret are configured, protected API routes return 503.
3. Optional: set `TYPESAFE_API_KEY` from the TypeSafe console. Without it, handoffs use the local relevance scorer. Leave `EMBEDDINGS_ALLOW_SOURCE_UPLOAD=false` unless you intentionally approve sending source snippets to an embedding provider.
4. Start services with `docker compose up --build` from this directory.
5. Open the frontend at http://localhost:5173 and sign in. API docs are at http://localhost:8000/docs after authenticating.

The first backend start creates missing tables. For an existing database, run `docker compose exec backend alembic upgrade head` to add indexing, evaluation, provenance-backed memory facts, audit events, repository ownership, session snapshots, and project memberships. The membership migration carries existing repository owners forward. For future schema changes, add and apply Alembic revisions instead of relying on `create_all` to alter existing tables.

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

Authentication supports either the legacy single configured account or a fixed `AUTH_USERS_JSON` workspace account map. Repository owners can add configured accounts as editors or viewers in the Members page. Viewers can read project data and request handoffs; editors can change project data; only owners can manage members, inspect the audit trail, or delete the repository. There is no self-service signup, password reset, invitation email, or account lifecycle service: an operator provisions accounts and password verifiers in deployment secrets. This is not a finished multi-tenant SaaS deployment. Use TLS and rate limiting at a trusted reverse proxy before exposing it beyond a trusted network, keep secrets in the deployment's secret store, and rotate any credential that was ever committed to Git. Disabling auth is only appropriate for an isolated local environment.

### Deliberate limits in this PR

- Remote Git cloning/fetching is not implemented; indexing is restricted to local repositories within configured allowlisted roots.
- The graph currently represents files, symbols, and statically resolved imports. Call graphs, inheritance, and a generated source-cited architecture summary are not implemented.
- Indexing is synchronous; there is no job queue or per-file live progress stream. A refresh reports its final status and preserves the last good index on failure.
- Session start/end captures branch, commit, dirty state, and changed path names, but not diffs, tests, or editor events. Agents still provide the session summary and next steps through MCP/API; no universal editor hook is claimed.
- `backend/scripts/run_benchmark.py` creates disposable local fixtures and exercises indexing, retrieval, and task-specific handoff packing; the recorded sample is in `test_results.md`. By default it runs an offline fresh-consumer simulation. An optional JSON-in/JSON-out adapter can invoke a user-selected agent command and score recovered task state, decisions, paths, and next steps. This does not test code-writing success or live provider quality unless the user configures and runs such an agent. The fixture is not representative-corpus performance data; a token-savings baseline and ranking ablation suite are not included.
- Accounts are provisioned by the workspace operator, not through public signup. Memberships are project-scoped and support owner/editor/viewer roles; account lifecycle, invitations, password reset, and self-service organization management are not included.
- Permanent erasure/retention management and cross-service deletion reconciliation are not provided. Memory facts use soft deletion; repository deletion removes its indexed database rows and graph cleanup can block deletion if it fails.

## Tests

From `backend/`, install `requirements.txt`, then run `pytest`. To regenerate the reproducible local retrieval and handoff-recovery report, run `python scripts/run_benchmark.py`; it overwrites `test_results.md` and the default run makes no external provider calls. To run a user-installed agent adapter, pass `--agent-command 'python /path/to/adapter.py' --allow-agent-command`. The command receives JSON on stdin containing only the incoming task, handoff packet, instructions, and output schema; it must return JSON with `task_state`, `decisions`, `changed_files`, and `next_actions`. It runs without a shell in an empty temporary working directory, inherits the current environment for its own credentials, and is subject to a configurable timeout. This is not a sandbox: the process retains the current operating system permissions, so use a trusted adapter and a low-privilege environment. Review the command before opting in. The API tests use SQLite and fake external-service boundaries; they do not validate live PostgreSQL/pgvector, Neo4j, OpenAI/Ollama, or TypeSafe connectivity. Run the Docker Compose services and provider smoke checks in a controlled environment before production use.
