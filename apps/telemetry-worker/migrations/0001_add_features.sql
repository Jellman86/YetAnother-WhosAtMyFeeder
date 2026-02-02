-- Add new feature tracking columns
ALTER TABLE heartbeats ADD COLUMN media_cache_clips BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN auto_video_classification BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN ebird_enabled BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN inaturalist_enabled BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN notifications_discord BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN notifications_pushover BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN notifications_telegram BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN notifications_email BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN enrichment_mode TEXT;
ALTER TABLE heartbeats ADD COLUMN access_auth_enabled BOOLEAN;
ALTER TABLE heartbeats ADD COLUMN access_public_enabled BOOLEAN;
