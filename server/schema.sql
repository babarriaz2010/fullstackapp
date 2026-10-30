-- Run explicitly with: python -m server.init_db
-- All statements run in one transaction; repeated initialization is safe.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Original files are retained for small uploads; existing rows stay intact.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS file_content BYTEA;

CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL,
    page_number INTEGER CHECK (page_number > 0),
    embedding_model TEXT NOT NULL,
    embedding VECTOR NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

-- The unique constraint also indexes document_id for document lookups.
-- Choose embedding dimensions and a vector index when adding the RAG model.
