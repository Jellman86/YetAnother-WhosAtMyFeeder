-- Inference-health distribution and most-recent recovery context.
-- Status values: 'ok' | 'degraded' | 'unhealthy' (sanitized client-side).
-- Reason values: alphanumeric+underscore identifiers from the classifier
-- service (e.g. live_gpu_lease_expiry_fallback, gpu_unhealthy_fallback).

ALTER TABLE heartbeats ADD COLUMN inference_health_status TEXT;
ALTER TABLE heartbeats ADD COLUMN inference_health_unhealthy_runtimes INTEGER;
ALTER TABLE heartbeats ADD COLUMN inference_health_degraded_runtimes INTEGER;
ALTER TABLE heartbeats ADD COLUMN inference_health_total_runtimes INTEGER;
ALTER TABLE heartbeats ADD COLUMN last_recovery_reason TEXT;
ALTER TABLE heartbeats ADD COLUMN last_recovery_status TEXT;

CREATE INDEX IF NOT EXISTS idx_inference_health_status ON heartbeats(inference_health_status);
CREATE INDEX IF NOT EXISTS idx_last_recovery_reason ON heartbeats(last_recovery_reason);
