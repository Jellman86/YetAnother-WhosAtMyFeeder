import { describe, expect, it } from 'vitest';
import { authoredLocale } from './authored-locales';

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

        // docs/standards/layout-patterns.md §5: no em dashes, in any language. A lone dash
        // standing in for an empty value is not punctuation.
        it(`${name} uses no em dash as punctuation`, () => {
            expect(leaves.filter(([, value]) => value.includes('—') && value.trim() !== '—')).toEqual([]);
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

/**
 * docs/standards/layout-patterns.md, writing rules: controls, headings and labels are in sentence
 * case. A short label whose later words are capitalised ("Clear History", "Test AI Connection")
 * fails unless the word is a name: a product, a place, a model, or a page or tab of the app.
 * German capitalises its nouns and Japanese and Chinese have no case, so they are not checked.
 */
const NAMES = new Set(
    `YA-WAMF Yet Another WhosAtMyFeeder Frigate MQTT BirdNET BirdNET-Go eBird iNaturalist BirdWeather Home Assistant
    GitHub YouTube Freepik Flaticon Jellman86 Wikipedia Wikimedia Gmail Outlook Google Microsoft OAuth Discord Telegram
    Pushover Apprise Gemini OpenAI OpenRouter Anthropic Claude OpenDyslexic MegaDetector Cedar SpeciesNet RF-DETR Nano YOLOX YOLOX-Tiny
    MobileNet EfficientNet ConvNeXt ONNX Runtime TFLite OpenVINO CUDA Intel NVIDIA Hailo Coral Docker Leaflet OpenStreetMap
    Open-Meteo HACS MIT License Record Format Token Northern Cardinal United States Kingdom North America Europe
    Unknown Bird Tit NaN Celsius Fahrenheit
    Dashboard Explorer Leaderboard Settings Notifications Events Species Garden Health Connection Detection Integrations
    Enrichment Security Data Appearance Accessibility Advanced Beta Debug Explore Jobs About`
        .split(/\s+/)
        .filter(Boolean)
);
const SENTENCE_CASE_LOCALES = ['en', 'es', 'fr', 'it', 'pt', 'ru'];
/**
 * Never lowered to sentence case: German capitalises every noun ("YA-WAMF Bot", not "YA-WAMF bot"),
 * and Japanese and Chinese have no letter case. A copy pass must leave their capitals alone.
 */
const CASE_EXEMPT_LOCALES = ['de', 'ja', 'zh'];
/** Names a language spells its own way: places, units and the Garden feature. */
const LOCALE_NAMES: Record<string, string[]> = {
    es: ['Unidos', 'Unido', 'Norte', 'Jardín'],
    fr: ['Jardin', 'Wikipédia', 'Mo', 'Go', 'Nord', 'Uni', 'Unis'],
    it: ['Uniti', 'Unito', 'Nord', 'Giardino'],
    pt: ['Unidos', 'Unido', 'Norte', 'Jardim'],
    ru: ['Сад', 'Северная', 'Америка', 'Википедии']
};

/** A page or tab is a name in every language, so its own label may be capitalised where it is cited. */
function interfaceNames(locale: LocaleRoot): Set<string> {
    const settings = (locale.settings ?? {}) as LocaleRoot;
    const labels = [...stringLeaves((locale.nav ?? {}) as LocaleRoot), ...stringLeaves((settings.tabs ?? {}) as LocaleRoot)].map(([, value]) => value);
    return new Set(labels.flatMap((label) => label.match(/[\p{L}][\p{L}\p{N}'’.-]*/gu) ?? []));
}

function titleCasedWords(value: string, names: Set<string>): string[] {
    const plain = value.replace(/\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/g, ' ');
    const words = plain.match(/[\p{L}][\p{L}\p{N}'’.-]*/gu) ?? [];
    if (words.length < 2 || words.length > 6) return [];
    const offenders: string[] = [];
    let index = 0;
    for (const match of plain.matchAll(/[\p{L}][\p{L}\p{N}'’.-]*/gu)) {
        const word = match[0];
        const before = plain.slice(0, match.index).trimEnd();
        const startsClause = index === 0 || /[.:!?·•|/(“"«›→-]$/.test(before);
        index += 1;
        if (startsClause || !/^\p{Lu}\p{Ll}/u.test(word)) continue;
        const bare = word.replace(/[’'](?:s)?$/u, '').replace(/[.]$/, '');
        if (!NAMES.has(bare) && !names.has(bare)) offenders.push(word);
    }
    return offenders;
}

describe('sentence case', () => {
    it('checks every language or names why it is exempt', () => {
        const covered = [...SENTENCE_CASE_LOCALES, ...CASE_EXEMPT_LOCALES].sort();
        expect(covered).toEqual(LOCALES.map(([name]) => name).sort());
    });

    it('keeps German nouns capitalised where a copy pass touched them', () => {
        const german = new Map(stringLeaves(de as LocaleRoot));
        expect(german.get('settings.discord.bot_placeholder')).toBe('YA-WAMF Bot');
    });

    for (const name of SENTENCE_CASE_LOCALES) {
        const locale = LOCALES.find(([localeName]) => localeName === name)?.[1] ?? {};
        const names = new Set([...interfaceNames(locale), ...(LOCALE_NAMES[name] ?? [])]);
        it(`${name} labels capitalise only their first word and names`, () => {
            expect(
                stringLeaves(locale)
                    .filter(([path]) => !path.startsWith('project_notes.'))
                    .map(([path, value]) => [path, value, titleCasedWords(value, names)] as const)
                    .filter(([, , words]) => words.length > 0)
                    .map(([path, value]) => `${path}: ${value}`)
            ).toEqual([]);
        });
    }
});
