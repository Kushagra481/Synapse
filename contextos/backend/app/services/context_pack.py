"""Build small, portable handoff packets for coding agents."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from app.services.jev import score_relevance


def estimate_tokens(text: str) -> int:
    """Conservative, dependency-free estimate; actual tokenizer counts vary by model."""
    return max(1, (len(text) + 3) // 4)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(_text(part) for part in value if part is not None)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_text(part)}" for key, part in value.items() if part is not None)
    return str(value).strip()


def _candidate(kind: str, title: str, content: Any, updated_at: Any = None, base: float = 0.0) -> dict[str, Any] | None:
    value = _text(content)
    if not value:
        return None
    return {"kind": kind, "title": title, "content": value[:2800], "updated_at": updated_at, "base": base}


def _lexical_score(item: dict[str, Any], task: str) -> float:
    words = {w.lower() for w in task.split() if len(w) > 2}
    text = (item["title"] + " " + item["content"]).lower()
    hits = sum(1 for word in words if word in text)
    age_bonus = 0.0
    stamp = item.get("updated_at")
    if stamp:
        try:
            age = (datetime.now(timezone.utc) - stamp.replace(tzinfo=timezone.utc)).days
            age_bonus = max(0.0, 0.15 - min(age, 30) / 200)
        except (TypeError, AttributeError):
            pass
    return item["base"] + min(hits / max(len(words), 1), 1.0) * 0.6 + age_bonus


async def build_context_pack(
    repo,
    memory,
    tasks,
    decisions,
    sessions,
    task: str = "",
    max_tokens: int = 4000,
    code_results: list[dict[str, Any]] | None = None,
    retrieval_metadata: dict[str, Any] | None = None,
    memory_facts: list[Any] | None = None,
) -> dict[str, Any]:
    budget = min(max(int(max_tokens), 128), 32000)
    items: list[dict[str, Any]] = []
    if repo:
        item = _candidate("project", repo.name, {"description": repo.description, "path": repo.local_path, "branch": repo.default_branch, "language": repo.language}, repo.updated_at, 0.4)
        if item: items.append(item)
    if memory:
        fields = ["project_goal", "architecture_summary", "tech_stack", "current_task", "active_tasks", "blocked_tasks", "next_steps", "known_bugs", "open_questions", "recent_changes", "recently_modified_files", "recent_commits", "custom_notes"]
        payload = {field: getattr(memory, field) for field in fields if getattr(memory, field, None)}
        item = _candidate("project memory", "Persistent project memory", payload, memory.updated_at, 1.0)
        if item: items.append(item)
    for fact in memory_facts or []:
        payload = {
            "fact": fact.content,
            "type": fact.fact_type,
            "confidence": round(float(fact.confidence), 2),
            "verified": fact.verified,
            "source_type": fact.source_type,
            "source_ref": fact.source_ref,
            "source_file": fact.source_file_path,
            "source_commit": fact.source_commit_sha,
            "evidence": fact.evidence_quote,
        }
        item = _candidate("memory fact", fact.title, payload, fact.updated_at, 0.65 if fact.verified else 0.35)
        if item:
            item["source"] = {
                "fact_id": fact.id,
                "type": fact.source_type,
                "reference": fact.source_ref,
                "file_path": fact.source_file_path,
                "commit_sha": fact.source_commit_sha,
                "confidence": fact.confidence,
                "verified": fact.verified,
            }
            items.append(item)
    for row in tasks:
        item = _candidate("task", row.title, {"status": row.status.value, "priority": row.priority.value, "description": row.description, "blocked_reason": row.blocked_reason, "completion_notes": row.completion_notes}, row.updated_at, 0.45 if row.status.value in ("active", "blocked") else 0.2)
        if item: items.append(item)
    for row in decisions:
        item = _candidate("decision", row.title, {"status": row.status.value, "category": row.category.value, "context": row.context, "decision": row.decision, "rationale": row.rationale, "consequences": row.consequences}, row.updated_at, 0.5 if row.status.value == "accepted" else 0.1)
        if item: items.append(item)
    for row in sessions:
        item = _candidate("session", f"{row.llm_provider}/{row.llm_model}: {row.objective or 'coding handoff'}", {"summary": row.summary, "conversation_summary": row.conversation_summary, "files_modified": row.files_modified, "decisions_made": row.decisions_made, "tasks_completed": row.tasks_completed, "open_questions": row.open_questions, "next_steps": row.next_steps, "starting_branch": getattr(row, "starting_branch", None), "starting_commit_sha": getattr(row, "starting_commit_sha", None), "handoff_branch": getattr(row, "handoff_branch", None), "handoff_commit_sha": getattr(row, "handoff_commit_sha", None), "handoff_changed_files": getattr(row, "handoff_changed_files", None), "handoff_working_tree_dirty": getattr(row, "handoff_working_tree_dirty", None)}, row.updated_at, 0.25)
        if item: items.append(item)

    lexical = [_lexical_score(item, task) for item in items]
    # Jev sees saved context summaries only. Repository source is never sent to
    # an external scorer; code evidence is ranked locally by the search service.
    jev_indices = [
        index
        for index, item in enumerate(items)
        if item.get("source", {}).get("type") != "repository_file"
    ]
    jev_candidates = [items[index] for index in jev_indices]
    jev_scores = await score_relevance(task, jev_candidates) if task.strip() else None
    jev_by_index = (
        {index: jev_scores[position] for position, index in enumerate(jev_indices) if position < len(jev_scores)}
        if jev_scores
        else {}
    )
    for index, item in enumerate(items):
        item["score"] = jev_by_index.get(index, lexical[index])
    for code_rank, result in enumerate(code_results or [], start=1):
        path = result.get("file_path", "")
        start_line = result.get("start_line", 0)
        end_line = result.get("end_line", 0)
        title = f"{result.get('qualified_name') or result.get('symbol') or path} ({path}:{start_line}-{end_line})"
        content = (
            f"Source: {path}:{start_line}-{end_line}\n"
            f"Commit: {result.get('indexed_commit_sha') or 'uncommitted snapshot'}\n"
            f"Freshness: {result.get('freshness', 'indexed_snapshot')}\n"
            f"Current commit: {result.get('current_commit_sha') or 'unknown'}\n"
            f"Relevance: {result.get('relevance_reason', 'Local lexical search')}\n\n"
            f"{result.get('source_text', '')}"
        )
        code_score = 0.45 + (0.9 / max(int(result.get("retrieval_rank", code_rank)), 1))
        item = _candidate("code evidence", title, content, base=code_score)
        if item:
            item["score"] = code_score
            item["source"] = {
                "file_path": path,
                "start_line": start_line,
                "end_line": end_line,
                "indexed_commit_sha": result.get("indexed_commit_sha"),
                "current_commit_sha": result.get("current_commit_sha"),
                "freshness": result.get("freshness", "indexed_snapshot"),
                "ranking_signals": result.get("ranking_signals", {}),
            }
            items.append(item)
    items.sort(key=lambda item: item["score"], reverse=True)

    lines = [f"# ContextOS handoff: {repo.name if repo else 'Project'}", "", "Use this as saved project context. Keep working state updated before ending your session."]
    token_limit_chars = budget * 4
    if task.strip():
        task_budget = max(0, token_limit_chars - len("\n".join(lines)) - 100)
        lines += ["", "## Incoming task", task.strip()[:task_budget]]
    included = []
    for item in items:
        section = f"\n## {item['kind']}: {item['title']}\n{item['content']}"
        current = "\n".join(lines)
        if len(current) + len(section) + 1 > token_limit_chars:
            continue
        lines.append(section)
        included.append(item)
    text = "\n".join(lines)
    return {
        "text": text,
        "estimated_tokens": estimate_tokens(text),
        "budget_tokens": budget,
        "included_items": len(included),
        "available_items": len(items),
        "omitted_items": len(items) - len(included),
        "jev_used": bool(jev_scores),
        "retrieval": retrieval_metadata or {},
        "items": [
            {
                "kind": item["kind"],
                "title": item["title"],
                "relevance": round(float(item["score"]), 3),
                **({"source": item["source"]} if item.get("source") else {}),
            }
            for item in included
        ],
    }
