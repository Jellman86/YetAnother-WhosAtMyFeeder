DROP TABLE IF EXISTS heartbeats;

CREATE TABLE heartbeats (
    installation_id TEXT PRIMARY KEY,
    app_version TEXT,
    platform_system TEXT,
    platform_release TEXT,
    platform_machine TEXT,
    model_type TEXT,
    birdnet_enabled BOOLEAN,
    birdweather_enabled BOOLEAN,
    llm_enabled BOOLEAN,
    llm_provider TEXT,
    media_cache_enabled BOOLEAN,
    media_cache_clips BOOLEAN,
    auto_video_classification BOOLEAN,
    ebird_enabled BOOLEAN,
    inaturalist_enabled BOOLEAN,
    notifications_discord BOOLEAN,
    notifications_pushover BOOLEAN,
    notifications_telegram BOOLEAN,
    notifications_email BOOLEAN,
    enrichment_mode TEXT,
    access_auth_enabled BOOLEAN,
    access_public_enabled BOOLEAN,
    ip_country TEXT,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_last_seen ON heartbeats(last_seen);
CREATE INDEX idx_app_version ON heartbeats(app_version);