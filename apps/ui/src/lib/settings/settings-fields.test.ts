import { describe, expect, it } from 'vitest';
import { RUNTIME_DISCLOSURES } from './runtime-problem';
import { settingsMoreId, settingsPartIsInMore } from './settings-more';
import type { SettingsSection } from './settings-route';
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
        // A channel's own settings are in Channels; when to notify is in the rules.
        expect(settingsFieldPart('notifications_discord_webhook_url')).toBe('channels');
        expect(settingsFieldPart('notifications_telegram_include_snapshot')).toBe('channels');
        expect(settingsFieldPart('notifications_notify_on_update')).toBe('rules');
        expect(settingsFieldPart('notifications_filter_min_confidence')).toBe('rules');
        // Garden's alerts send through the bird alert channels, so they are set in Notifications.
        expect(settingsFieldPart('garden_notifications_enabled')).toBe('garden-alerts');
        expect(settingsFieldSection('garden_notifications_enabled')).toBe('notifications');
        expect(settingsFieldPart('garden_cameras')).toBe('connection');
        // Garden's naming threshold is set in the naming card, beside the birds' one.
        expect(settingsFieldPart('garden_naming_threshold')).toBe('detection');
        expect(settingsFieldPart('inaturalist_default_latitude')).toBe('networks');
        // Every external service is set in Integrations, BirdNET-Go and the weather among them.
        for (const field of ['birdnet_url', 'audio_topic', 'camera_audio_mapping', 'ha_weather_entity', 'ebird_api_key', 'birdweather_station_token', 'llm_model', 'enrichment_mode']) {
            expect(settingsFieldSection(field), field).toBe('integrations');
        }
        expect(settingsFieldPart('llm_api_key')).toBe('ai');
        expect(settingsFieldPart('media_cache_max_size_mb')).toBe('data');
        expect(settingsFieldPart('enrichment_sightings_source')).toBe('enrichment');
    });

    it('keeps identification rules in Detection and everything about the models in Models', () => {
        for (const field of ['classification_threshold', 'classification_min_confidence', 'blocked_species', 'range_filter_enabled', 'trust_frigate_sublabel', 'auto_video_classification', 'video_classification_frames', 'personalized_rerank_enabled']) {
            expect(settingsFieldPart(field), field).toBe('detection');
        }
        for (const field of ['inference_provider', 'image_execution_mode', 'live_worker_count', 'background_worker_count', 'bird_crop_detector_model_id', 'bird_model_region_override', 'strict_non_finite_output']) {
            expect(settingsFieldPart(field), field).toBe('models');
        }
    });

    it('keeps what is kept in Data, repair jobs in Maintenance, and what leaves the install in Access & privacy', () => {
        expect(settingsFieldPart('retention_days')).toBe('data');
        expect(settingsFieldPart('frigate_missing_behavior')).toBe('data');
        expect(settingsFieldPart('auto_purge_missing_clips')).toBe('data');
        expect(settingsFieldPart('maintenance_max_concurrent')).toBe('maintenance');
        expect(settingsFieldPart('auto_analyze_unknowns')).toBe('maintenance');
        expect(settingsFieldPart('telemetry_enabled')).toBe('telemetry');
        expect(settingsFieldSection('telemetry_enabled')).toBe('access');
    });

    it('keeps the feeder\'s location on the first screen of Cameras & connection, never in a part under More options', () => {
        for (const field of ['location_latitude', 'location_longitude', 'location_automatic', 'location_state', 'location_country']) {
            const part = settingsFieldPart(field);
            expect(part, field).toBe('location');
            expect(settingsFieldSection(field), field).toBe('cameras');
            expect(settingsPartIsInMore(part ?? 'location'), field).toBe(false);
        }
        expect(settingsPartIsInMore('enrichment')).toBe(true);
        expect(settingsPartIsInMore('telemetry')).toBe(false);
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
        expect(settingsFieldSection('notifications_discord_webhook_url')).toBe('notifications');
        expect(settingsFieldSection('llm_api_key')).toBe('integrations');
        expect(settingsFieldSection('auth_password')).toBe('access');
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
            sections: ['cameras', 'integrations']
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
        expect(firstRefusedField(['mqtt_port', 'llm_model'], 'integrations')).toBe('llm_model');
        expect(firstRefusedField(['llm_model', 'garden_naming_threshold', 'mqtt_port'], 'storage')).toBe('mqtt_port');
        expect(firstRefusedField(['llm_model', 'garden_naming_threshold'], 'display')).toBe('garden_naming_threshold');
        expect(firstRefusedField([], 'cameras')).toBeNull();
    });
});

describe('where a refused field is shown', () => {
    it('names a refused visit gap and leads to its field, rather than calling it another setting (#1044)', () => {
        expect(settingsFieldPlace('visit_gap_seconds')).toEqual({ labelKey: 'settings.visit_gap.label', inputId: 'visit-gap-seconds' });
    });

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
                    if (more[1] !== settingsFieldSection(field)) problems.push(`${field}: opens ${disclosure}, but lives in ${settingsFieldSection(field)}`);
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

    it('opens More options for every field drawn only inside it', () => {
        // The components each section draws inside its More options, and what they draw in turn.
        // A component drawn both inside and outside (one with a main and a more region) is left to
        // the cases below, since which region holds an input is not in the markup alone.
        const fileOf = (component: string): string | undefined =>
            Object.keys(settingsMarkup).find((file) => file.endsWith(`/${component}.svelte`));
        const drawn = (source: string): string[] => [...source.matchAll(/<([A-Z]\w+)[\s>]/g)].map((match) => match[1]);
        const problems: string[] = [];
        for (const [sectionFile, source] of Object.entries(settingsMarkup)) {
            const block = /<SectionMore section="(\w+)"[\s\S]*?<\/SectionMore>/.exec(source);
            if (!block) continue;
            const section = block[1];
            const outside = new Set(drawn(source.replace(block[0], '')));
            const inside = new Set(drawn(block[0]).filter((component) => !outside.has(component) && fileOf(component)));
            for (const component of [...inside]) {
                for (const nested of drawn(settingsMarkup[fileOf(component) ?? ''] ?? '')) if (fileOf(nested)) inside.add(nested);
            }
            const files = new Set([...inside].map(fileOf));
            for (const [field, place] of settingsFieldPlaces()) {
                if (!files.has(fileWithId(place.inputId) ?? '')) continue;
                if (!(place.disclosures ?? []).includes(settingsMoreId(section as SettingsSection))) {
                    problems.push(`${field}: drawn inside ${section}'s More options (${sectionFile}) without opening it`);
                }
            }
        }
        expect(problems).toEqual([]);
    });

    it('opens More options only for a field inside it', () => {
        expect(settingsFieldPlace('location_latitude')?.disclosures ?? []).toEqual([]);
        expect(settingsFieldPlace('ebird_max_results')?.disclosures).toEqual(['integrations-ebird-advanced']);
        expect(settingsFieldPlace('frigate_url')?.disclosures ?? []).toEqual([]);
        expect(settingsFieldPlace('mqtt_server')?.disclosures ?? []).toEqual([]);
        expect(settingsFieldPlace('frigate_external_url')?.disclosures).toEqual(['settings-more-cameras']);
        expect(settingsFieldPlace('recording_clip_before_seconds')?.disclosures).toEqual(['settings-more-cameras', 'connection-full-visit']);
        expect(settingsFieldPlace('audio_buffer_hours')?.disclosures).toEqual(['integrations-birdnet-advanced']);
    });

    it('shows a refused concurrency by opening Storage\'s More options, since Jobs at once is a plain card inside it', () => {
        expect(settingsFieldPlace('maintenance_max_concurrent')?.disclosures).toEqual(['settings-more-storage']);
        expect(settingsFieldPlace('media_cache_max_size_mb')?.disclosures ?? []).toEqual([]);
    });
});
