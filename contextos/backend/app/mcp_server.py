"""MCP stdio server exposing ContextOS to coding agents."""
from __future__ import annotations
import os
import httpx
from mcp.server.fastmcp import FastMCP

API = os.getenv("CONTEXTOS_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("CONTEXTOS_API_TOKEN", "")
mcp = FastMCP("ContextOS")


def _request(method: str, path: str, payload: dict | None = None):
    headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
    response = httpx.request(method, API + path, json=payload, headers=headers, timeout=15.0)
    response.raise_for_status()
    return response.json() if response.content else None


@mcp.tool()
def get_agent_context(repository_id: str, task: str = "", max_tokens: int = 4000) -> dict:
    """Fetch a compact, task-specific Markdown handoff packet from ContextOS."""
    return _request("POST", f"/repositories/{repository_id}/context", {"task": task, "max_tokens": max_tokens})


@mcp.tool()
def index_repository(repository_id: str, full_reindex: bool = False) -> dict:
    """Index or refresh a registered local repository inside ContextOS's allowed read-only roots."""
    return _request(
        "POST",
        f"/repositories/{repository_id}/ingest?full_reindex={str(full_reindex).lower()}",
    )


@mcp.tool()
def search_repository_code(repository_id: str, query: str, limit: int = 20, profile: str = "hybrid") -> dict:
    """Search the indexed symbols and source excerpts for a repository."""
    from urllib.parse import quote

    if profile not in {"lexical", "hybrid", "jev"}:
        raise ValueError("profile must be lexical, hybrid, or jev")
    return _request(
        "GET",
        f"/repositories/{repository_id}/code/search?q={quote(query)}&limit={limit}&profile={quote(profile)}",
    )


@mcp.tool()
def start_agent_session(repository_id: str, objective: str, provider: str = "coding-agent", model: str = "unknown", developer_name: str | None = None) -> dict:
    """Record the start of a coding-agent work session."""
    return _request("POST", f"/repositories/{repository_id}/sessions", {"llm_provider": provider, "llm_model": model, "developer_name": developer_name, "objective": objective, "status": "active"})


@mcp.tool()
def finish_agent_session(repository_id: str, session_id: str, summary: str, next_steps: list[str] | None = None, files_modified: list[str] | None = None) -> dict:
    """Save a concise handoff summary and mark an agent session complete."""
    return _request("PATCH", f"/repositories/{repository_id}/sessions/{session_id}", {"status": "completed", "summary": summary, "conversation_summary": summary, "next_steps": next_steps or [], "files_modified": files_modified or []})


@mcp.tool()
def record_project_decision(repository_id: str, title: str, decision: str, context: str = "", rationale: str = "", category: str = "other") -> dict:
    """Store a durable decision so later agents do not repeat the discussion."""
    return _request("POST", f"/repositories/{repository_id}/decisions", {"repository_id": repository_id, "title": title, "decision": decision, "context": context, "rationale": rationale, "status": "accepted", "category": category})


@mcp.tool()
def update_project_memory(repository_id: str, project_goal: str | None = None, architecture_summary: str | None = None, current_task: str | None = None, custom_notes: str | None = None) -> dict:
    """Update persistent project memory with verified facts and agent instructions."""
    payload = {key: value for key, value in {"project_goal": project_goal, "architecture_summary": architecture_summary, "current_task": current_task, "custom_notes": custom_notes}.items() if value is not None}
    return _request("PATCH", f"/repositories/{repository_id}/memory", payload)


@mcp.tool()
def record_memory_fact(
    repository_id: str,
    title: str,
    content: str,
    topic_key: str,
    fact_type: str = "project",
    source_type: str = "session",
    source_ref: str | None = None,
    source_file_path: str | None = None,
    confidence: float = 0.7,
    verified: bool = False,
    supersedes_fact_id: str | None = None,
) -> dict:
    """Save a provenance-aware fact; use the stable topic key to surface conflicts."""
    payload = {
        "title": title,
        "content": content,
        "topic_key": topic_key,
        "fact_type": fact_type,
        "source_type": source_type,
        "source_ref": source_ref,
        "confidence": confidence,
        "verified": verified,
        "supersedes_fact_id": supersedes_fact_id,
    }
    if source_file_path:
        payload["source_type"] = "repository_file"
        payload["source_file_path"] = source_file_path
    return _request("POST", f"/repositories/{repository_id}/memory/facts", payload)


@mcp.tool()
def list_memory_facts(repository_id: str, include_stale: bool = False) -> list[dict]:
    """List current project facts, optionally including stale/conflicting history."""
    from urllib.parse import quote

    return _request(
        "GET",
        f"/repositories/{repository_id}/memory/facts?include_stale={quote(str(include_stale).lower())}",
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
