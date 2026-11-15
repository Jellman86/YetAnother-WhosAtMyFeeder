import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['./**/*.svelte', './**/*.ts', '!./**/*.test.ts', '!./i18n/locales/**'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

function source(file: string): string {
    const found = sources[`./${file}`];
    if (typeof found !== 'string') throw new Error(`No source for ${file}`);
    return found;
}

/** The cross every hand-rolled close button drew, in the three spellings the app used. */
const HAND_DRAWN_CROSS = /M6 18L18 6M6 6l12 12|m6 6 12 12M18 6 6 18|M18 6 6 18M6 6l12 12/;

const DIALOGS = [
    'components/DetectionModal.svelte',
    'components/GardenCaptureModal.svelte',
    'components/ReviewQueueModal.svelte',
    'components/DiagnosticDialog.svelte',
    'components/SpeciesDetailModal.svelte',
    'components/VideoPlayer.svelte',
    'components/KeyboardShortcuts.svelte',
    'components/CameraStatus.svelte',
    'components/setup/WizardShell.svelte'
];

describe('one close button for every dialog', () => {
    it('closes through the shared button, not a cross drawn in place', () => {
        for (const file of DIALOGS) {
            expect(source(file), file).toContain('<DialogCloseButton');
            expect(source(file), file).not.toMatch(HAND_DRAWN_CROSS);
        }
    });

    it('draws the same round 44px target whatever it sits on', () => {
        const button = source('components/DialogCloseButton.svelte');
        expect(button).toContain('h-11 w-11 shrink-0 rounded-full p-0');
        expect(button).toContain("tone === 'media'");
        expect(button).toContain("$_('common.close', { default: 'Close' })");
    });
});

describe('fallback copy in the code', () => {
    // layout-patterns.md writing rules: no em dashes in UI copy. The locales are checked by the
    // editorial test; an English fallback in the code is UI copy too whenever a key is missing.
    it('carries no em dash', () => {
        const offenders: string[] = [];
        for (const [path, text] of Object.entries(sources)) {
            for (const match of text.matchAll(/default:\s*(['"`])((?:(?!\1).)*)\1/g)) {
                if (match[2].includes('—') && match[2].trim() !== '—') offenders.push(`${path}: ${match[2].slice(0, 60)}`);
            }
        }
        expect(offenders).toEqual([]);
    });
});
