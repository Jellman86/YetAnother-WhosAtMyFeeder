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

const REQUIRED_KEYS = [
    'notifications.page_title',
    'notifications.page_subtitle',
    'jobs.pipeline_title',
    'jobs.pipeline_subtitle',
    'jobs.queued',
    'jobs.queue_known',
    'jobs.queue_reported',
    'jobs.queue_not_reported',
    'jobs.queue_unknown_suffix',
    'jobs.running',
    'jobs.stale_hint',
    'jobs.outcomes',
    'jobs.completed',
    'jobs.failed',
    'jobs.completed_failed_counts',
    'jobs.kind_reclassify',
    'jobs.kind_backfill',
    'jobs.kind_weather_backfill',
    'jobs.kind_taxonomy_sync',
    'jobs.errors_title',
    'jobs.errors_subtitle',
    'jobs.errors_export',
    'jobs.errors_clear',
    'jobs.errors_summary',
    'jobs.errors_latest_health',
    'jobs.errors_empty',
    'jobs.errors_count',
    'jobs.errors_first_seen',
    'jobs.errors_last_seen',
    'jobs.errors_samples',
    'jobs.errors_snapshot_ref',
    'jobs.error_bundles_title',
    'jobs.error_bundles_subtitle',
    'jobs.error_bundles_label_placeholder',
    'jobs.error_bundles_capture',
    'jobs.error_bundles_clear',
    'jobs.error_bundles_empty',
    'jobs.error_bundles_stats',
    'jobs.error_bundles_download',
    'jobs.error_bundles_delete',
    'jobs.current_issues_title',
    'jobs.current_issues_empty',
    'jobs.recent_incidents_title',
    'jobs.recent_incidents_empty',
    'jobs.incident_detail_title',
    'jobs.report_issue_title',
    'jobs.report_issue_empty',
    'jobs.report_issue_copy_summary',
    'jobs.report_issue_open_github'
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
