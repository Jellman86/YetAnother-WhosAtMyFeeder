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
type LocaleLeaf = [path: string, value: string];

function stringLeaves(value: LocaleRoot, prefix = ''): LocaleLeaf[] {
    return Object.entries(value).flatMap(([key, child]) => {
        const path = prefix ? `${prefix}.${key}` : key;
        if (typeof child === 'string') return [[path, child] as LocaleLeaf];
        if (child && typeof child === 'object' && !Array.isArray(child)) {
            return stringLeaves(child as LocaleRoot, path);
        }
        return [];
    });
}

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

const MOJIBAKE = /[\u0080-\u009f\ufffd]|Ã.|Â.|â[\u0080-\u00bf]/u;
const TECHNICAL_ELLIPSIS_KEYS = new Set([
    'settings.discord.webhook_placeholder',
    'settings.telegram.bot_token_placeholder'
]);

const ASCII_ACCENT_LOSS_MARKERS: Record<string, string[]> = {
    de: ['Gaesten', 'vollstaendige', 'verfuegbar', 'moeglicherweise', 'geloescht', 'fuer'],
    es: [
        'Obtencion',
        'Configuracion',
        'grabacion',
        'puntuacion',
        'analisis',
        'automatico',
        'automaticamente',
        'minima',
        'Anulacion',
        'esperara',
        'linea',
        'cache',
        'fisico',
        'busqueda'
    ],
    fr: [
        'telechargement',
        'telecharger',
        'invites a telecharger',
        'detection',
        'detections',
        "creation d'une detection",
        'envoyees uniquement',
        'mises a jour',
        'analyse video',
        'chaine video',
        "delai d'attente",
        'supplementaire',
        'Recuperation des clips',
        'desactivee',
        'parametres',
        'peut-etre ete',
        'Apercus',
        'differees',
        'memoire tampon',
        'fleches'
    ],
    it: ['puo', 'attendera'],
    pt: ['Configuracoes', 'gravacao', 'nao', 'indisponivel', 'Previas', 'reproducao', 'fisico', 'estao']
};

function containsWholeAsciiMarker(value: string, markers: string[]): boolean {
    return markers.some((marker) => {
        const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return new RegExp(`\\b${escaped}\\b`, 'i').test(value);
    });
}

const SCRIPT_EXPECTATIONS: Record<string, RegExp> = {
    ja: /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u,
    ru: /\p{Script=Cyrillic}/u,
    zh: /\p{Script=Han}/u
};
const SCRIPT_EXEMPT_KEYS = new Set(['settings.discord.bot_placeholder']);

describe('locale editorial quality', () => {
    for (const [name, locale] of LOCALES) {
        const leaves = stringLeaves(locale);

        it(`${name} has no surrounding whitespace or encoding damage`, () => {
            expect(
                leaves.filter(([, value]) => value !== value.trim() || MOJIBAKE.test(value))
            ).toEqual([]);
        });

        it(`${name} uses a typographic ellipsis outside literal technical examples`, () => {
            expect(
                leaves.filter(
                    ([path, value]) => value.includes('...') && !TECHNICAL_ELLIPSIS_KEYS.has(path)
                )
            ).toEqual([]);
        });
    }

    for (const [name, markers] of Object.entries(ASCII_ACCENT_LOSS_MARKERS)) {
        const locale = LOCALES.find(([localeName]) => localeName === name)?.[1];
        it(`${name} has no known ASCII-only accent substitutions`, () => {
            expect(
                stringLeaves(locale ?? {}).filter(([, value]) =>
                    containsWholeAsciiMarker(value, markers)
                )
            ).toEqual([]);
        });
    }

    it('French uses non-breaking spacing before double punctuation', () => {
        expect(stringLeaves(fr as LocaleRoot).filter(([, value]) => / [:;!?]/.test(value))).toEqual([]);
    });

    for (const [name, expectedScript] of Object.entries(SCRIPT_EXPECTATIONS)) {
        const locale = LOCALES.find(([localeName]) => localeName === name)?.[1];
        it(`${name} does not contain sentence-length Latin-only UI copy`, () => {
            expect(
                stringLeaves(locale ?? {}).filter(([path, value]) => {
                    const latinWords = value.match(/[A-Za-z]{2,}/g) ?? [];
                    return (
                        latinWords.length >= 4 &&
                        !expectedScript.test(value) &&
                        !path.endsWith('_placeholder') &&
                        !/https?:\/\//.test(value) &&
                        !SCRIPT_EXEMPT_KEYS.has(path)
                    );
                })
            ).toEqual([]);
        });
    }
});
