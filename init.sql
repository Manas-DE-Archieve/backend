-- Full database initialization script
-- Run this on a fresh database: psql -U postgres -d postgres -f init_full.sql

-- Required extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- USERS
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          VARCHAR(20) NOT NULL DEFAULT 'user',  -- user | moderator | super_admin
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- DOCUMENTS
CREATE TABLE IF NOT EXISTS documents (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename            TEXT NOT NULL,
    file_type           TEXT,
    raw_text            TEXT,
    status              VARCHAR(20) DEFAULT 'pending',       -- pending | processing | processed | failed_extraction
    verification_status VARCHAR(20) NOT NULL DEFAULT 'verified', -- pending | verified | rejected | auto_rejected
    similarity_score    FLOAT,
    duplicate_of_id     UUID REFERENCES documents(id),
    uploaded_by         UUID REFERENCES users(id),
    uploaded_at         TIMESTAMPTZ DEFAULT NOW(),
    content_hash        TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_documents_verification_status
    ON documents(verification_status, similarity_score DESC NULLS LAST);

-- CHUNKS (requires pgvector)
CREATE TABLE IF NOT EXISTS chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text  TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding   vector(1536),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- CHAT SESSIONS
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID REFERENCES users(id),
    title      TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CHAT MESSAGES
CREATE TABLE IF NOT EXISTS chat_messages (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,  -- user | assistant
    content    TEXT NOT NULL,
    sources    JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- FACTS
CREATE TABLE IF NOT EXISTS facts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES documents(id) ON DELETE CASCADE,
    source_filename TEXT,
    icon            TEXT,
    category        TEXT,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- PERSONS
CREATE TABLE IF NOT EXISTS persons (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id          UUID REFERENCES documents(id),
    full_name            TEXT NOT NULL,
    birth_year           INTEGER,
    death_year           INTEGER,
    region               TEXT,
    district             TEXT,
    occupation           TEXT,
    charge               TEXT,
    arrest_date          DATE,
    sentence             TEXT,
    sentence_date        DATE,
    rehabilitation_date  DATE,
    biography            TEXT,
    source               TEXT,
    status               VARCHAR(20) DEFAULT 'pending',  -- pending | verified | rejected
    name_embedding       vector(1536),
    created_by           UUID REFERENCES users(id),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_persons_document_id ON persons(document_id);