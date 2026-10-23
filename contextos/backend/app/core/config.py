"""
ContextOS — Application Settings

Uses Pydantic BaseSettings for environment variable loading.
All configuration comes from the .env file or environment variables.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object. All values are sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "ContextOS"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    SECRET_KEY: str = Field(default="dev-secret-key-change-in-production")

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://contextos:contextos_secret@localhost:5432/contextos"
    )
    # Sync URL for Alembic migrations (asyncpg → psycopg2)
    @property
    def DATABASE_URL_SYNC(self) -> str:
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # ── Neo4j ─────────────────────────────────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "contextos_neo4j"
    NEO4J_DATABASE: str = "neo4j"

    # ── Embeddings ────────────────────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "openai"   # openai | ollama | none
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # ── LLM ──────────────────────────────────────────────────────────────────
    LLM_PROVIDER: str = "openai"          # openai | anthropic | gemini | ollama
    LLM_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    TYPESAFE_API_KEY: str = ""

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # ── Repository Storage ────────────────────────────────────────────────────
    REPO_CACHE_DIR: str = ".repo_cache"
    MAX_FILE_SIZE_BYTES: int = 524288  # 512 KB
    MAX_INDEXED_FILES: int = 10000
    MAX_INDEXED_TOTAL_BYTES: int = 104857600  # 100 MB per indexing run
    # Comma-separated absolute/relative roots that local indexing is allowed to read.
    REPO_ALLOWED_ROOTS: str = ".repo_cache"

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | text

    # ── Security ─────────────────────────────────────────────────────────────
    # Files/patterns to never index (security-sensitive)
    EXCLUDED_PATTERNS: List[str] = [
        ".env", ".env.*", "*.pem", "*.key", "*.cert",
        "credentials", "*secret*", "*password*", "*token*",
        ".git", "node_modules", "__pycache__", "venv", ".venv",
        "dist", "build", "target",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()


settings = get_settings()
