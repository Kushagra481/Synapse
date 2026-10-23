"""Read-only, incremental repository indexing and lexical code retrieval."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from tree_sitter import Language, Parser

from app.core.config import settings
from app.models.code_index import CodeSymbol, IndexedFile, RepositoryIndexState
from app.models.repository import IngestionStatus, Repository


EXCLUDED_PATTERNS = (
    ".git", ".env", ".env.*", "*.pem", "*.key", "*.cert", "*.p12", "*.pfx",
    "*credentials*", "*secret*", "*password*", "*token*", "node_modules",
    "bower_components", "Pods", "vendor", "__pycache__", "venv", ".venv",
    ".tox", ".mypy_cache", ".ruff_cache", ".next", ".nuxt", ".idea",
    "coverage", "dist", "build", "target", ".repo_cache",
)
SECRET_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~-]{24,}"),
    re.compile(r"\bsk-(?:live|prod)-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token)"
        r"\s*[:=]\s*['\"][^'\"]{20,}['\"]"
    ),
)
LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".c": "cpp",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "cpp",
    ".hpp": "cpp",
}
SUPPORTED_TEXT_SUFFIXES = {
    *LANGUAGE_BY_SUFFIX,
    ".md", ".mdx", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".sql", ".sh", ".bash", ".html", ".css", ".scss",
    ".xml", ".graphql", ".proto", ".dockerfile",
}
SUPPORTED_TEXT_BASENAMES = {
    "dockerfile", "makefile", "justfile", "license", "readme",
    "gemfile", "rakefile", "procfile",
}
LANGUAGE_PARSERS = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "java": ("tree_sitter_java", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
}
SYMBOL_KINDS = {
    "function_definition": "function",
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "class_definition": "class",
    "class_declaration": "class",
    "class_specifier": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "enum_specifier": "enum",
    "struct_specifier": "struct",
    "record_declaration": "class",
}
MAX_SYMBOL_SOURCE_CHARS = 24000
FALLBACK_CHUNK_CHARS = 6000


class RepositoryIndexError(ValueError):
    """A repository cannot be safely indexed."""


@dataclass
class FileSnapshot:
    relative_path: str
    content: str
    content_sha256: str
    byte_size: int
    language: str | None
    parser: str
    symbols: list[dict[str, Any]]


def _stable_id(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "contextos:" + value))


def _allowed_roots() -> list[Path]:
    raw_roots = [part.strip() for part in settings.REPO_ALLOWED_ROOTS.split(",") if part.strip()]
    if not raw_roots:
        raw_roots = [settings.REPO_CACHE_DIR]
    roots = []
    for value in raw_roots:
        path = Path(value).expanduser()
        roots.append(path.resolve())
    return roots


def validate_repository_path(local_path: str) -> tuple[Path, Repo]:
    """Require a real Git worktree whose resolved root is inside an allowlisted mount."""
    candidate = Path(local_path).expanduser()
    if not candidate.is_absolute():
        raise RepositoryIndexError("Use an absolute path inside a configured repository root.")
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RepositoryIndexError("Repository path does not exist or cannot be resolved.") from None
    if not root.is_dir():
        raise RepositoryIndexError("Repository path must be a directory.")
    if not any(root == allowed or allowed in root.parents for allowed in _allowed_roots()):
        raise RepositoryIndexError("Repository path is outside the configured read-only roots.")
    try:
        git_repo = Repo(str(root), search_parent_directories=False)
        worktree = Path(git_repo.working_tree_dir or "").resolve(strict=True)
    except (InvalidGitRepositoryError, NoSuchPathError, OSError, RuntimeError):
        raise RepositoryIndexError("Path is not the root of a valid Git working tree.") from None
    if worktree != root:
        raise RepositoryIndexError("Register the Git repository root, not a subdirectory.")
    return root, git_repo


def _is_excluded(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    patterns = tuple(settings.EXCLUDED_PATTERNS or []) + EXCLUDED_PATTERNS
    return any(
        fnmatch.fnmatchcase(relative_path, pattern)
        or any(fnmatch.fnmatchcase(part, pattern) for part in parts)
        for pattern in patterns
    )


def _is_supported_text_file(path: Path) -> bool:
    return (
        path.suffix.lower() in SUPPORTED_TEXT_SUFFIXES
        or path.name.lower() in SUPPORTED_TEXT_BASENAMES
    )


def _is_secret_content(content: str) -> bool:
    return any(pattern.search(content) for pattern in SECRET_CONTENT_PATTERNS)


def _tree_sitter_symbols(content: str, language_name: str) -> tuple[list[dict[str, Any]], bool]:
    module_name, factory_name = LANGUAGE_PARSERS[language_name]
    module = __import__(module_name, fromlist=[factory_name])
    parser = Parser(Language(getattr(module, factory_name)()))
    source = content.encode("utf-8")
    tree = parser.parse(source)
    symbols: list[dict[str, Any]] = []

    def symbol_name(node) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return name_node.text.decode("utf-8", errors="replace")
        if language_name == "cpp":
            declarator = node.child_by_field_name("declarator")
            while declarator is not None:
                if declarator.type in {"identifier", "field_identifier", "type_identifier"}:
                    return declarator.text.decode("utf-8", errors="replace")
                nested = declarator.child_by_field_name("declarator")
                if nested is None:
                    identifier = next(
                        (
                            child
                            for child in declarator.named_children
                            if child.type in {"identifier", "field_identifier", "type_identifier"}
                        ),
                        None,
                    )
                    if identifier is not None:
                        return identifier.text.decode("utf-8", errors="replace")
                    return ""
                declarator = nested
            if node.type in {"class_specifier", "struct_specifier"}:
                identifier = next(
                    (
                        child
                        for child in node.named_children
                        if child.type in {"type_identifier", "identifier"}
                    ),
                    None,
                )
                if identifier is not None:
                    return identifier.text.decode("utf-8", errors="replace")
        return ""

    def walk(node, scopes: list[str]) -> None:
        kind = SYMBOL_KINDS.get(node.type)
        next_scopes = scopes
        if kind:
            name = symbol_name(node)
            if language_name == "cpp" and kind == "function" and scopes:
                kind = "method"
            if name:
                qualified = ".".join([*scopes, name])
                node_source = node.text.decode("utf-8", errors="replace")
                lines = node_source.splitlines() or [node_source]
                symbols.append(
                    {
                        "name": name[:512],
                        "qualified_name": qualified[:1024],
                        "kind": kind,
                        "start_line": node.start_point.row + 1,
                        "end_line": node.end_point.row + 1,
                        "signature": lines[0][:500],
                        "source_text": node_source[:MAX_SYMBOL_SOURCE_CHARS],
                    }
                )
                if kind in {"class", "interface", "struct", "enum"}:
                    next_scopes = [*scopes, name]
        for child in node.named_children:
            walk(child, next_scopes)

    walk(tree.root_node, [])
    return symbols, tree.root_node.has_error


def _fallback_chunks(content: str) -> list[dict[str, Any]]:
    lines = content.splitlines()
    chunks: list[dict[str, Any]] = []
    start = 0
    current: list[str] = []
    current_size = 0
    chunk_number = 1
    for line_number, line in enumerate(lines, start=1):
        line_size = len(line) + 1
        if current and (current_size + line_size > FALLBACK_CHUNK_CHARS or len(current) >= 200):
            text = "\n".join(current)
            chunks.append(
                {
                    "name": f"chunk-{chunk_number}",
                    "qualified_name": f"chunk-{chunk_number}",
                    "kind": "chunk",
                    "start_line": start,
                    "end_line": line_number - 1,
                    "signature": current[0][:500],
                    "source_text": text,
                }
            )
            chunk_number += 1
            current = []
            current_size = 0
        if not current:
            start = line_number
        current.append(line)
        current_size += line_size
    if current:
        text = "\n".join(current)
        chunks.append(
            {
                "name": f"chunk-{chunk_number}",
                "qualified_name": f"chunk-{chunk_number}",
                "kind": "chunk",
                "start_line": start,
                "end_line": len(lines),
                "signature": current[0][:500],
                "source_text": text,
            }
        )
    return chunks


def _parse_file(relative_path: str, raw: bytes, commit_sha: str | None) -> FileSnapshot:
    text = raw.decode("utf-8")
    language = LANGUAGE_BY_SUFFIX.get(Path(relative_path).suffix.lower())
    parser_name = "tree_sitter" if language else "fallback"
    symbols: list[dict[str, Any]] = []
    if language:
        symbols, has_error = _tree_sitter_symbols(text, language)
        if has_error:
            parser_name = "tree_sitter_partial"
    if not symbols:
        symbols = _fallback_chunks(text)
        if not language:
            parser_name = "fallback"
    return FileSnapshot(
        relative_path=relative_path,
        content=text,
        content_sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        language=language,
        parser=parser_name,
        symbols=symbols,
    )


def _working_tree_files(root: Path, git_repo: Repo) -> tuple[list[Path], int]:
    files: list[Path] = []
    skipped = 0
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        kept_dirs = []
        for dirname in dirnames:
            full = current / dirname
            relative = full.relative_to(root).as_posix()
            if full.is_symlink() or _is_excluded(relative):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs
        for filename in filenames:
            full = current / filename
            relative = full.relative_to(root).as_posix()
            if full.is_symlink() or _is_excluded(relative):
                skipped += 1
                continue
            if not _is_supported_text_file(Path(filename)):
                skipped += 1
                continue
            files.append(full)
    ignored: set[str] = set()
    relative_paths = [path.relative_to(root).as_posix() for path in files]
    for start in range(0, len(relative_paths), 200):
        batch = relative_paths[start : start + 200]
        try:
            ignored.update(path.replace("\\", "/") for path in git_repo.ignored(*batch))
        except GitCommandError:
            # A malformed ignore rule must not broaden indexing; continue with safe defaults.
            continue
    kept = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative in ignored:
            skipped += 1
        else:
            kept.append(path)
    if len(kept) > settings.MAX_INDEXED_FILES:
        raise RepositoryIndexError(
            f"Repository contains more indexable files than the configured limit ({settings.MAX_INDEXED_FILES})."
        )
    return kept, skipped


async def index_repository(
    db: AsyncSession, repository: Repository, force: bool = False
) -> dict[str, Any]:
    """Index a safe snapshot of a local Git working tree without modifying it."""
    repository_id = repository.id
    root, git_repo = validate_repository_path(repository.local_path)
    commit_sha = git_repo.head.commit.hexsha if git_repo.head.is_valid() else None
    repository.ingestion_status = IngestionStatus.RUNNING
    repository.ingestion_error = None
    await db.commit()
    try:
        paths, skipped_count = _working_tree_files(root, git_repo)
        snapshots: list[FileSnapshot] = []
        total_bytes = 0
        for path in paths:
            try:
                size = path.stat().st_size
                if size > settings.MAX_FILE_SIZE_BYTES:
                    skipped_count += 1
                    continue
                total_bytes += size
                if total_bytes > settings.MAX_INDEXED_TOTAL_BYTES:
                    raise RepositoryIndexError(
                        "Repository exceeds the configured total byte limit for one indexing run."
                    )
                raw = path.read_bytes()
                if b"\x00" in raw:
                    skipped_count += 1
                    continue
                snapshot = _parse_file(path.relative_to(root).as_posix(), raw, commit_sha)
                if _is_secret_content(snapshot.content):
                    skipped_count += 1
                    continue
                snapshots.append(snapshot)
            except RepositoryIndexError:
                raise
            except OSError as exc:
                raise RepositoryIndexError(
                    "Could not read a candidate file; the refresh was cancelled to preserve the existing index."
                ) from exc
            except (UnicodeDecodeError, ValueError):
                skipped_count += 1

        existing_rows = (
            await db.scalars(select(IndexedFile).where(IndexedFile.repository_id == repository_id))
        ).all()
        existing = {row.relative_path: row for row in existing_rows}
        current_paths = {snapshot.relative_path for snapshot in snapshots}
        removed_paths = set(existing) - current_paths
        added_count = changed_count = unchanged_count = symbol_count = 0

        for relative_path in removed_paths:
            row = existing[relative_path]
            await db.execute(delete(CodeSymbol).where(CodeSymbol.file_id == row.id))
            await db.delete(row)

        for snapshot in snapshots:
            prior = existing.get(snapshot.relative_path)
            if prior and prior.content_sha256 == snapshot.content_sha256 and not force:
                prior.indexed_commit_sha = commit_sha
                unchanged_count += 1
                symbol_count += (await db.scalar(
                    select(func.count())
                    .select_from(CodeSymbol)
                    .where(CodeSymbol.file_id == prior.id)
                )) or 0
                continue

            if prior:
                await db.execute(delete(CodeSymbol).where(CodeSymbol.file_id == prior.id))
                await db.delete(prior)
                changed_count += 1
            else:
                added_count += 1

            file_row = IndexedFile(
                id=_stable_id(f"file:{repository_id}:{snapshot.relative_path}"),
                repository_id=repository_id,
                relative_path=snapshot.relative_path,
                content_sha256=snapshot.content_sha256,
                byte_size=snapshot.byte_size,
                language=snapshot.language,
                parser=snapshot.parser,
                indexed_commit_sha=commit_sha,
            )
            db.add(file_row)
            await db.flush()
            for symbol in snapshot.symbols:
                db.add(
                    CodeSymbol(
                        id=_stable_id(
                            f"symbol:{repository_id}:{snapshot.relative_path}:"
                            f"{symbol['qualified_name']}:{symbol['start_line']}:{symbol['kind']}"
                        ),
                        repository_id=repository_id,
                        file_id=file_row.id,
                        **symbol,
                    )
                )
                symbol_count += 1

        state = await db.get(RepositoryIndexState, repository_id)
        now = datetime.now(timezone.utc)
        values = {
            "indexed_commit_sha": commit_sha,
            "indexed_at": now,
            "file_count": len(snapshots),
            "symbol_count": symbol_count,
            "skipped_count": skipped_count,
            "working_tree_dirty": git_repo.is_dirty(untracked_files=True),
        }
        if state is None:
            state = RepositoryIndexState(repository_id=repository_id, **values)
            db.add(state)
        else:
            for key, value in values.items():
                setattr(state, key, value)
        repository.ingestion_status = IngestionStatus.COMPLETED
        repository.last_ingested_at = now.isoformat()
        repository.ingestion_error = None
        await db.commit()
        return {
            "repository_id": repository_id,
            "indexed_commit_sha": commit_sha,
            "file_count": len(snapshots),
            "symbol_count": symbol_count,
            "skipped_count": skipped_count,
            "added_count": added_count,
            "changed_count": changed_count,
            "removed_count": len(removed_paths),
            "unchanged_count": unchanged_count,
            "working_tree_dirty": values["working_tree_dirty"],
            "indexed_at": now.isoformat(),
        }
    except Exception as exc:
        await db.rollback()
        failed_repository = await db.get(Repository, repository_id)
        if failed_repository:
            failed_repository.ingestion_status = IngestionStatus.FAILED
            failed_repository.ingestion_error = f"Index failed ({type(exc).__name__})."
            await db.commit()
        if isinstance(exc, RepositoryIndexError):
            raise
        raise RepositoryIndexError("Repository indexing failed; the existing index was left unchanged.") from exc


async def get_index_status(db: AsyncSession, repository_id: str) -> dict[str, Any] | None:
    repository = await db.get(Repository, repository_id)
    if not repository:
        return None
    state = await db.get(RepositoryIndexState, repository_id)
    if not state:
        return {
            "repository_id": repository_id,
            "ingestion_status": repository.ingestion_status.value,
            "ingestion_error": repository.ingestion_error,
            "indexed_commit_sha": None,
            "indexed_at": None,
            "file_count": 0,
            "symbol_count": 0,
            "skipped_count": 0,
            "working_tree_dirty": False,
        }
    return {
        "repository_id": state.repository_id,
        "ingestion_status": repository.ingestion_status.value,
        "ingestion_error": repository.ingestion_error,
        "indexed_commit_sha": state.indexed_commit_sha,
        "indexed_at": state.indexed_at.isoformat(),
        "file_count": state.file_count,
        "symbol_count": state.symbol_count,
        "skipped_count": state.skipped_count,
        "working_tree_dirty": state.working_tree_dirty,
    }


def _lexical_score(query: str, tokens: list[str], symbol: CodeSymbol, file: IndexedFile) -> float:
    name = symbol.name.lower()
    qualified = symbol.qualified_name.lower()
    path = file.relative_path.lower()
    source = symbol.source_text.lower()
    score = 0.0
    if query.lower() == name or query.lower() == qualified:
        score += 5.0
    if query.lower() in qualified:
        score += 3.0
    if query.lower() in path:
        score += 2.0
    hits = sum(1 for token in tokens if token in name or token in qualified or token in path or token in source)
    score += hits / max(len(tokens), 1) * 2.0
    return score


async def search_code(
    db: AsyncSession,
    repository_id: str,
    query: str,
    limit: int = 20,
    path_filter: str | None = None,
) -> dict[str, Any]:
    """Search indexed symbols/chunks with an explainable lexical baseline."""
    state = await get_index_status(db, repository_id)
    tokens = list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", query.lower())))[:12]
    if not tokens:
        return {"query": query, "results": [], "total": 0, "index": await get_index_status(db, repository_id)}
    predicates = []
    for token in tokens:
        escaped_token = token.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_token}%"
        predicates.extend(
            [
                CodeSymbol.name.ilike(pattern, escape="\\"),
                CodeSymbol.qualified_name.ilike(pattern, escape="\\"),
                CodeSymbol.source_text.ilike(pattern, escape="\\"),
                IndexedFile.relative_path.ilike(pattern, escape="\\"),
            ]
        )
    statement = (
        select(CodeSymbol, IndexedFile)
        .join(IndexedFile, IndexedFile.id == CodeSymbol.file_id)
        .where(CodeSymbol.repository_id == repository_id, or_(*predicates))
    )
    if path_filter:
        statement = statement.where(IndexedFile.relative_path.ilike(f"%{path_filter}%"))
    rows = (await db.execute(statement.limit(1000))).all()
    ranked = sorted(
        rows,
        key=lambda row: _lexical_score(query, tokens, row[0], row[1]),
        reverse=True,
    )[: min(max(limit, 1), 50)]
    results = []
    for symbol, file in ranked:
        score = _lexical_score(query, tokens, symbol, file)
        results.append(
            {
                "file_path": file.relative_path,
                "language": file.language,
                "symbol": symbol.name,
                "qualified_name": symbol.qualified_name,
                "kind": symbol.kind,
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
                "signature": symbol.signature,
                "source_text": symbol.source_text[:12000],
                "source_truncated": len(symbol.source_text) > 12000,
                "indexed_commit_sha": file.indexed_commit_sha,
                "freshness": "indexed_snapshot",
                "relevance_score": round(score, 3),
                "relevance_reason": "Lexical matches across symbol name, file path, and indexed source.",
            }
        )
    return {
        "query": query,
        "results": results,
        "total": len(rows),
        "index": state,
    }
