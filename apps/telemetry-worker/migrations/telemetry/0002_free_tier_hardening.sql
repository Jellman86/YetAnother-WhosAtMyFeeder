CREATE INDEX IF NOT EXISTS idx_heartbeat_daily_last_reported
    ON heartbeat_daily(last_reported_at);

CREATE TABLE IF NOT EXISTS telemetry_maintenance (
    task TEXT PRIMARY KEY,
    last_run_at TEXT NOT NULL,
    rows_removed INTEGER NOT NULL DEFAULT 0
);
