-- Track processed webhook events to prevent duplicates
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS processed_webhooks (
    id BIGSERIAL PRIMARY KEY,
    message_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(message_id, user_id)
);

-- Index for fast duplicate lookups
CREATE INDEX IF NOT EXISTS idx_processed_webhooks_lookup
ON processed_webhooks(message_id, user_id);

-- Comment for documentation
COMMENT ON TABLE processed_webhooks IS 'Tracks processed Gmail webhook events to ensure idempotency';
COMMENT ON COLUMN processed_webhooks.message_id IS 'Gmail message ID from webhook payload';
COMMENT ON COLUMN processed_webhooks.user_id IS 'User ID (external_user_id from Pipedream)';
