import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';

const de = authoredLocale('de');
const en = authoredLocale('en');
const es = authoredLocale('es');
const fr = authoredLocale('fr');
const itLocale = authoredLocale('it');
const ja = authoredLocale('ja');
const pt = authoredLocale('pt');
const ru = authoredLocale('ru');
const zh = authoredLocale('zh');

type LocaleRoot = Record<string, unknown>;

function pick(obj: LocaleRoot, path: string): unknown {
    return path.split('.').reduce<unknown>((current, segment) => {
        if (!current || typeof current !== 'object') return undefined;
        return (current as Record<string, unknown>)[segment];
    }, obj);
}

const REQUIRED_KEYS = [
    'jobs.pipeline_title',
    'jobs.queue_reported',
    'jobs.queue_depth_unknown',
    'jobs.queue_slots_free',
    'jobs.activity_reclassify_running',
    'jobs.activity_waiting_slots',
    'jobs.activity_circuit_open',
    'jobs.activity_processing',
    'jobs.activity_queued',
    'jobs.progress_units',
    'jobs.capacity_worker_slots',
    'jobs.blocker_circuit_open',
    'jobs.blocker_mqtt_pressure',
    'jobs.global_running_single',
    'jobs.global_running_multi',
    'jobs.global_summary_circuit_open',
    'jobs.kind_reclassify',
    'jobs.kind_backfill',
    'jobs.kind_weather_backfill',
    'jobs.kind_taxonomy_sync',
    'jobs.errors_clear',
    'jobs.errors_backend_empty',
    'jobs.error_bundles_label_placeholder',
    'jobs.error_bundles_capture',
    'jobs.error_bundles_clear',
    'jobs.error_bundles_stats',
    'jobs.error_bundles_download',
    'jobs.error_bundles_delete',
    'jobs.earlier_incidents_title',
    'jobs.earlier_incidents_empty',
    'jobs.earlier_incidents_desc',
];

const LOCALES: Array<[string, LocaleRoot]> = [
    ['en', en as LocaleRoot],
    ['de', de as LocaleRoot],
    ['es', es as LocaleRoot],
    ['fr', fr as LocaleRoot],
    ['it', itLocale as LocaleRoot],
    ['ja', ja as LocaleRoot],
    ['pt', pt as LocaleRoot],
    ['ru', ru as LocaleRoot],
    ['zh', zh as LocaleRoot]
];

describe('locale coverage for notifications/jobs/errors', () => {
    for (const [localeName, locale] of LOCALES) {
        it(`${localeName} has required keys`, () => {
            for (const key of REQUIRED_KEYS) {
                const value = pick(locale, key);
                expect(typeof value).toBe('string');
                expect(String(value).length).toBeGreaterThan(0);
            }
        });
    }
});
