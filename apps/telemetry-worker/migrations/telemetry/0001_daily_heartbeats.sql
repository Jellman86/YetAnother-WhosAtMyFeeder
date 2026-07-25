CREATE TABLE IF NOT EXISTS heartbeat_daily (
    report_date TEXT NOT NULL,
    installation_id_hash TEXT NOT NULL,
    last_reported_at TEXT NOT NULL,
    version TEXT,
    channel TEXT,
    platform TEXT,
    machine TEXT,
    inference_provider TEXT,
    configured_inference_provider TEXT,
    model TEXT,
    country TEXT,
    gpu_model TEXT,
    deployment_image TEXT,
    runtime_flavor TEXT,
    compose_flavor TEXT,
    environment TEXT,
    feature_flags TEXT,
    PRIMARY KEY (report_date, installation_id_hash)
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_daily_date
    ON heartbeat_daily(report_date);
CREATE INDEX IF NOT EXISTS idx_heartbeat_daily_version_date
    ON heartbeat_daily(report_date, version);

CREATE TABLE IF NOT EXISTS ingestion_daily_budget (
    budget_date TEXT PRIMARY KEY,
    write_units INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
