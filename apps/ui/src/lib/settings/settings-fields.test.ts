import { describe, expect, it } from 'vitest';
import { RUNTIME_DISCLOSURES } from './runtime-problem';
import { changedFields, firstRefusedField, settingsFieldPart, settingsFieldPlace, settingsFieldPlaces, settingsFieldSection, summarizeUnsaved } from './settings-fields';

// Every Settings part's markup, to check each refused field's place against what is really there.
const settingsMarkup = import.meta.glob<string>(['../components/settings/*.svelte', '../components/settings/sections/*.svelte', '../pages/Settings.svelte'], {
    query: '?raw',
    import: 'default',
    eager: true
});

/** The file that holds an element with this id, written as an attribute or as a string constant. */
function fileWithId(id: string): string | null {
    const attribute = new RegExp(`id="${id}"`);
    const constant = new RegExp(`['"]${id}['"]`);
    return Object.entries(settingsMarkup).find(([, source]) => attribute.test(source) || constant.test(source))?.[0] ?? null;
}

describe('where a saved setting lives', () => {
    it('names the part that shows each field, preferring an exact entry over a family prefix', () => {
        expect(settingsFieldPart('frigate_url')).toBe('connection');
        expect(settingsFieldPart('mqtt_port')).toBe('connection');
        expect(settingsFieldPart('notifications_discord_webhook_url')).toBe('notifications');
        // Garden's alerts are set with the rest of Garden.
        expect(settingsFieldPart('garden_notifications_enabled')).toBe('beta');
        expect(settingsFieldPart('garden_cameras')).toBe('connection');
        // Garden's naming threshold is set in the naming card, beside the birds' one.
        expect(settingsFieldPart('garden_naming_threshold')).toBe('detection');
        expect(settingsFieldPart('inaturalist_default_latitude')).toBe('integrations');
        expect(settingsFieldPart('llm_api_key')).toBe('ai');
        expect(settingsFieldPart('media_cache_max_size_mb')).toBe('data');
        expect(settingsFieldPart('enrichment_sightings_source')).toBe('integrations');
    });

    it('keeps identification rules in Detection and everything about the models in Models', () => {
        for (const field of ['classification_threshold', 'classification_min_confidence', 'blocked_species', 'range_filter_enabled', 'trust_frigate_sublabel', 'auto_video_classification', 'video_classification_frames', 'personalized_rerank_enabled']) {
            expect(settingsFieldPart(field), field).toBe('detection');
        }
        for (const field of ['inference_provider', 'image_execution_mode', 'live_worker_count', 'background_worker_count', 'bird_crop_detector_model_id', 'bird_model_region_override', 'strict_non_finite_output']) {
            expect(settingsFieldPart(field), field).toBe('models');
        }
    });

    it('keeps what is kept in Data, repair jobs in Maintenance, and what leaves the install in Security', () => {
        expect(settingsFieldPart('retention_days')).toBe('data');
        expect(settingsFieldPart('frigate_missing_behavior')).toBe('data');
        expect(settingsFieldPart('auto_purge_missing_clips')).toBe('data');
        expect(settingsFieldPart('maintenance_max_concurrent')).toBe('maintenance');
        expect(settingsFieldPart('auto_analyze_unknowns')).toBe('maintenance');
        expect(settingsFieldPart('telemetry_enabled')).toBe('security');
    });

    it('has no home for a field Settings never shows', () => {
        expect(settingsFieldPart('not_a_setting')).toBeNull();
        expect(settingsFieldSection('not_a_setting')).toBeNull();
    });

    it('names the section that holds each part', () => {
        expect(settingsFieldSection('frigate_url')).toBe('cameras');
        expect(settingsFieldSection('classification_threshold')).toBe('identification');
        expect(settingsFieldSection('inference_provider')).toBe('identification');
        expect(settingsFieldSection('garden_naming_threshold')).toBe('identification');
        expect(settingsFieldSection('notifications_discord_webhook_url')).toBe('alerts');
        expect(settingsFieldSection('llm_api_key')).toBe('sharing');
        expect(settingsFieldSection('auth_password')).toBe('sharing');
        expect(settingsFieldSection('retention_days')).toBe('storage');
        expect(settingsFieldSection('maintenance_max_concurrent')).toBe('storage');
        expect(settingsFieldSection('accessibility_high_contrast')).toBe('display');
    });

    it('gives the appearance fields saved under their appearance_ names a home', () => {
        for (const field of ['appearance_font_theme', 'appearance_color_theme', 'appearance_explorer_view']) {
            expect(settingsFieldSection(field), field).toBe('display');
        }
    });
});

describe('the unsaved-changes summary', () => {
    it('counts each changed setting once and lists its sections in navigation order', () => {
        expect(summarizeUnsaved(['llm_model', 'mqtt_port', 'frigate_url', 'mqtt_port', 'threshold_nope'])).toEqual({
            count: 4,
            sections: ['cameras', 'sharing']
        });
        expect(summarizeUnsaved(['retention_days', 'auto_analyze_unknowns'])).toEqual({ count: 2, sections: ['storage'] });
    });

    it('is empty when nothing differs from what is saved', () => {
        expect(summarizeUnsaved([])).toEqual({ count: 0, sections: [] });
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

    it('has no input for a field shown some other way, and every place belongs to a part', () => {
        expect(settingsFieldPlace('cameras')).toBeNull();
        for (const field of ['frigate_url', 'audio_buffer_hours', 'auth_password', 'garden_naming_threshold']) {
            expect(settingsFieldPart(field)).not.toBeNull();
        }
    });
});

describe('which refused field is shown first', () => {
    it('prefers one in the open section, then the first in navigation order', () => {
        expect(firstRefusedField(['mqtt_port', 'llm_model'], 'sharing')).toBe('llm_model');
        expect(firstRefusedField(['llm_model', 'garden_naming_threshold', 'mqtt_port'], 'storage')).toBe('mqtt_port');
        expect(firstRefusedField(['llm_model', 'garden_naming_threshold'], 'display')).toBe('garden_naming_threshold');
        expect(firstRefusedField([], 'cameras')).toBeNull();
    });
});

describe('where a refused field is shown', () => {
    it('names, for every field, an input and closed sections that exist in the same part\'s markup', () => {
        const problems: string[] = [];
        for (const [field, place] of settingsFieldPlaces()) {
            const inputFile = fileWithId(place.inputId);
            if (!inputFile) {
                problems.push(`${field}: no element with id ${place.inputId}`);
                continue;
            }
            for (const disclosure of place.disclosures ?? []) {
                const source = settingsMarkup[inputFile];
                // A section's More options is drawn by the section around the part that holds the input.
                const more = /^settings-more-(\w+)$/.exec(disclosure);
                if (more) {
                    const opened = Object.values(settingsMarkup).some((markup) => markup.includes(`<SectionMore section="${more[1]}"`));
                    if (!opened) problems.push(`${field}: no section draws ${disclosure}`);
                    continue;
                }
                // The runtime sections take their ids from one shared list (runtime-problem.ts).
                const shared = (RUNTIME_DISCLOSURES as readonly string[]).indexOf(disclosure);
                const named = new RegExp(`id="${disclosure}"|['"]${disclosure}['"]`).test(source)
                    || (shared >= 0 && source.includes(`RUNTIME_DISCLOSURES[${shared}]`));
                if (!named) {
                    problems.push(`${field}: section ${disclosure} is not in ${inputFile}, which holds ${place.inputId}`);
                }
            }
        }
        expect(problems).toEqual([]);
    });

    it('opens More options only for a field inside it', () => {
        expect(settingsFieldPlace('frigate_url')?.disclosures ?? []).toEqual([]);
        expect(settingsFieldPlace('mqtt_server')?.disclosures ?? []).toEqual([]);
        expect(settingsFieldPlace('frigate_external_url')?.disclosures).toEqual(['settings-more-cameras']);
        expect(settingsFieldPlace('recording_clip_before_seconds')?.disclosures).toEqual(['settings-more-cameras', 'connection-full-visit']);
        expect(settingsFieldPlace('audio_buffer_hours')?.disclosures).toEqual(['settings-more-cameras', 'integrations-birdnet-advanced']);
    });

    it('shows a refused concurrency on Maintenance with nothing to open, since Jobs at once is a plain section', () => {
        expect(settingsFieldPlace('maintenance_max_concurrent')?.disclosures ?? []).toEqual([]);
    });
});
