import { describe, expect, it } from 'vitest';
import { settingsFieldSection } from '../../settings/settings-fields';
import enSettings from '../../i18n/locales/en/settings.json';
import identificationSource from './sections/IdentificationSection.svelte?raw';
import loadersSource from './sections/part-loaders.ts?raw';
import settingsPageSource from '../../pages/Settings.svelte?raw';

// The file is created by this change; a glob keeps the test failing, not erroring, until it exists.
const visitGapSources = import.meta.glob('./VisitGapSettings.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const visitGapSource = visitGapSources['./VisitGapSettings.svelte'] ?? '';
const copy = (enSettings as Record<string, unknown>).visit_gap as Record<string, string> | undefined;

describe('the visit gap setting (#1044)', () => {
    it('is a number field in seconds that a refused save marks, bounded as the API bounds it', () => {
        expect(visitGapSource).toContain('<SettingsInput');
        expect(visitGapSource).toContain('field="visit_gap_seconds"');
        expect(visitGapSource).toContain('type="number"');
        expect(visitGapSource).toMatch(/min=\{5\}/);
        expect(visitGapSource).toMatch(/max=\{300\}/);
        expect(visitGapSource).toContain('describedBy=');
    });

    it('sits with the naming threshold, where the owner sets how captures are recorded', () => {
        expect(loadersSource).toContain("import('../VisitGapSettings.svelte')");
        expect(loadersSource).toMatch(/detection: \(\) => Promise\.all\(\[loadNamingSettings\(\), loadVisitGapSettings\(\), loadDetectionSettings\(\)\]\)/);
        const detectionPart = identificationSource.split('data-settings-part="detection"')[1].split('data-settings-part="models"')[0];
        expect(detectionPart.indexOf('NamingSettings')).toBeLessThan(detectionPart.indexOf('VisitGapSettings'));
        expect(settingsFieldSection('visit_gap_seconds')).toBe('identification');
    });

    it('is a saved setting: read, compared for unsaved changes, and sent', () => {
        expect(settingsPageSource).toContain("field: 'visit_gap_seconds', draft: visitGapSeconds");
        expect(settingsPageSource).toContain('visitGapSeconds = settings.visit_gap_seconds ?? 60');
        expect(settingsPageSource).toContain('visit_gap_seconds: visitGapSeconds');
        expect(settingsPageSource).toContain('bind:visitGapSeconds');
    });

    it('says what the gap does, what it cannot do, and what happens to history', () => {
        expect(copy?.desc).toMatch(/same species on the same camera/);
        expect(copy?.limit).toMatch(/cannot count individual birds/);
        expect(copy?.history).toMatch(/keep the visit counts/);
        for (const text of Object.values(copy ?? {})) expect(text).not.toContain('—');
    });
});
