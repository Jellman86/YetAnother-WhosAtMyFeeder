import { describe, expect, it } from 'vitest';
import de from './locales/de.json';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import itLocale from './locales/it.json';
import ja from './locales/ja.json';
import pt from './locales/pt.json';
import ru from './locales/ru.json';
import zh from './locales/zh.json';

type LocaleRoot = Record<string, unknown>;

function pick(obj: LocaleRoot, path: string): unknown {
    return path.split('.').reduce<unknown>((current, segment) => {
        if (!current || typeof current !== 'object') return undefined;
        return (current as Record<string, unknown>)[segment];
    }, obj);
}

const NON_ENGLISH_LOCALES: Array<[string, LocaleRoot]> = [
    ['de', de as LocaleRoot],
    ['es', es as LocaleRoot],
    ['fr', fr as LocaleRoot],
    ['it', itLocale as LocaleRoot],
    ['ja', ja as LocaleRoot],
    ['pt', pt as LocaleRoot],
    ['ru', ru as LocaleRoot],
    ['zh', zh as LocaleRoot]
];

const MUST_BE_LOCALIZED = [
    'settings.cameras.preview_close',
    'settings.telemetry.title',
    'settings.telemetry.desc',
    'settings.telemetry.transparency',
    'settings.telemetry.install_id',
    'settings.telemetry.version',
    'settings.telemetry.platform',
    'settings.telemetry.privacy_notice',
    'settings.telemetry.includes',
    'settings.telemetry.includes_value',
    'settings.telemetry.geography',
    'settings.telemetry.geography_value',
    'settings.telemetry.frequency',
    'settings.telemetry.frequency_value',
    'settings.telemetry.appreciation_tooltip',
    'settings.integrations.ebird.export_range_help',
    'settings.integrations.ebird.export_range_error',
    'settings.integrations.ebird.export_everything',
    'settings.integrations.ebird.export_everything_help',
    'settings.notifications.enable_notify_hint',
    'settings.notifications.min_confidence_label',
    'settings.notifications.add_species_label',
    'settings.notifications.remove_species_label',
    'settings.security.title',
    'settings.enrichment.title',
    'settings.enrichment.mode_single',
    'settings.enrichment.mode_per',
    'settings.enrichment.provider',
    'settings.enrichment.summary_title',
    'settings.enrichment.taxonomy_title',
    'settings.enrichment.sightings_title',
    'settings.enrichment.seasonality_title',
    'settings.enrichment.rarity_title',
    'settings.enrichment.links_title',
    'settings.enrichment.disabled',
    'jobs.pipeline_subtitle',
    'jobs.queue_unknown_suffix',
    'jobs.queue_slots_free',
    'jobs.stale_hint',
    'jobs.outcomes',
    'jobs.completed_failed_counts',
    'jobs.activity_label',
    'jobs.progress_label',
    'jobs.capacity_label',
    'jobs.blocker_label',
    'jobs.freshness_label',
    'jobs.queue_known',
    'jobs.queue_reported',
    'jobs.queue_not_reported',
    'jobs.queue_depth_unknown',
    'jobs.running',
    'jobs.completed',
    'jobs.failed',
    'jobs.system_throughput',
    'jobs.system_throughput_subtitle',
    'jobs.activity_reclassify_running',
    'jobs.activity_waiting_slots',
    'jobs.activity_circuit_open',
    'jobs.activity_processing',
    'jobs.activity_queued',
    'jobs.progress_expanding',
    'jobs.progress_units',
    'jobs.capacity_worker_slots',
    'jobs.blocker_circuit_open',
    'jobs.freshness_stale',
    'jobs.freshness_updated',
    'jobs.global_summary_with_queue',
    'jobs.global_summary_circuit_open',
    'jobs.global_summary_basic',
    'jobs.global_summary_mixed_units',
    'jobs.kind_reclassify',
    'jobs.kind_backfill',
    'jobs.kind_weather_backfill',
    'jobs.kind_taxonomy_sync'
];

describe('locale audit for active non-English UX', () => {
    for (const [localeName, locale] of NON_ENGLISH_LOCALES) {
        it(`${localeName} does not contain dead top-level ai strings`, () => {
            expect(pick(locale, 'ai')).toBeUndefined();
        });

        it(`${localeName} localizes selected active settings/jobs strings`, () => {
            for (const key of MUST_BE_LOCALIZED) {
                const englishValue = pick(en as LocaleRoot, key);
                const localizedValue = pick(locale, key);
                expect(typeof localizedValue).toBe('string');
                expect(localizedValue).not.toBe(englishValue);
            }
        });
    }
});
