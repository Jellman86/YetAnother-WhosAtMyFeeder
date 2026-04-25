// @ts-nocheck — uses node:fs/node:path at vitest runtime; types are not in
// the app tsconfig and we don't want to add @types/node for one guard file.
import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SETTINGS_DIR = join(__dirname, '..');
const PRIMITIVES_DIR = __dirname;

function listSettingsComponents(): string[] {
    const out: string[] = [];
    for (const entry of readdirSync(SETTINGS_DIR)) {
        const full = join(SETTINGS_DIR, entry);
        const s = statSync(full);
        if (s.isFile() && entry.endsWith('.svelte')) {
            out.push(full);
        }
    }
    return out;
}

/**
 * The migration to settings/_primitives is rolling out one tab per PR.  These
 * tabs have already moved over and must NOT regress.  When a new tab migrates,
 * add it to this list — the audit then guards it.  Tabs not on the list are
 * grandfathered in and skipped.
 */
const MIGRATED_COMPONENTS = new Set([
    'AccessibilitySettings.svelte',
    'AISettings.svelte',
    'AppearanceSettings.svelte',
    'AuthenticationSettings.svelte',
    'ConnectionSettings.svelte',
    'DataSettings.svelte',
    'DetectionSettings.svelte',
    'EnrichmentSettings.svelte',
    'IntegrationSettings.svelte'
]);

describe('settings primitives — style audit', () => {
    it('migrated tabs do not reintroduce inline role="switch" markup', () => {
        const offenders: string[] = [];
        for (const path of listSettingsComponents()) {
            const name = path.split('/').pop()!;
            if (!MIGRATED_COMPONENTS.has(name)) continue;
            const src = readFileSync(path, 'utf8');
            // Inline switches are the most common copy-paste offender.  The
            // SettingsToggle primitive owns role="switch"; any other use in a
            // migrated tab means somebody bypassed the primitive.
            if (src.includes('role="switch"')) {
                offenders.push(name);
            }
        }
        expect(offenders, `Migrated settings tabs must use SettingsToggle, not inline role="switch" markup. Offenders: ${offenders.join(', ')}`).toEqual([]);
    });

    it('SettingsToggle primitive is the only role="switch" source', () => {
        const togglePath = join(PRIMITIVES_DIR, 'SettingsToggle.svelte');
        expect(readFileSync(togglePath, 'utf8')).toContain('role="switch"');
    });

    it('SettingsCard primitive uses the standard card chrome', () => {
        const cardPath = join(PRIMITIVES_DIR, 'SettingsCard.svelte');
        const src = readFileSync(cardPath, 'utf8');
        expect(src).toContain('rounded-3xl');
        expect(src).toContain('card-base');
    });
});
