import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';

// The backend's reasons, from `filter_and_label` in backend/app/services/detection_service.py:
// `low_confidence` is a score under the minimum confidence floor, so the frame is not kept at all;
// `below_threshold` is a score under the naming threshold with no Unknown bird fallback.
// The Health copy once named them the other way round.
//
// Each locale's own words, as Settings names the floor and the glossary names the threshold.
// Russian inflects, so its terms are the stems that survive the case ending.
const TERMS = {
    en: { floor: 'minimum confidence floor', threshold: 'naming threshold' },
    de: { floor: 'Konfidenzuntergrenze', threshold: 'Benennungsschwelle' },
    es: { floor: 'suelo de confianza mínimo', threshold: 'umbral de identificación' },
    fr: { floor: 'seuil minimal de confiance', threshold: 'seuil d’identification' },
    it: { floor: 'livello minimo di confidenza', threshold: 'soglia di identificazione' },
    ja: { floor: '最小信頼度下限', threshold: '識別のしきい値' },
    pt: { floor: 'piso mínimo de confiança', threshold: 'limiar de identificação' },
    ru: { floor: 'уверенности', threshold: 'определения' },
    zh: { floor: '最低置信度下限', threshold: '命名阈值' }
} as const;

type Tree = Record<string, unknown>;

function text(root: Tree, path: string): string {
    const value = path.split('.').reduce<unknown>(
        (node, segment) => (node && typeof node === 'object' ? (node as Tree)[segment] : undefined),
        root
    );
    if (typeof value !== 'string') throw new Error(`missing ${path}`);
    return value.toLocaleLowerCase();
}

describe('Health drop reasons name the setting that dropped the frame', () => {
    for (const [locale, terms] of Object.entries(TERMS)) {
        const root = authoredLocale(locale) as Tree;
        const floor = terms.floor.toLocaleLowerCase();
        const threshold = terms.threshold.toLocaleLowerCase();

        it(`${locale}: filter_low_confidence is the minimum confidence floor`, () => {
            for (const key of ['jobs.errors_drop_reason', 'jobs.errors_drop_reason_row']) {
                expect(text(root, `${key}.filter_low_confidence`)).toContain(floor);
                expect(text(root, `${key}.filter_low_confidence`)).not.toContain(threshold);
            }
        });

        it(`${locale}: filter_below_threshold is the naming threshold`, () => {
            for (const key of ['jobs.errors_drop_reason', 'jobs.errors_drop_reason_row']) {
                expect(text(root, `${key}.filter_below_threshold`)).toContain(threshold);
                expect(text(root, `${key}.filter_below_threshold`)).not.toContain(floor);
            }
        });

        it(`${locale}: the filtered hint points at the floor, the setting that keeps more of them`, () => {
            expect(text(root, 'jobs.errors_filtered_hint')).toContain(floor);
        });
    }
});
