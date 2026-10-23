"""
ContextOS — Neo4j Graph Database Layer

Provides:
- Async-compatible Neo4j driver initialization
- get_graph_session() context manager for running Cypher queries
- init_graph() / close_graph() lifecycle functions
- Graph schema constraint initialization
"""

from __future__ import annotations

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable

from app.core.config import settings

logger = structlog.get_logger(__name__)

_driver: AsyncDriver | None = None


# ─── Lifecycle ────────────────────────────────────────────────────────────────

async def init_graph() -> None:
    """Initialize the Neo4j driver and verify connectivity."""
    global _driver

    _driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        max_connection_pool_size=50,
    )

    try:
        await _driver.verify_connectivity()
    except ServiceUnavailable as e:
        logger.error("contextos.neo4j.unavailable", error=str(e))
        raise

    # Get server version info
    async with _driver.session(database=settings.NEO4J_DATABASE) as session:
        result = await session.run("CALL dbms.components() YIELD name, versions")
        record = await result.single()
        if record:
            logger.info(
                "contextos.neo4j.version",
                component=record["name"],
                version=record["versions"][0] if record["versions"] else "unknown",
            )

    # Initialize schema constraints
    await _init_graph_schema()


async def close_graph() -> None:
    """Close the Neo4j driver gracefully."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("contextos.neo4j.closed")


def get_driver() -> AsyncDriver:
    """Return the global Neo4j driver."""
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized. Call init_graph() first.")
    return _driver


# ─── Schema Constraints ───────────────────────────────────────────────────────

async def _init_graph_schema() -> None:
    """
    Create Neo4j uniqueness constraints for all core node types.
    Idempotent — safe to run on every startup.
    """
    constraints = [
        # Code entities
        "CREATE CONSTRAINT repo_id IF NOT EXISTS FOR (n:Repository) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT file_id IF NOT EXISTS FOR (n:File) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT dir_id IF NOT EXISTS FOR (n:Directory) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT class_id IF NOT EXISTS FOR (n:Class) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT function_id IF NOT EXISTS FOR (n:Function) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT method_id IF NOT EXISTS FOR (n:Method) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT variable_id IF NOT EXISTS FOR (n:Variable) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT module_id IF NOT EXISTS FOR (n:Module) REQUIRE n.id IS UNIQUE",
        # Memory entities
        "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (n:Task) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT bug_id IF NOT EXISTS FOR (n:Bug) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT decision_id IF NOT EXISTS FOR (n:Decision) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT session_id IF NOT EXISTS FOR (n:Session) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (n:Conversation) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT developer_id IF NOT EXISTS FOR (n:Developer) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT commit_id IF NOT EXISTS FOR (n:Commit) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT feature_id IF NOT EXISTS FOR (n:Feature) REQUIRE n.id IS UNIQUE",
    ]

    driver = get_driver()
    async with driver.session(database=settings.NEO4J_DATABASE) as session:
        for constraint in constraints:
            try:
                await session.run(constraint)
            except Exception as e:
                # Constraint already exists or minor error — log and continue
                logger.debug("contextos.neo4j.constraint_skip", error=str(e))

    logger.info("contextos.neo4j.schema_initialized", constraint_count=len(constraints))


# ─── Session Helper ───────────────────────────────────────────────────────────

class GraphSession:
    """Thin wrapper for running Cypher queries via the Neo4j driver."""

    def __init__(self) -> None:
        self._driver = get_driver()

    async def run(self, query: str, **params) -> list[dict]:
        """Run a Cypher query and return all records as dicts."""
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            result = await session.run(query, **params)
            return [dict(record) async for record in result]

    async def run_one(self, query: str, **params) -> dict | None:
        """Run a Cypher query and return the first record as a dict, or None."""
        records = await self.run(query, **params)
        return records[0] if records else None

    async def execute_write(self, query: str, **params) -> list[dict]:
        """Run a write transaction."""
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            async def work(tx):
                result = await tx.run(query, **params)
                records = [dict(record) async for record in result]
                return records

            return await session.execute_write(work)

    async def run_transaction(self, statements: list[tuple[str, dict]]) -> None:
        """Run a group of parameterized Cypher statements atomically."""
        async with self._driver.session(database=settings.NEO4J_DATABASE) as session:
            async def work(tx):
                for query, params in statements:
                    result = await tx.run(query, **params)
                    await result.consume()

            await session.execute_write(work)


def get_graph_session() -> GraphSession:
    """Return a GraphSession instance (dependency injectable)."""
    return GraphSession()
