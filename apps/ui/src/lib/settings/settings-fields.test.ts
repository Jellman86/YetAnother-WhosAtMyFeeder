import { describe, expect, it } from 'vitest';
import { changedFields, firstRefusedField, settingsFieldPlace, settingsFieldTab, summarizeUnsaved } from './settings-fields';

describe('where a saved setting lives', () => {
    it('names the tab that shows each field, preferring an exact entry over a family prefix', () => {
        expect(settingsFieldTab('frigate_url')).toBe('connection');
        expect(settingsFieldTab('mqtt_port')).toBe('connection');
        expect(settingsFieldTab('notifications_discord_webhook_url')).toBe('notifications');
        // Garden's alerts are set with the rest of Garden.
        expect(settingsFieldTab('garden_notifications_enabled')).toBe('beta');
        expect(settingsFieldTab('garden_cameras')).toBe('connection');
        expect(settingsFieldTab('garden_naming_threshold')).toBe('beta');
        expect(settingsFieldTab('inaturalist_default_latitude')).toBe('integrations');
        expect(settingsFieldTab('llm_api_key')).toBe('ai');
        expect(settingsFieldTab('media_cache_max_size_mb')).toBe('data');
        expect(settingsFieldTab('enrichment_sightings_source')).toBe('integrations');
    });

    it('keeps identification rules in Detection and everything about the models in Models', () => {
        for (const field of ['classification_threshold', 'classification_min_confidence', 'blocked_species', 'range_filter_enabled', 'trust_frigate_sublabel', 'auto_video_classification', 'video_classification_frames', 'personalized_rerank_enabled']) {
            expect(settingsFieldTab(field), field).toBe('detection');
        }
        for (const field of ['inference_provider', 'image_execution_mode', 'live_worker_count', 'background_worker_count', 'bird_crop_detector_model_id', 'bird_model_region_override', 'strict_non_finite_output']) {
            expect(settingsFieldTab(field), field).toBe('models');
        }
    });

    it('keeps what is kept in Data, repair jobs in Maintenance, and what leaves the install in Security', () => {
        expect(settingsFieldTab('retention_days')).toBe('data');
        expect(settingsFieldTab('frigate_missing_behavior')).toBe('data');
        expect(settingsFieldTab('auto_purge_missing_clips')).toBe('data');
        expect(settingsFieldTab('maintenance_max_concurrent')).toBe('maintenance');
        expect(settingsFieldTab('auto_analyze_unknowns')).toBe('maintenance');
        expect(settingsFieldTab('telemetry_enabled')).toBe('security');
    });

    it('has no home for a field Settings never shows', () => {
        expect(settingsFieldTab('not_a_setting')).toBeNull();
    });
});

describe('the unsaved-changes summary', () => {
    it('counts each changed setting once and lists its tabs in navigation order', () => {
        expect(summarizeUnsaved(['llm_model', 'mqtt_port', 'frigate_url', 'mqtt_port'])).toEqual({
            count: 3,
            tabs: ['connection', 'ai']
        });
    });

    it('is empty when nothing differs from what is saved', () => {
        expect(summarizeUnsaved([])).toEqual({ count: 0, tabs: [] });
    });
});

describe('which fields a draft changes', () => {
    it('compares lists by content, so an equal copy is not a change', () => {
        expect(changedFields([
            { field: 'cameras', draft: ['patio'], saved: ['patio'] },
            { field: 'mqtt_port', draft: 1884, saved: 1883 },
            { field: 'location_latitude', draft: null, saved: null },
            { field: 'location_longitude', draft: null, saved: -1.5 }
        ])).toEqual(['mqtt_port', 'location_longitude']);
    });
});

describe('where a refused value is shown', () => {
    it('points each field with its own input at that input and its visible label', () => {
        expect(settingsFieldPlace('mqtt_port')).toEqual({ labelKey: 'settings.frigate.mqtt_port', inputId: 'mqtt-port' });
        expect(settingsFieldPlace('notifications_instance_url')?.inputId).toBe('notification-instance-url');
    });

    it('has no input for a field shown some other way, and every place belongs to a tab', () => {
        expect(settingsFieldPlace('cameras')).toBeNull();
        for (const field of ['frigate_url', 'audio_buffer_hours', 'auth_password', 'garden_naming_threshold']) {
            expect(settingsFieldTab(field)).not.toBeNull();
        }
    });
});

describe('which refused field is shown first', () => {
    it('prefers one on the open tab, then the first in navigation order', () => {
        expect(firstRefusedField(['llm_model', 'mqtt_port'], 'ai')).toBe('llm_model');
        expect(firstRefusedField(['llm_model', 'garden_naming_threshold', 'mqtt_port'], 'security')).toBe('mqtt_port');
        expect(firstRefusedField([], 'connection')).toBeNull();
    });
});
