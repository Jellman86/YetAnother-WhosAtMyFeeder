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

import notableNearbySource from '../components/NotableNearby.svelte?raw';
import detectionModalSource from '../components/DetectionModal.svelte?raw';
import speciesDetailSource from '../components/SpeciesDetailModal.svelte?raw';
import integrationSettingsSource from '../components/settings/IntegrationSettings.svelte?raw';

// The structural audit proves every locale carries the same placeholders. This
// test closes the other half of the contract: that the components actually pass
// those names. A rename on one side alone renders a literal "{distance}".

type LocaleRoot = Record<string, unknown>;

const LOCALES: Array<[string, LocaleRoot]> = [
    ['de', de as LocaleRoot],
    ['en', en as LocaleRoot],
    ['es', es as LocaleRoot],
    ['fr', fr as LocaleRoot],
    ['it', itLocale as LocaleRoot],
    ['ja', ja as LocaleRoot],
    ['pt', pt as LocaleRoot],
    ['ru', ru as LocaleRoot],
    ['zh', zh as LocaleRoot]
];

function pick(obj: LocaleRoot, path: string): unknown {
    return path.split('.').reduce<unknown>((current, segment) => {
        if (!current || typeof current !== 'object') return undefined;
        return (current as Record<string, unknown>)[segment];
    }, obj);
}

function placeholders(value: unknown): string[] {
    if (typeof value !== 'string') return [];
    return [...value.matchAll(/\{([a-zA-Z0-9_]+)\}/g)].map(match => match[1]).sort();
}

// Located by scanning rather than by building a regex out of the key, so no
// caller-supplied text is ever compiled as a pattern.
const VALUES_SEARCH_WINDOW = 200;

function valuesPassedFor(source: string, key: string): string[] {
    const keyAt = source.indexOf(`'${key}'`);
    if (keyAt === -1) return [];
    const valuesAt = source.indexOf('values:', keyAt);
    if (valuesAt === -1 || valuesAt - keyAt > VALUES_SEARCH_WINDOW) return [];
    const open = source.indexOf('{', valuesAt);
    const close = source.indexOf('}', open);
    if (open === -1 || close === -1) return [];
    return [...source.slice(open + 1, close).matchAll(/([a-zA-Z0-9_]+)\s*:/g)].map(m => m[1]).sort();
}

const CONTRACTS: Array<[string, string, string[], string]> = [
    ['dashboard.notable_nearby.scope', 'NotableNearby', ['days', 'distance'], notableNearbySource],
    ['dashboard.notable_nearby.empty', 'NotableNearby', ['days', 'distance'], notableNearbySource],
    ['settings.integrations.ebird.radius', 'IntegrationSettings', ['unit'], integrationSettingsSource],
    ['settings.integrations.ebird.radius_help', 'IntegrationSettings', ['max', 'min', 'unit'], integrationSettingsSource]
];

describe('eBird distance strings', () => {
    it.each(CONTRACTS)('%s carries the same placeholders in every locale', (key, _component, expected) => {
        for (const [code, locale] of LOCALES) {
            expect(placeholders(pick(locale, key)), `${code} ${key}`).toEqual(expected);
        }
    });

    it.each(CONTRACTS)('%s is called with those values in %s', (key, _component, expected, source) => {
        expect(valuesPassedFor(source, key)).toEqual(expected);
    });

    it('renders the radius through the unit-aware formatter rather than a hard-coded km suffix', () => {
        for (const source of [notableNearbySource, detectionModalSource, speciesDetailSource]) {
            expect(source).not.toMatch(/\{ebirdRadius\}km/);
            expect(source).not.toMatch(/\{radius\}km/);
        }
        expect(notableNearbySource).toContain('formatDistance');
        expect(detectionModalSource).toContain('formatDistance');
        expect(speciesDetailSource).toContain('formatDistance');
    });

    it('keeps the stored radius in kilometres so a unit switch cannot rewrite it', () => {
        expect(integrationSettingsSource).toContain('ebirdRadiusFromDisplayValue');
        expect(integrationSettingsSource).toContain('ebirdRadiusToDisplayValue');
        expect(integrationSettingsSource).not.toMatch(/ebirdDefaultRadiusKm = Number\(v\)/);
    });
});
