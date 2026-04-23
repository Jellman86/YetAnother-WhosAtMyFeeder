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
    'settings.data.cache_high_quality_event_snapshot_jpeg_quality',
    'settings.data.cache_high_quality_event_snapshot_jpeg_quality_help',
    'settings.data.media_integrity_title',
    'settings.data.frigate_missing_behavior',
    'settings.data.frigate_missing_behavior_mark',
    'settings.data.frigate_missing_behavior_keep',
    'settings.data.frigate_missing_behavior_delete',
    'settings.data.frigate_missing_behavior_note',
    'settings.data.purge_missing_media',
    'settings.data.auto_purge_missing_media',
    'settings.data.purge_missing_media_confirm',
    'settings.data.purge_missing_scan_success',
    'settings.data.media_integrity_note',
    'settings.data.timezone_repair_title',
    'settings.data.timezone_repair_preview_button',
    'settings.data.timezone_repair_apply_button',
    'settings.integrations.ebird.export_from',
    'settings.integrations.ebird.export_from_label',
    'settings.integrations.ebird.export_to',
    'settings.integrations.ebird.export_to_label',
    'settings.integrations.ebird.export_everything',
    'settings.integrations.ebird.export_everything_label',
    'settings.integrations.ebird.export_everything_help',
    'settings.integrations.ebird.export_range_help',
    'settings.integrations.ebird.export_range_error',
    'settings.location.weather_unit_system',
    'settings.location.state',
    'settings.location.country',
    'settings.location.metric',
    'settings.location.imperial',
    'settings.location.british',
    'settings.location.weather_unit_system_desc',
    'detection.upstream_missing.title',
    'detection.upstream_missing.card_label',
    'detection.upstream_missing.card_title',
    'detection.upstream_missing.description',
    'detection.upstream_missing.since',
    'detection.upstream_missing.last_checked',
    'detection.upstream_missing.error',
    'common.unit_mph',
    'common.unit_in'
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

describe('locale coverage for settings data cache quality strings', () => {
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
