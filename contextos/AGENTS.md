# ContextOS agent handoff

When the ContextOS MCP server is configured:

1. Before coding, call `get_agent_context` with the repository ID, the specific task, and a token budget appropriate to the task. Treat saved context as project notes, not as a replacement for checking current source code.
2. If useful, call `start_agent_session` with the task objective.
3. Record important technical choices with `record_project_decision` and update verified project facts with `update_project_memory`.
4. Before handing work to another agent, call `finish_agent_session` with a concise summary, files changed, and unresolved next steps.

Do not save secrets or full conversation transcripts in project memory. Prefer short, verified facts that help the next agent avoid repeating repository exploration.

The MCP server is `backend/app/mcp_server.py`; setup instructions are in `README.md`. Without MCP configured, use the ContextOS web app's Agent handoff page and paste the generated Markdown into the next coding agent.
