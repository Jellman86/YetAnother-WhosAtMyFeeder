import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';
import settingsPageSource from '../pages/Settings.svelte?raw';

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
    'settings.data.cache_high_quality_event_snapshot_jpeg_quality',
    'settings.data.cache_high_quality_event_snapshot_jpeg_quality_help',
    'settings.data.open_diagnostics',
    'settings.data.frigate_missing_behavior',
    'settings.data.frigate_missing_behavior_mark',
    'settings.data.frigate_missing_behavior_keep',
    'settings.data.frigate_missing_behavior_delete',
    'settings.data.frigate_missing_behavior_note',
    'settings.data.purge_missing_media',
    'settings.data.auto_purge_missing_media',
    'settings.data.purge_missing_media_confirm_delete',
    'settings.data.purge_missing_media_confirm_mark',
    'settings.data.purge_missing_media_confirm_keep',
    'settings.data.purge_missing_media_confirm_unsaved',
    'settings.data.purge_missing_media_delete_button',
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
    'settings.location.country',
    'settings.location.metric',
    'settings.location.imperial',
    'settings.location.british',
    'settings.location.weather_unit_system_desc',
    'detection.upstream_missing.title',
    'detection.upstream_missing.card_label',
    'detection.upstream_missing.card_title',
    'detection.upstream_missing.compact_label',
    'detection.upstream_missing.learn_more',
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
        it(`${localeName} scan result distinguishes failed checks from missing media`, () => {
            expect(pick(locale, 'settings.data.purge_missing_scan_success')).toContain('{errors}');
        });
    }
});

// The delete scan keeps every visit whose photo YA-WAMF still holds; its confirmation must say so.
const DELETE_CONFIRM_PHOTO_EXCEPTION: Record<string, string> = {
    en: 'unless YA-WAMF still holds their photo',
    de: 'sofern YA-WAMF kein Foto',
    es: 'salvo que YA-WAMF aún conserve su foto',
    fr: 'sauf si YA-WAMF conserve encore leur photo',
    it: 'a meno che YA-WAMF non ne conservi ancora la foto',
    ja: 'YA-WAMF が写真を保持していない場合に限り',
    pt: 'a menos que o YA-WAMF ainda guarde a foto',
    ru: 'если у YA-WAMF не осталось их фото',
    zh: '只有在 YA-WAMF 也没有保存其照片时'
};

describe('the delete scan confirmation says which visits are kept', () => {
    for (const [localeName, locale] of LOCALES) {
        it(`${localeName} names the photo exception`, () => {
            expect(pick(locale, 'settings.data.purge_missing_media_confirm_delete')).toContain(
                DELETE_CONFIRM_PHOTO_EXCEPTION[localeName]
            );
        });
    }
    it('the Settings fallback matches the English text', () => {
        expect(settingsPageSource).toContain(String(pick(en as LocaleRoot, 'settings.data.purge_missing_media_confirm_delete')));
    });
});
