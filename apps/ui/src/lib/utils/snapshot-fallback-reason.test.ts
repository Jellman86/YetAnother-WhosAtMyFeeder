import { describe, expect, it } from 'vitest';
import { authoredLocale } from '../i18n/authored-locales';
import { formatSnapshotFallbackReason, SNAPSHOT_FALLBACK_REASON_KEYS } from './snapshot-fallback-reason';

const LOCALE_NAMES = ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh'] as const;

describe('formatSnapshotFallbackReason', () => {
    it('defines every known fallback reason and both HTTP templates in all 9 locales', () => {
        for (const name of LOCALE_NAMES) {
            const locale = authoredLocale(name) as {
                detection: { reclassification: { snapshot_fallback_reason: Record<string, string> } };
            };
            const map = locale.detection.reclassification.snapshot_fallback_reason;
            for (const key of [...SNAPSHOT_FALLBACK_REASON_KEYS, 'event_http', 'clip_http']) {
                expect(typeof map[key], `${name}: ${key}`).toBe('string');
                expect(map[key].trim().length, `${name}: ${key}`).toBeGreaterThan(0);
            }
            expect(map.event_http, `${name}: event_http`).toContain('{status}');
            expect(map.clip_http, `${name}: clip_http`).toContain('{status}');
        }
    });

    it('maps dynamic event_http_<status> and clip_http_<status> codes to localized templates', () => {
        const calls: Array<{ key: string; status?: string | number }> = [];
        const t = (key: string, options?: { default?: string; values?: Record<string, string | number> }) => {
            calls.push({ key, status: options?.values?.status });
            return `${key}:${options?.values?.status ?? ''}`;
        };

        expect(formatSnapshotFallbackReason('event_http_502', t)).toBe(
            'detection.reclassification.snapshot_fallback_reason.event_http:502'
        );
        expect(formatSnapshotFallbackReason('clip_http_404', t)).toBe(
            'detection.reclassification.snapshot_fallback_reason.clip_http:404'
        );
    });

    it('falls back to a localized generic message rather than leaking unknown snake_case codes', () => {
        const t = (key: string, options?: { default?: string }) =>
            key === 'detection.reclassification.snapshot_fallback_reason_generic'
                ? 'Localized generic fallback'
                : options?.default ?? key;

        expect(formatSnapshotFallbackReason('brand_new_backend_code', t)).toBe('Localized generic fallback');
        expect(formatSnapshotFallbackReason('', t)).toBe('Localized generic fallback');
        expect(formatSnapshotFallbackReason(null, t, 'Custom fallback')).toBe('Custom fallback');
    });
});
