-- Track background email sync jobs
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS sync_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    task_id TEXT,  -- Celery task ID
    status TEXT NOT NULL DEFAULT 'queued',  -- queued, processing, completed, failed
    days INTEGER NOT NULL,
    emails_processed INTEGER DEFAULT 0,
    error_message TEXT,
    progress JSONB,  -- { phase: 'fetching_ids', progress: 50, ... }
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_status CHECK (status IN ('queued', 'processing', 'completed', 'failed'))
);

-- Index for user's sync history
CREATE INDEX IF NOT EXISTS idx_sync_jobs_user
ON sync_jobs(user_id, created_at DESC);

-- Index for active syncs
CREATE INDEX IF NOT EXISTS idx_sync_jobs_status
ON sync_jobs(status, created_at DESC)
WHERE status IN ('queued', 'processing');

-- Index for task lookup
CREATE INDEX IF NOT EXISTS idx_sync_jobs_task_id
ON sync_jobs(task_id)
WHERE task_id IS NOT NULL;

-- Comments for documentation
COMMENT ON TABLE sync_jobs IS 'Tracks background email sync jobs processed by Celery workers';
COMMENT ON COLUMN sync_jobs.user_id IS 'Supabase user ID (same as external_user_id)';
COMMENT ON COLUMN sync_jobs.account_id IS 'Pipedream account ID for Gmail access';
COMMENT ON COLUMN sync_jobs.task_id IS 'Celery task ID for monitoring and status checks';
COMMENT ON COLUMN sync_jobs.status IS 'Job status: queued (waiting for worker), processing (active), completed (done), failed (error)';
COMMENT ON COLUMN sync_jobs.progress IS 'JSON object with current phase and progress percentage';
COMMENT ON COLUMN sync_jobs.duration_seconds IS 'Time taken to complete sync (seconds)';
