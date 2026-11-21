import { describe, expect, it } from 'vitest';
import { showsCause, statusCauseKey, statusCauses, statusStateKey } from './status-words';

describe('the words of a status chip', () => {
    it('says a missing model and a finder to download in their own words, as the Models line does', () => {
        expect(statusStateKey('classifier', { state: 'error', cause: 'model_missing' })).toBe('settings.status.cause.classifier.model_missing');
        expect(statusStateKey('finder', { state: 'degraded', cause: 'not_downloaded' })).toBe('settings.status.cause.finder.not_downloaded');
    });

    it('says the state for every other cause, and "not measured" for no reading', () => {
        expect(statusStateKey('classifier', { state: 'error', cause: 'runtime_failed' })).toBe('settings.status.state.error');
        expect(statusStateKey('finder', { state: 'degraded', cause: 'cpu_fallback' })).toBe('settings.status.state.degraded');
        expect(statusStateKey('mqtt', null)).toBe('settings.status.state.unknown');
    });
});

describe('a status cause in words', () => {
    // Node types are absent from the app tsconfig; this check reads the shared fixture from disk.
    // @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
    const load = () => import('node:fs').then(({ readFileSync }) => JSON.parse(
        readFileSync(new URL('../../../../../backend/tests/fixtures/status_causes.json', import.meta.url), 'utf8')
    ) as { causes: Record<string, string[]> });

    it('knows exactly the causes the backend can send', async () => {
        const { causes } = await load();
        expect(statusCauses()).toEqual(causes);
    });

    it('has words for every cause and every part, in every language', async () => {
        const { causes } = await load();
        for (const locale of ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh']) {
            // @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
            const { readFileSync } = await import('node:fs');
            const status = JSON.parse(readFileSync(new URL(`../i18n/locales/${locale}/settings.json`, import.meta.url), 'utf8')).status;
            for (const [key, list] of Object.entries(causes)) {
                expect(status.purpose[key], `${locale} purpose.${key}`).toBeTruthy();
                for (const cause of list) expect(status.why[key]?.[cause], `${locale} why.${key}.${cause}`).toBeTruthy();
            }
        }
    });

    it('never words a cause it does not know, so no raw code reaches the page', () => {
        expect(statusCauseKey('frigate', 'cameras_offline')).toBe('settings.status.why.frigate.cameras_offline');
        expect(statusCauseKey('frigate', 'something_new')).toBeNull();
        expect(statusCauseKey('mqtt', undefined)).toBeNull();
    });
});

describe('when the column words a cause', () => {
    it('never from a stale reading, and above the settings only for a part that needs a look', () => {
        expect(showsCause({ state: 'ok' }, { detailed: true, stale: false })).toBe(true);
        expect(showsCause({ state: 'error' }, { detailed: true, stale: true })).toBe(false);
        expect(showsCause({ state: 'error' }, { detailed: false, stale: true })).toBe(false);
        expect(showsCause({ state: 'ok' }, { detailed: false, stale: false })).toBe(false);
        expect(showsCause({ state: 'degraded' }, { detailed: false, stale: false })).toBe(true);
    });
});
