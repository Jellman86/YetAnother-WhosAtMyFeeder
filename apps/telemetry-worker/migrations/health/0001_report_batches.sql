CREATE TABLE IF NOT EXISTS health_report_batches (
    report_id TEXT PRIMARY KEY,
    installation_id_hash TEXT NOT NULL,
    report_date TEXT NOT NULL,
    reported_at TEXT NOT NULL,
    app_version TEXT,
    schema_version TEXT,
    country TEXT,
    issue_group_count INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0,
    critical_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    event_groups_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_health_batches_date
    ON health_report_batches(report_date);
CREATE INDEX IF NOT EXISTS idx_health_batches_install_date
    ON health_report_batches(installation_id_hash, report_date);
