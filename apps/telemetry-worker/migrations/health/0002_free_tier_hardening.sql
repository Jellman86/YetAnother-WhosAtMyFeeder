CREATE INDEX IF NOT EXISTS idx_health_issue_updated_at
    ON health_issue_reports(updated_at);
CREATE INDEX IF NOT EXISTS idx_health_batches_reported_at
    ON health_report_batches(reported_at);
