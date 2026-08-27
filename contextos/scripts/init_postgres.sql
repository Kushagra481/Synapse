-- ContextOS PostgreSQL initialization script
-- Runs once when the container is first created.

-- Enable pgvector extension for semantic embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable trigram matching for fuzzy text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;
