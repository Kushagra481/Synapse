"""Neo4j projection of code index metadata and explicitly resolved imports."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.graph import GraphSession
from app.models.code_index import CodeImport, CodeSymbol, IndexedFile


def _graph_id(kind: str, repository_id: str, path: str, name: str = "") -> str:
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"contextos:{kind}:{repository_id}:{path}:{name}"))


async def sync_repository_graph(
    db: AsyncSession, repository_id: str, repository_name: str, commit_sha: str | None
) -> str:
    """Rebuild the repository's graph projection from committed SQL index data."""
    if not settings.GRAPH_SYNC_ENABLED or settings.APP_ENV == "test":
        return "disabled"
    try:
        graph = GraphSession()
    except RuntimeError:
        return "unavailable"

    files = (
        await db.scalars(select(IndexedFile).where(IndexedFile.repository_id == repository_id))
    ).all()
    file_ids = [file.id for file in files]
    symbols = (
        await db.scalars(select(CodeSymbol).where(CodeSymbol.repository_id == repository_id))
    ).all()
    imports = (
        await db.scalars(select(CodeImport).where(CodeImport.repository_id == repository_id))
    ).all()
    files_by_id = {file.id: file for file in files}

    file_rows = [
        {
            "id": file.id,
            "repository_id": repository_id,
            "path": file.relative_path,
            "language": file.language,
            "hash": file.content_sha256,
            "commit_sha": file.indexed_commit_sha,
        }
        for file in files
    ]
    symbol_rows = [
        {
            "id": symbol.id,
            "file_id": symbol.file_id,
            "name": symbol.name,
            "qualified_name": symbol.qualified_name,
            "kind": symbol.kind,
            "start_line": symbol.start_line,
            "end_line": symbol.end_line,
            "signature": symbol.signature,
        }
        for symbol in symbols
        if symbol.file_id in files_by_id
    ]
    import_rows = [
        {
            "id": _graph_id(
                "module", repository_id, row.target_module, row.target_file_path or ""
            ),
            "file_id": row.file_id,
            "target_module": row.target_module,
            "target_file_path": row.target_file_path,
            "repository_id": repository_id,
        }
        for row in imports
        if row.file_id in files_by_id
    ]

    statements: list[tuple[str, dict]] = [
        (
            "MATCH (n) WHERE n.repository_id = $repository_id "
            "AND (n:File OR n:Symbol OR n:Module) DETACH DELETE n",
            {"repository_id": repository_id},
        ),
        (
            "MERGE (r:Repository {id: $repository_id}) "
            "SET r.name = $name, r.indexed_commit_sha = $commit_sha",
            {"repository_id": repository_id, "name": repository_name, "commit_sha": commit_sha},
        ),
    ]
    for start in range(0, len(file_rows), 500):
        statements.append(
            (
                "UNWIND $rows AS row "
                "MATCH (r:Repository {id: row.repository_id}) "
                "MERGE (f:File {id: row.id}) "
                "SET f.repository_id = row.repository_id, f.path = row.path, "
                "f.language = row.language, f.content_sha256 = row.hash, "
                "f.indexed_commit_sha = row.commit_sha "
                "MERGE (r)-[:CONTAINS]->(f)",
                {"rows": file_rows[start : start + 500]},
            )
        )
    for start in range(0, len(symbol_rows), 500):
        statements.append(
            (
                "UNWIND $rows AS row MATCH (f:File {id: row.file_id}) "
                "MERGE (s:Symbol {id: row.id}) "
                "SET s.repository_id = $repository_id, s.name = row.name, "
                "s.qualified_name = row.qualified_name, s.kind = row.kind, "
                "s.start_line = row.start_line, s.end_line = row.end_line, "
                "s.signature = row.signature "
                "MERGE (f)-[:DEFINES]->(s)",
                {"rows": symbol_rows[start : start + 500], "repository_id": repository_id},
            )
        )
    resolved_imports = [row for row in import_rows if row["target_file_path"]]
    for start in range(0, len(resolved_imports), 500):
        statements.append(
            (
                "UNWIND $rows AS row "
                "MATCH (f:File {id: row.file_id}) "
                "MATCH (target:File {repository_id: row.repository_id, path: row.target_file_path}) "
                "MERGE (f)-[:IMPORTS]->(target)",
                {"rows": resolved_imports[start : start + 500]},
            )
        )
    unresolved_imports = [row for row in import_rows if not row["target_file_path"]]
    for start in range(0, len(unresolved_imports), 500):
        statements.append(
            (
                "UNWIND $rows AS row MATCH (f:File {id: row.file_id}) "
                "MERGE (m:Module {id: row.id}) "
                "SET m.repository_id = row.repository_id, m.name = row.target_module "
                "MERGE (f)-[:IMPORTS]->(m)",
                {"rows": unresolved_imports[start : start + 500]},
            )
        )
    try:
        await graph.run_transaction(statements)
        return "synced"
    except Exception:
        # Do not return graph errors or source-derived Cypher parameters to callers.
        return "failed"


async def delete_repository_graph(repository_id: str) -> str:
    if not settings.GRAPH_SYNC_ENABLED or settings.APP_ENV == "test":
        return "disabled"
    try:
        graph = GraphSession()
        await graph.run_transaction(
            [
                (
                    "MATCH (n) WHERE n.repository_id = $repository_id "
                    "AND (n:File OR n:Symbol OR n:Module) DETACH DELETE n",
                    {"repository_id": repository_id},
                ),
                (
                    "MATCH (r:Repository {id: $repository_id}) DETACH DELETE r",
                    {"repository_id": repository_id},
                ),
            ]
        )
        return "deleted"
    except RuntimeError:
        return "unavailable"
    except Exception:
        return "failed"


async def related_file_ids(repository_id: str, file_ids: list[str]) -> list[str]:
    """Return one-hop resolved import neighbors for lexical candidates."""
    if not settings.GRAPH_SYNC_ENABLED or settings.APP_ENV == "test" or not file_ids:
        return []
    try:
        graph = GraphSession()
        rows = await graph.run(
            "MATCH (source:File {repository_id: $repository_id})-[:IMPORTS]->(target:File) "
            "WHERE source.id IN $file_ids RETURN DISTINCT target.id AS id",
            repository_id=repository_id,
            file_ids=file_ids,
        )
        return [str(row["id"]) for row in rows if row.get("id")]
    except Exception:
        return []
