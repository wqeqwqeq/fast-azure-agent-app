-- ================================================================
-- PostgreSQL Database Initialization Script
-- ================================================================
-- This script initializes the chat_history database with required
-- tables and indexes for the DAPE OpsAgent Manager application.
--
-- Usage: psql -f init.sql
--   Requires PGHOST, PGUSER, PGPORT, PGDATABASE, PGPASSWORD env vars
-- ================================================================

-- Create database if it doesn't exist
-- Note: This must be run from the 'postgres' default database
SELECT 'CREATE DATABASE chat_history'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'chat_history')\gexec

-- Connect to the chat_history database
\c chat_history

-- ================================================================
-- Table: conversations
-- Stores conversation metadata (title, model, timestamps)
-- Each conversation is associated with a user via user_client_id
-- ================================================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id VARCHAR(50) PRIMARY KEY,
    user_client_id VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    model VARCHAR(100) NOT NULL,
    agent_level_llm_overwrite JSONB DEFAULT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_modified TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for efficient user-scoped queries sorted by last_modified
CREATE INDEX IF NOT EXISTS idx_conversations_user_modified
    ON conversations (user_client_id, last_modified DESC);

-- Index for filtering by creation date (for N-day lookups)
CREATE INDEX IF NOT EXISTS idx_conversations_user_created
    ON conversations (user_client_id, created_at DESC);

-- ================================================================
-- Table: messages
-- Stores individual chat messages within conversations
-- sequence_number ensures proper message ordering
-- ================================================================
CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(50) NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_satisfy BOOLEAN DEFAULT NULL,
    comment TEXT DEFAULT NULL,

    -- Ensure unique sequence numbers within each conversation
    CONSTRAINT unique_conversation_sequence UNIQUE (conversation_id, sequence_number)
);

-- Index for efficient message retrieval sorted by sequence
CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
    ON messages (conversation_id, sequence_number ASC);

-- ================================================================
-- Table: memory
-- Stores summarized conversation memory (append-only for audit trail)
-- Each summarization creates a NEW row (not upsert)
-- Empty summaries are NOT written - if no memory, no row exists
-- ================================================================
CREATE TABLE IF NOT EXISTS memory (
    memory_id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(50) NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    -- Track which messages were summarized using sequence from messages table
    start_sequence INTEGER NOT NULL,        -- First message sequence included
    end_sequence INTEGER NOT NULL,          -- Last message sequence included
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generation_time_ms INTEGER DEFAULT NULL -- How long summarization took (observability)
);

-- Index for getting most recent memory per conversation
CREATE INDEX IF NOT EXISTS idx_memory_conversation_latest
    ON memory (conversation_id, end_sequence DESC);

-- ================================================================
-- Verification
-- ================================================================
\echo ''
\echo '✅ Database initialization complete!'
\echo ''
\echo '📊 Tables created:'
SELECT
    schemaname as schema,
    tablename as table_name,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename IN ('conversations', 'messages', 'memory')
ORDER BY tablename;

\echo ''
\echo '🔍 Indexes created:'
SELECT
    schemaname as schema,
    tablename as table_name,
    indexname as index_name
FROM pg_indexes
WHERE schemaname = 'public'
    AND tablename IN ('conversations', 'messages', 'memory')
ORDER BY tablename, indexname;

\echo ''
\echo '🎉 Ready to use!'
