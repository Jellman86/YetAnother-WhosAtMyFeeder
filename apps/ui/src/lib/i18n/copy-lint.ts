/**
 * The copy lint. docs/standards/glossary.md says how YA-WAMF words things; this module finds the
 * strings that do not. It reads one locale string at a time and reports every rule it breaks, so
 * the test beside it can count findings per rule, language and namespace and hold each count to a
 * baseline that may only fall.
 */

export const COPY_RULES = [
    'em-dash',
    'vague-error',
    'raw-error',
    'backend-prose',
    'status-only',
    'glossary',
    'informal-address',
    'unit-spacing',
    'missing-key'
] as const;
export type CopyRule = (typeof COPY_RULES)[number];

export interface CopyFinding {
    rule: CopyRule;
    /** What was found and what the glossary asks for instead. */
    detail: string;
}

interface GlossaryTerm {
    /** The one word the glossary keeps. */
    use: string;
    /** The words it replaces, as written in docs/standards/glossary.md. */
    avoid: readonly string[];
    pattern: RegExp;
    /** Keys where the avoided word means something else, with the reason. */
    except?: { keys: RegExp; reason: string };
}

function term(use: string, avoid: readonly string[], pattern: RegExp, except?: GlossaryTerm['except']): GlossaryTerm {
    return { use, avoid, pattern, except };
}

/** A sighting is someone else's report, so the word stays where the copy is about eBird or a place. */
const OTHER_PEOPLES_REPORTS = {
    keys: /ebird|nearby|notable|reference|hotspot|location|inat/i,
    reason: 'a sighting is a report from eBird or another observer, which is what these strings describe'
};

/**
 * One entry per glossary term that has words to avoid. The glossary document lists the same words,
 * and copy-lint.test.ts fails when the two disagree.
 */
export const GLOSSARY: Record<string, readonly GlossaryTerm[]> = {
    en: [
        term('visit, capture or call', ['detection', 'detections'], /\bdetections?\b/i),
        term('visit', ['sighting', 'sightings'], /\bsightings?\b/i, OTHER_PEOPLES_REPORTS),
        term(
            'naming threshold',
            ['confidence threshold', 'species threshold', 'classification threshold', 'score threshold', 'configured threshold'],
            /\b(?:confidence|species|classification|score|configured) threshold\b/i
        ),
        term(
            'Unknown bird',
            ['Unknown species', 'Unidentified bird', 'Unidentified detection', 'Unidentified visit'],
            /\bunknown species\b|\bunidentified (?:bird|detection|visit)s?\b/i
        ),
        term('Health', ['system health', 'Errors page', 'Diagnostics page'], /\bsystem health\b|\b(?:errors|diagnostics) page\b/i),
        term('Explorer', ['Events', 'Go to Events', 'Events page'], /^Events$|\b(?:[Gg]o to|[Oo]pen|in|on) Events\b|\bEvents (?:page|tab|list)\b/),
        term('Garden animal', ['Garden wildlife', 'garden visitor', 'Garden creature'], /\bgarden (?:wildlife|visitors?|creatures?)\b/i),
        term('model', ['classifier', 'classifiers'], /\bclassifiers?\b/i),
        term(
            'bird finder',
            ['crop detector', 'bird detector', 'crop model', 'bird crop detector'],
            /\b(?:bird |crop )+detectors?\b|\bcrop models?\b/i
        ),
        term(
            'Needs your call',
            ['Needs review', 'Awaiting review', 'Pending review', 'review queue'],
            /\b(?:needs|awaiting|pending) review\b|\breview queue\b/i
        ),
        term('owner', ['admin', 'administrator'], /\badmin(?:istrator)?s?\b/i, {
            keys: /^auth\.username_placeholder$/,
            reason: 'the placeholder shows the literal default user name'
        }),
        term('AI', ['LLM'], /\bLLMs?\b/)
    ],
    de: [
        term('Besuch, Aufnahme oder Ruf', ['Erkennung', 'Erkennungen'], /(?<![\p{L}-])Erkennung(?:en)?(?![\p{L}])/u),
        term('Besuch', ['Sichtung', 'Sichtungen'], /(?<![\p{L}-])Sichtung(?:en)?(?![\p{L}])/u, OTHER_PEOPLES_REPORTS),
        term(
            'Benennungsschwelle',
            ['Konfidenzschwelle', 'Artschwelle', 'Klassifizierungsschwelle', 'Konfidenzschwellenwert'],
            /Konfidenzschwelle|Artschwelle|Klassifizierungsschwelle/u
        ),
        term(
            'Unbekannter Vogel',
            ['Unbekannte Art', 'Unbestimmter Vogel', 'Unbestimmte Erkennung'],
            /Unbekannte[rn]? Art(?![\p{L}])|Unbestimmte[rn]? (?:Vogel|Erkennung|Besuch)/u
        ),
        term('Zustand', ['Systemgesundheit', 'Systemzustand'], /System(?:gesundheit|zustand)/u),
        term('Explorer', ['Ereignisse', 'Zu Ereignissen'], /^Ereignisse$|\bZu(?:r|m)? Ereignissen\b/u),
        term('Gartentier', ['Garten-Wildtier', 'Gartenbesucher'], /Garten-?[Ww]ildtier|Gartenbesucher/u),
        term('Modell', ['Klassifikator', 'Klassifizierer'], /Klassifikator|Klassifizierer/u),
        term('Vogelfinder', ['Vogeldetektor', 'Zuschnittdetektor', 'Zuschnittmodell', 'Crop-Detektor'], /Vogeldetektor|Zuschnitt-?(?:detektor|modell)|Crop-Detektor/u),
        term(
            'Erfordert Ihre Entscheidung',
            ['Zu prüfen', 'Prüfung erforderlich', 'Prüfwarteschlange'],
            /\bZu prüfen\b|Prüfung erforderlich|Prüfwarteschlange/u
        ),
        term('Besitzer', ['Eigentümer', 'Betreiber', 'Inhaber', 'Admin', 'Administrator'], /Eigentümer|Betreiber|(?<![\p{L}])Inhaber|\bAdmin(?:istrator)?/u, {
            keys: /^auth\.username_placeholder$/,
            reason: 'the placeholder shows the literal default user name'
        }),
        term('KI', ['LLM'], /\bLLMs?\b/)
    ]
};

/** Errors that name no cause and no next step, in each language's usual wording. */
const VAGUE_ERRORS: Record<string, RegExp> = {
    en: /something went wrong|an error (?:has )?occurred|unknown error|unexpected error|\boops\b|try again later/i,
    de: /etwas ist schief ?gelaufen|ist schief ?gegangen|ein fehler ist aufgetreten|unbekannter fehler|unerwarteter fehler|später erneut versuchen|versuchen sie es später/i,
    es: /algo salió mal|ocurrió un error|se produjo un error|error desconocido|error inesperado|inténtalo de nuevo más tarde/i,
    fr: /une erreur est survenue|une erreur s[’']est produite|quelque chose s[’']est mal passé|erreur inconnue|erreur inattendue|réessayez plus tard/i,
    it: /qualcosa è andato storto|si è verificato un errore|errore sconosciuto|errore imprevisto|riprova più tardi/i,
    pt: /algo deu errado|ocorreu um erro|erro desconhecido|erro inesperado|tente novamente mais tarde/i,
    ru: /что-то пошло не так|произошла ошибка|неизвестная ошибка|непредвиденная ошибка|повторите попытку позже/i,
    ja: /問題が発生しました|エラーが発生しました|不明なエラー|予期しないエラー|後でもう一度/,
    zh: /出了点问题|出错了|发生错误|未知错误|意外错误|请稍后再试/
};

/** The transport's own words: an errno name, an HTTP status line, a JavaScript exception. */
const RAW_ERROR =
    /\bE(?:CONN(?:REFUSED|RESET|ABORTED)|TIMEDOUT|NOTFOUND|ACCES|NOENT|PIPE|HOSTUNREACH|AI_AGAIN)\b|\berrno\b|\bTraceback\b|\b(?:Network|Type|Syntax)Error\b|\bFailed to fetch\b|\bHTTP[ -]?(?:\{\w+\}|[1-5]\d\d)(?!\d)|\b[45]\d\d (?:Bad Request|Unauthorized|Forbidden|Not Found|Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)\b|\bInternal Server Error\b|\bBad Gateway\b|\bGateway Timeout\b|\bstatus code\b/;

/** A sentence that hands over to whatever the server or an exception said. */
const BACKEND_PROSE = /[:：]\s*\{(?:error|err|message|msg|detail|details|exception)\}[.。]?$/;

/** "Health status: degraded": a state with no cause, no consequence and nothing to do. */
const STATUS_ONLY = /^[^{}.!?]{0,40}[:：]\s*(?:\{(?:status|state|level|health|severity)\}|degraded|unhealthy|error|failed|unknown)[.。]?$/i;
const STATUS_NAMESPACES = new Set(['notifications', 'jobs', 'status', 'errors', 'error', 'system_telemetry', 'update_banner', 'telemetry_banner']);

const INFORMAL_GERMAN = /(?<![\p{L}-])(?:du|dich|dir|dein(?:e[mnrs]?)?|euch|euer|eure[mnrs]?)(?![\p{L}-])/iu;

/**
 * A number and its unit share a line: the space between them is a no-break space (U+00A0 or
 * U+202F). Latin and Cyrillic unit symbols; Japanese and Chinese set a unit without a space.
 */
const UNIT_AFTER_PLAIN_SPACE = /(?:\d|\})[ ](?:[kKMGT]B|[КМГ]Б|ms|мс|lx|km|км|mph|fps|px|°[CF]|%|(?:min|mi|s|h|m)(?![\p{L}\p{N}]))(?![\p{L}])/u;

function namespaceOf(key: string): string {
    return key.split('.')[0];
}

/** Every rule the string breaks. `key` is the dotted path, starting with the namespace. */
export function lintCopy(locale: string, key: string, value: string): CopyFinding[] {
    const findings: CopyFinding[] = [];
    const add = (rule: CopyRule, detail: string) => findings.push({ rule, detail });

    // A lone dash standing in for an empty value is not punctuation.
    if (value.includes('—') && value.trim() !== '—') add('em-dash', 'use a comma, a colon, a semicolon or a full stop');

    const vague = VAGUE_ERRORS[locale]?.exec(value);
    if (vague) add('vague-error', `"${vague[0]}" names no cause and no next step`);

    const raw = RAW_ERROR.exec(value);
    if (raw) add('raw-error', `"${raw[0]}" is the transport's wording; say the cause and the next step`);

    if (BACKEND_PROSE.test(value)) add('backend-prose', 'ends by quoting a raw message; word the cause here and keep the raw text in details');

    if (STATUS_NAMESPACES.has(namespaceOf(key)) && STATUS_ONLY.test(value)) {
        add('status-only', 'states a status alone; say what it means and what to do');
    }

    for (const entry of GLOSSARY[locale] ?? []) {
        if (entry.except?.keys.test(key)) continue;
        const found = entry.pattern.exec(value);
        if (found) add('glossary', `"${found[0]}": the glossary says "${entry.use}"`);
    }

    if (locale === 'de') {
        const informal = INFORMAL_GERMAN.exec(value);
        if (informal) add('informal-address', `"${informal[0]}": German copy addresses the reader as "Sie"`);
    }

    const unit = UNIT_AFTER_PLAIN_SPACE.exec(value);
    if (unit) add('unit-spacing', `"${unit[0]}": join a number and its unit with a no-break space`);

    return findings;
}

type CopyLeaf = readonly [key: string, value: string];

/** The dotted key and text of every string in a dictionary. */
function copyLeaves(node: unknown, prefix = ''): CopyLeaf[] {
    if (typeof node !== 'object' || node === null || Array.isArray(node)) return [];
    return Object.entries(node).flatMap(([key, child]): CopyLeaf[] => {
        const path = prefix ? `${prefix}.${key}` : key;
        return typeof child === 'string' ? [[path, child]] : copyLeaves(child, path);
    });
}

/** Counts per rule, then per "language/namespace": the shape of the committed baseline. */
export type CopyCounts = Partial<Record<CopyRule, Record<string, number>>>;

export interface CopyReport {
    counts: CopyCounts;
    /** Every finding, "rule language key: detail", for the message of a failing run. */
    lines: string[];
}

export function lintDictionaries(dictionaries: Record<string, unknown>, reference = 'en'): CopyReport {
    const counts: CopyCounts = {};
    const lines: string[] = [];
    const record = (rule: CopyRule, locale: string, key: string, detail: string) => {
        const bucket = (counts[rule] ??= {});
        const scope = `${locale}/${namespaceOf(key)}`;
        bucket[scope] = (bucket[scope] ?? 0) + 1;
        lines.push(`${rule} ${locale} ${key}: ${detail}`);
    };
    const referenceKeys = copyLeaves(dictionaries[reference]).map(([key]) => key);
    for (const [locale, dictionary] of Object.entries(dictionaries)) {
        const leaves = copyLeaves(dictionary);
        for (const [key, value] of leaves) {
            for (const finding of lintCopy(locale, key, value)) record(finding.rule, locale, key, finding.detail);
        }
        if (locale === reference) continue;
        const present = new Set(leaves.map(([key]) => key));
        for (const key of referenceKeys) {
            if (!present.has(key)) record('missing-key', locale, key, `present in ${reference}, missing here`);
        }
    }
    return { counts, lines };
}
