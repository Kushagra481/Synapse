"""Read-only, incremental repository indexing and lexical code retrieval."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git import Repo
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tree_sitter import Language, Parser

from app.core.config import settings
from app.models.code_index import CodeImport, CodeSymbol, IndexedFile, RepositoryIndexState
from app.models.memory_fact import ProjectMemoryFact
from app.models.repository import IngestionStatus, Repository
from app.services.embeddings import embed_code_items, embedding_text
from app.services.graph_index import related_file_ids, sync_repository_graph
from app.services.jev import score_relevance


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
    imports: list[dict[str, Any]]


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


def _tree_sitter_parse(content: str, language_name: str):
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
    return tree, symbols, tree.root_node.has_error


def _tree_sitter_symbols(content: str, language_name: str) -> tuple[list[dict[str, Any]], bool]:
    _, symbols, has_error = _tree_sitter_parse(content, language_name)
    return symbols, has_error


IMPORT_NODE_TYPES = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
    "java": {"import_declaration"},
    "cpp": {"preproc_include"},
}


def _tree_sitter_imports(tree, source: bytes, language_name: str) -> list[dict[str, Any]]:
    imports: list[dict[str, Any]] = []
    accepted = IMPORT_NODE_TYPES.get(language_name, set())

    def target_for(statement: str) -> list[str]:
        value = statement.strip()
        if language_name == "python":
            from_match = re.match(r"from\s+([.\w]+)\s+import\b", value)
            if from_match:
                return [from_match.group(1)]
            imported = re.sub(r"^import\s+", "", value)
            return [part.strip().split(" as ")[0] for part in imported.split(",") if part.strip()]
        quoted = re.search(r"""['"]([^'"]+)['"]""", value)
        if quoted:
            return [quoted.group(1)]
        angle = re.search(r"<([^>]+)>", value)
        if angle:
            return [angle.group(1)]
        if language_name == "java":
            value = re.sub(r"^import\s+(?:static\s+)?", "", value)
            return [value.rstrip(";").strip()] if value else []
        return []

    def walk(node) -> None:
        if node.type in accepted:
            statement = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
            for target in target_for(statement):
                if target:
                    imports.append(
                        {
                            "target_module": target[:1024],
                            "statement": statement[:2000],
                            "start_line": node.start_point.row + 1,
                        }
                    )
        for child in node.named_children:
            walk(child)

    walk(tree.root_node)
    return imports


def _resolve_import_path(
    source_path: str, target: str, language: str | None, available: set[str]
) -> str | None:
    """Resolve only deterministic, repository-local import paths."""
    candidates: list[str] = []
    source_dir = Path(source_path).parent
    if language in {"javascript", "typescript", "tsx"} and target.startswith("."):
        base = Path(os.path.normpath((source_dir / target).as_posix()))
        candidates.append(base.as_posix())
        for suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"):
            candidates.append(base.as_posix() + suffix)
            candidates.append((base / ("index" + suffix)).as_posix())
    elif language == "cpp":
        base = Path(os.path.normpath((source_dir / target).as_posix()))
        candidates.extend((base.as_posix(), target))
    elif language == "java":
        module_path = Path(target.replace(".", "/"))
        candidates.append(module_path.as_posix() + ".java")
    elif language == "python":
        dotted = target.lstrip(".")
        if target.startswith("."):
            base = source_dir
            for _ in range(max(len(target) - len(target.lstrip(".")) - 1, 0)):
                base = base.parent
            module_path = base / dotted.replace(".", "/") if dotted else base
        else:
            module_path = Path(dotted.replace(".", "/"))
        candidates.extend(
            (module_path.as_posix() + ".py", (module_path / "__init__.py").as_posix())
        )
    for candidate in candidates:
        normalized = os.path.normpath(candidate).replace("\\", "/")
        if normalized in available:
            return normalized
    return None


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
    imports: list[dict[str, Any]] = []
    if language:
        tree, symbols, has_error = _tree_sitter_parse(text, language)
        imports = _tree_sitter_imports(tree, raw, language)
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
        imports=imports,
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
    repository_name = repository.name
    root, git_repo = validate_repository_path(repository.local_path)
    commit_sha = git_repo.head.commit.hexsha if git_repo.head.is_valid() else None
    prior_state = await db.get(RepositoryIndexState, repository_id)
    prior_embedding_model = prior_state.embedding_model if prior_state else None
    embedding_provider = settings.EMBEDDING_PROVIDER.strip().lower()
    embedding_config = (
        f"{embedding_provider}:{settings.EMBEDDING_MODEL}:{settings.EMBEDDING_DIMENSION}"
        if settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD and embedding_provider in {"openai", "ollama"}
        else None
    )
    embedding_reconfigure = bool(embedding_config and prior_embedding_model != embedding_config)
    if embedding_reconfigure:
        force = True
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

        available_paths = {snapshot.relative_path for snapshot in snapshots}
        for snapshot in snapshots:
            for import_row in snapshot.imports:
                import_row["target_file_path"] = _resolve_import_path(
                    snapshot.relative_path,
                    import_row["target_module"],
                    snapshot.language,
                    available_paths,
                )

        existing_rows = (
            await db.scalars(select(IndexedFile).where(IndexedFile.repository_id == repository_id))
        ).all()
        existing = {row.relative_path: row for row in existing_rows}
        if not settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD or embedding_reconfigure:
            # Opting out or changing model/config removes stale stored vectors.
            await db.execute(
                update(CodeSymbol)
                .where(CodeSymbol.repository_id == repository_id)
                .values(embedding=None)
            )
        current_paths = {snapshot.relative_path for snapshot in snapshots}
        removed_paths = set(existing) - current_paths
        added_count = changed_count = unchanged_count = symbol_count = 0
        pending_symbols: list[tuple[FileSnapshot, dict[str, Any]]] = []
        for snapshot in snapshots:
            prior = existing.get(snapshot.relative_path)
            if prior is None or prior.content_sha256 != snapshot.content_sha256 or force:
                pending_symbols.extend((snapshot, symbol) for symbol in snapshot.symbols)

        embedding_limit = max(settings.MAX_EMBEDDINGS_PER_INDEX, 0)
        embedded_items = pending_symbols[:embedding_limit]
        embedding_batch = await embed_code_items(
            [embedding_text(file.relative_path, symbol) for file, symbol in embedded_items]
        )
        for (_, symbol), vector in zip(embedded_items, embedding_batch.vectors):
            if vector is not None:
                symbol["embedding"] = vector
            else:
                symbol.pop("embedding", None)
        for _, symbol in pending_symbols[len(embedded_items) :]:
            symbol.pop("embedding", None)
        embedding_status = embedding_batch.status
        if len(pending_symbols) > embedding_limit and embedding_status == "ready":
            embedding_status = "partial_limit"

        for relative_path in removed_paths:
            row = existing[relative_path]
            await db.execute(delete(CodeImport).where(CodeImport.file_id == row.id))
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
                await db.execute(delete(CodeImport).where(CodeImport.file_id == prior.id))
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
            for import_row in snapshot.imports:
                db.add(
                    CodeImport(
                        id=_stable_id(
                            f"import:{repository_id}:{snapshot.relative_path}:"
                            f"{import_row['target_module']}:{import_row['start_line']}"
                        ),
                        repository_id=repository_id,
                        file_id=file_row.id,
                        **import_row,
                    )
                )

        state = await db.get(RepositoryIndexState, repository_id)
        now = datetime.now(timezone.utc)
        import_count = sum(len(snapshot.imports) for snapshot in snapshots)
        await db.flush()
        if (
            settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD
            and embedding_status in {"ready", "empty"}
        ):
            remaining_embedding_budget = max(embedding_limit - len(embedded_items), 0)
            if remaining_embedding_budget:
                missing_vectors = (
                    await db.execute(
                        select(CodeSymbol, IndexedFile)
                        .join(IndexedFile, IndexedFile.id == CodeSymbol.file_id)
                        .where(
                            CodeSymbol.repository_id == repository_id,
                            CodeSymbol.embedding.is_(None),
                        )
                        .order_by(IndexedFile.relative_path, CodeSymbol.start_line)
                        .limit(remaining_embedding_budget)
                    )
                ).all()
                if missing_vectors:
                    backfill = await embed_code_items(
                        [
                            embedding_text(
                                file.relative_path,
                                {
                                    "qualified_name": symbol.qualified_name,
                                    "kind": symbol.kind,
                                    "signature": symbol.signature,
                                    "source_text": symbol.source_text,
                                },
                            )
                            for symbol, file in missing_vectors
                        ]
                    )
                    if backfill.status == "ready":
                        for (symbol, _), vector in zip(missing_vectors, backfill.vectors):
                            if vector is not None:
                                symbol.embedding = vector
                    else:
                        embedding_status = backfill.status
        await db.flush()
        stored_embedding_count = await db.scalar(
            select(func.count())
            .select_from(CodeSymbol)
            .where(CodeSymbol.repository_id == repository_id, CodeSymbol.embedding.is_not(None))
        ) or 0
        total_symbol_count = await db.scalar(
            select(func.count()).select_from(CodeSymbol).where(CodeSymbol.repository_id == repository_id)
        ) or 0
        if (
            embedding_config
            and stored_embedding_count < total_symbol_count
            and embedding_status in {"ready", "empty"}
        ):
            embedding_status = "partial_limit"
        current_hashes = {snapshot.relative_path: snapshot.content_sha256 for snapshot in snapshots}
        repository_facts = (
            await db.scalars(
                select(ProjectMemoryFact).where(
                    ProjectMemoryFact.repository_id == repository_id,
                    ProjectMemoryFact.source_file_path.is_not(None),
                    ProjectMemoryFact.deleted_at.is_(None),
                    ProjectMemoryFact.superseded_by_id.is_(None),
                )
            )
        ).all()
        for fact in repository_facts:
            fact.is_stale = (
                current_hashes.get(fact.source_file_path) != fact.source_content_sha256
            )
        values = {
            "indexed_commit_sha": commit_sha,
            "indexed_at": now,
            "file_count": len(snapshots),
            "symbol_count": symbol_count,
            "import_count": import_count,
            "skipped_count": skipped_count,
            "working_tree_dirty": git_repo.is_dirty(untracked_files=True),
            "embedding_status": embedding_status,
            "embedding_model": embedding_config,
            "embedding_count": stored_embedding_count,
            "graph_sync_status": "pending",
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
        graph_sync_status = await sync_repository_graph(
            db, repository_id, repository_name, commit_sha
        )
        refreshed_state = await db.get(RepositoryIndexState, repository_id)
        if refreshed_state:
            refreshed_state.graph_sync_status = graph_sync_status
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
            "embedding_status": embedding_status,
            "embedding_model": embedding_config,
            "embedding_count": stored_embedding_count,
            "import_count": import_count,
            "graph_sync_status": graph_sync_status,
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
            "import_count": 0,
            "skipped_count": 0,
            "working_tree_dirty": False,
            "embedding_status": "disabled",
            "embedding_model": None,
            "embedding_count": 0,
            "graph_sync_status": "pending",
        }
    return {
        "repository_id": state.repository_id,
        "ingestion_status": repository.ingestion_status.value,
        "ingestion_error": repository.ingestion_error,
        "indexed_commit_sha": state.indexed_commit_sha,
        "indexed_at": state.indexed_at.isoformat(),
        "file_count": state.file_count,
        "symbol_count": state.symbol_count,
        "import_count": state.import_count,
        "skipped_count": state.skipped_count,
        "working_tree_dirty": state.working_tree_dirty,
        "embedding_status": state.embedding_status,
        "embedding_model": state.embedding_model,
        "embedding_count": state.embedding_count,
        "graph_sync_status": state.graph_sync_status,
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


def _ranked_freshness(file: IndexedFile, root: Path | None, current_commit: str | None) -> str:
    if root is None:
        return "unknown"
    path = root / file.relative_path
    try:
        if path.is_symlink():
            return "stale_file_symlink"
        resolved = path.resolve(strict=True)
        if root not in resolved.parents or resolved.is_symlink() or not resolved.is_file():
            return "stale_file_missing"
        if resolved.stat().st_size > settings.MAX_FILE_SIZE_BYTES:
            return "stale_file_oversize"
        current_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except FileNotFoundError:
        return "stale_file_missing"
    except (OSError, RuntimeError):
        return "unknown"
    if current_hash != file.content_sha256:
        return "stale_file_changed"
    if current_commit and file.indexed_commit_sha and current_commit != file.indexed_commit_sha:
        return "file_matches_newer_commit"
    return "file_matches_working_tree"


async def search_code(
    db: AsyncSession,
    repository_id: str,
    query: str,
    limit: int = 20,
    path_filter: str | None = None,
    ranking_profile: str = "hybrid",
) -> dict[str, Any]:
    """Fuse exact, lexical, optional semantic, and graph-neighbor evidence."""
    if ranking_profile not in {"lexical", "hybrid", "jev"}:
        raise RepositoryIndexError("Unsupported retrieval profile.")
    hybrid_profile = ranking_profile in {"hybrid", "jev"}
    started = time.perf_counter()
    state = await get_index_status(db, repository_id)
    tokens = list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", query.lower())))[:12]
    if not tokens:
        return {
            "query": query,
            "results": [],
            "total": 0,
            "index": state,
            "retrieval": {"method": "reciprocal_rank_fusion", "signals": [], "latency_ms": 0},
        }
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
    lexical_rows = sorted(
        rows,
        key=lambda row: _lexical_score(query, tokens, row[0], row[1]),
        reverse=True,
    )[:100]

    exact_rows = []
    if hybrid_profile:
        exact_rows = (
            await db.execute(
                select(CodeSymbol, IndexedFile)
                .join(IndexedFile, IndexedFile.id == CodeSymbol.file_id)
                .where(
                    CodeSymbol.repository_id == repository_id,
                    or_(
                        func.lower(CodeSymbol.name) == query.lower(),
                        func.lower(CodeSymbol.qualified_name) == query.lower(),
                    ),
                )
                .limit(100)
            )
        ).all()
        if path_filter:
            exact_rows = [
                row for row in exact_rows if path_filter.lower() in row[1].relative_path.lower()
            ]

    channels: dict[str, list[tuple[CodeSymbol, IndexedFile]]] = {"lexical": lexical_rows}
    if hybrid_profile and exact_rows:
        channels["exact_symbol"] = exact_rows

    vector_status = (
        "disabled_by_policy"
        if not settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD
        else "provider_disabled"
        if settings.EMBEDDING_PROVIDER.strip().lower() in {"", "none"}
        else "database_not_postgres"
    )
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if hybrid_profile and dialect == "postgresql" and settings.EMBEDDINGS_ALLOW_SOURCE_UPLOAD:
        vector_batch = await embed_code_items([query])
        vector_status = vector_batch.status
        if vector_batch.vectors and vector_batch.vectors[0] is not None:
            distance = CodeSymbol.embedding.cosine_distance(vector_batch.vectors[0])
            vector_stmt = (
                select(CodeSymbol, IndexedFile)
                .join(IndexedFile, IndexedFile.id == CodeSymbol.file_id)
                .where(CodeSymbol.repository_id == repository_id, CodeSymbol.embedding.is_not(None))
                .order_by(distance)
                .limit(100)
            )
            if path_filter:
                vector_stmt = vector_stmt.where(IndexedFile.relative_path.ilike(f"%{path_filter}%"))
            channels["semantic"] = (await db.execute(vector_stmt)).all()

    base_file_ids = list(dict.fromkeys(file.id for _, file in lexical_rows[:12]))
    related_ids = (
        await related_file_ids(repository_id, base_file_ids)
        if hybrid_profile
        else []
    )
    related_rows: list[tuple[CodeSymbol, IndexedFile]] = []
    if related_ids:
        graph_stmt = (
            select(CodeSymbol, IndexedFile)
            .join(IndexedFile, IndexedFile.id == CodeSymbol.file_id)
            .where(CodeSymbol.repository_id == repository_id, IndexedFile.id.in_(related_ids))
            .limit(100)
        )
        if path_filter:
            graph_stmt = graph_stmt.where(IndexedFile.relative_path.ilike(f"%{path_filter}%"))
        related_rows = (await db.execute(graph_stmt)).all()
        if related_rows:
            channels["graph_import"] = related_rows

    candidates: dict[str, tuple[CodeSymbol, IndexedFile]] = {}
    signals: dict[str, dict[str, float]] = {}
    weights = {"lexical": 1.0, "exact_symbol": 1.5, "semantic": 1.0, "graph_import": 0.55}
    rrf_k = 60
    for channel, channel_rows in channels.items():
        for rank, (symbol, file) in enumerate(channel_rows, start=1):
            candidates[symbol.id] = (symbol, file)
            signals.setdefault(symbol.id, {})[channel] = weights[channel] / (rrf_k + rank)
    ranked_by_local = sorted(
        candidates.values(),
        key=lambda pair: sum(signals[pair[0].id].values()),
        reverse=True,
    )
    jev_used = False
    jev_status = "not_requested"
    if ranking_profile == "jev":
        if not settings.JEV_ALLOW_SOURCE_UPLOAD:
            jev_status = "disabled_by_policy"
        elif not settings.TYPESAFE_API_KEY.strip():
            jev_status = "missing_credentials"
        else:
            jev_candidates = ranked_by_local[:32]
            jev_items = [
                {
                    "kind": "repository code",
                    "content": (
                        f"File: {file.relative_path}\n"
                        f"Symbol: {symbol.qualified_name}\n"
                        f"Kind: {symbol.kind}\n"
                        f"Signature: {symbol.signature}\n"
                        f"Source:\n{symbol.source_text[:1400]}"
                    ),
                }
                for symbol, file in jev_candidates
            ]
            jev_scores = await score_relevance(query, jev_items)
            if jev_scores and len(jev_scores) == len(jev_candidates):
                jev_used = True
                jev_status = "ranked"
                for (symbol, _), score in zip(jev_candidates, jev_scores):
                    signals[symbol.id]["jev"] = max(0.0, min(float(score), 1.0))
            else:
                jev_status = "unavailable_fallback"
    ranked = sorted(
        candidates.values(),
        key=lambda pair: (
            signals[pair[0].id].get("jev", -1.0) if jev_used else 0.0,
            sum(value for key, value in signals[pair[0].id].items() if key != "jev"),
        ),
        reverse=True,
    )[: min(max(limit, 1), 50)]
    repository = await db.get(Repository, repository_id)
    root: Path | None = None
    current_commit: str | None = None
    current_dirty: bool | None = None
    if repository:
        try:
            root, git_repo = validate_repository_path(repository.local_path)
            current_commit = git_repo.head.commit.hexsha if git_repo.head.is_valid() else None
            current_dirty = git_repo.is_dirty(untracked_files=True)
        except RepositoryIndexError:
            root = None

    results = []
    for rank_position, (symbol, file) in enumerate(ranked, start=1):
        score = sum(signals[symbol.id].values())
        current_freshness = _ranked_freshness(file, root, current_commit)
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
                "current_commit_sha": current_commit,
                "freshness": current_freshness,
                "relevance_score": round(score, 6),
                "retrieval_rank": rank_position,
                "relevance_reason": (
                    "Jev relevance probability with local hybrid signals as tie-breakers"
                    if jev_used
                    else "Reciprocal-rank fusion using " + ", ".join(signals[symbol.id])
                ),
                "ranking_signals": signals[symbol.id],
            }
        )
    return {
        "query": query,
        "results": results,
        "total": len(candidates),
        "index": state,
        "retrieval": {
            "method": "reciprocal_rank_fusion",
            "profile": "jev" if jev_used else ("hybrid_fallback" if ranking_profile == "jev" else ranking_profile),
            "requested_profile": ranking_profile,
            "jev_used": jev_used,
            "jev_status": jev_status,
            "signals": sorted({channel for signal in signals.values() for channel in signal}),
            "semantic_status": vector_status,
            "graph_neighbor_count": len(related_ids),
            "current_working_tree_dirty": current_dirty,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "estimated_context_tokens": sum(
                max(1, (len(row[0].source_text) + 3) // 4) for row in ranked
            ),
        },
    }
