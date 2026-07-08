-- Migration: persistent user flow state
-- Run once in Supabase Dashboard → SQL Editor

CREATE TABLE IF NOT EXISTS user_states (
    id BIGSERIAL PRIMARY KEY,
    telegram_id TEXT NOT NULL,
    state_data JSONB NOT NULL DEFAULT '{}',
    updated_at TEXT DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS user_states_telegram_id_idx ON user_states(telegram_id);

-- Refresh PostgREST schema cache so the API sees the new table immediately
NOTIFY pgrst, 'reload schema';
