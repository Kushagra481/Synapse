# ContextOS agent handoff

When the ContextOS MCP server is configured:

1. If the repository has not been indexed yet, or its code has changed substantially, call `index_repository`. Indexing is local, read-only, and limited to configured roots.
2. Before coding, call `get_agent_context` with the repository ID, the specific task, and an appropriate token budget. When you need deeper evidence, call `search_repository_code`. Treat saved context and indexed source as snapshots; verify important facts against the live working tree.
3. If useful, call `start_agent_session` with the task objective.
4. Record important technical choices with `record_project_decision`, update verified project summaries with `update_project_memory`, and store durable evidence-backed claims with `record_memory_fact`.
5. Before handing work to another agent, call `finish_agent_session` with a concise summary, files changed, and unresolved next steps.

Do not save secrets or full conversation transcripts in project memory. Prefer short, verified facts that help the next agent avoid repeating repository exploration.

The MCP server is `backend/app/mcp_server.py`; setup instructions are in `README.md`. Without MCP configured, use the ContextOS web app's Agent handoff page and paste the generated Markdown into the next coding agent.
