CREATE TABLE IF NOT EXISTS health_issue_reports (
    report_key TEXT PRIMARY KEY,
    installation_id_hash TEXT NOT NULL,
    issue_fingerprint TEXT NOT NULL,
    app_version TEXT,
    platform_system TEXT,
    platform_release TEXT,
    platform_machine TEXT,
    issue_source TEXT,
    issue_component TEXT,
    issue_reason_code TEXT,
    issue_stage TEXT,
    severity TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    report_count INTEGER DEFAULT 1,
    occurrence_count INTEGER DEFAULT 0,
    sample_context_json TEXT,
    last_payload_json TEXT,
    ip_country TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_health_issue_last_seen ON health_issue_reports(last_seen_at);
CREATE INDEX IF NOT EXISTS idx_health_issue_fingerprint ON health_issue_reports(issue_fingerprint);
CREATE INDEX IF NOT EXISTS idx_health_issue_component ON health_issue_reports(issue_component);
CREATE INDEX IF NOT EXISTS idx_health_issue_severity ON health_issue_reports(severity);
CREATE INDEX IF NOT EXISTS idx_health_issue_version ON health_issue_reports(app_version);
