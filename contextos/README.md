# ContextOS

ContextOS keeps concise, structured project memory outside any one coding agent. It records a project's goal and architecture, active work, decisions, bugs, and short session handoffs, then builds a task-specific Markdown packet that can be copied into any coding agent or requested through MCP.

## What works

- Repository, task, decision, memory, bug, session, and session-note APIs.
- A React workspace for repositories, tasks, persistent project memory, decisions, sessions, and handoff generation.
- Opt-in local repository indexing with Tree-sitter symbols for Python, JavaScript, TypeScript/TSX, Java, and C/C++; plain-text fallback chunks for supported documentation/config files.
- Incremental refresh by file content hash, deletion of stale file/symbol records, searchable code evidence with paths and line ranges, and inclusion of relevant indexed code in agent handoffs.
- A token-budgeted context endpoint: POST /repositories/{repository_id}/context accepts a task and a max_tokens budget and returns Markdown plus an estimated size.
- Optional TypeSafe Jev scoring to prioritize context items for a task. ContextOS assembles the final packet deterministically; Jev only returns structured relevance probabilities. If the key is absent or Jev is unavailable, local lexical ranking is used.
- An MCP stdio server with tools to fetch context, start/finish sessions, record decisions, and update project memory.

The saved records and generated context packet are not full chat logs. The handoff does not include Conversation.raw_content.

## Index a local repository

Indexing is read-only and only accepts Git repository roots inside `REPO_ALLOWED_ROOTS`. With Docker Compose, `REPOSITORY_ROOT` is mounted read-only at `/repos`; the example `.env` mounts the parent directory. For a repository at `../my-project`, register `/repos/my-project` in the UI, then choose **Index repository**. You can also call `POST /repositories/{repository_id}/ingest`; pass `?full_reindex=true` to force parsing unchanged files.

`GET /repositories/{repository_id}/index` reports the indexed commit, file/symbol counts, skipped files, and whether the working tree had changes. Search with `GET /repositories/{repository_id}/code/search?q=authentication`. Search results include a source path, line range, indexed commit, and a local lexical relevance explanation. Handoff generation adds matching code evidence within its token budget.

Indexing follows `.gitignore`, the configured excluded-name patterns, file-size/count limits, and a secret-content filter; it skips binary and symlink files. It does not run project code, clone remote URLs, or send indexed source to Jev or an embedding provider. Remote cloning, vector/graph retrieval, and live freshness checks are not implemented yet. Configure `REPO_ALLOWED_ROOTS` explicitly when running outside Docker; it is a comma-separated list of trusted roots.

## Run locally with Docker

1. Copy .env.example to .env and set local database passwords. Keep .env private; it is ignored by Git.
2. Optional: set TYPESAFE_API_KEY from the TypeSafe console. Without it, handoffs use the local relevance scorer.
3. Start services with docker compose up --build from this directory.
4. Open the frontend at http://localhost:5173 and the API docs at http://localhost:8000/docs.

The first backend start creates missing tables. For future schema changes, add and apply Alembic revisions instead of relying on create_all to alter existing tables.

## MCP setup

Start the backend first. Configure your coding agent's MCP server with the ContextOS backend folder as its working directory:

~~~json
{
  "mcpServers": {
    "contextos": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/contextos/backend",
      "env": { "CONTEXTOS_API_URL": "http://127.0.0.1:8000" }
    }
  }
}
~~~

The MCP tools let an agent index/search an allowed local repository, fetch a compact handoff at task start, and save a short session summary or decision before it exits. Adjust the command and path to your agent's MCP config format.

## Jev configuration

TypeSafe Jev uses POST https://api.typesafe.ai/v1/systemone with TYPESAFE_API_KEY. ContextOS sends the incoming task and up to 32 candidate memory summaries as a state, asking one Noul relevance question per candidate. Jev does not receive raw conversation transcripts. API errors and missing keys fall back to local ranking, so core context packing remains available without TypeSafe.

## API and safety notes

This is a local/internal prototype, not an internet-ready multi-user service. Do not expose the API publicly until authentication, tenant isolation, rate limits, and production secret management are added. Bind the database to trusted infrastructure and use strong, unique credentials. If credentials were ever committed to Git, rotate them; deleting a file in a new commit does not remove it from older Git history.

## Tests

From backend/, install requirements.txt, then run pytest. The API tests use SQLite and do not require PostgreSQL, Neo4j, or a TypeSafe key.
