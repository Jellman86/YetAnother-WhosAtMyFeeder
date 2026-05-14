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
    model_runtime TEXT,
    inference_provider_configured TEXT,
    inference_provider_active TEXT,
    inference_backend_active TEXT,
    image_execution_mode TEXT,
    bird_crop_detector_tier TEXT,
    cuda_available BOOLEAN,
    nvidia_gpu_detected BOOLEAN,
    openvino_available BOOLEAN,
    intel_gpu_available BOOLEAN,
    openvino_gpu_compile_ok BOOLEAN,
    openvino_gpu_compile_device TEXT,
    openvino_gpu_fallback_active BOOLEAN,
    deployment_mode TEXT,
    image_flavor TEXT,
    image_arch TEXT,
    app_branch TEXT,
    git_hash TEXT,
    inference_health_status TEXT,
    inference_health_unhealthy_runtimes INTEGER,
    inference_health_degraded_runtimes INTEGER,
    inference_health_total_runtimes INTEGER,
    last_recovery_reason TEXT,
    last_recovery_status TEXT,
    ip_country TEXT,
    last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_last_seen ON heartbeats(last_seen);
CREATE INDEX idx_app_version ON heartbeats(app_version);
CREATE INDEX idx_inference_provider_active ON heartbeats(inference_provider_active);
CREATE INDEX idx_image_arch ON heartbeats(image_arch);
CREATE INDEX idx_inference_health_status ON heartbeats(inference_health_status);
CREATE INDEX idx_last_recovery_reason ON heartbeats(last_recovery_reason);
