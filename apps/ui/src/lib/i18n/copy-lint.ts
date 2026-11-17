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
    /** The words it replaces, exactly as the "Not" column of docs/standards/glossary.md lists them. */
    avoid: readonly string[];
    /** Built from `avoid`, so the lint cannot enforce a word the glossary does not list, or miss one it does. */
    pattern: RegExp;
    /** Keys where the avoided word means something else, with the reason. */
    except?: { keys: RegExp; reason: string };
}

interface TermOptions {
    /** Match the capitals as written: "Go to Events" is a page name, "events" is Frigate's word. */
    exact?: boolean;
    except?: GlossaryTerm['except'];
}

function escaped(text: string): string {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** The listed words as whole words: a longer word or a German compound that contains one is another word. */
function wholeWords(words: readonly string[], exact = false): RegExp {
    const longestFirst = [...words].sort((a, b) => b.length - a.length).map(escaped);
    return new RegExp(`(?<![\\p{L}\\p{N}])(?:${longestFirst.join('|')})(?![\\p{L}\\p{N}])`, exact ? 'u' : 'iu');
}

function term(use: string, avoid: readonly string[], options: TermOptions = {}): GlossaryTerm {
    return { use, avoid, pattern: wholeWords(avoid, options.exact), except: options.except };
}

/** A sighting is someone else's report, so the word stays where the copy is about eBird or a place. */
const OTHER_PEOPLES_REPORTS = {
    keys: /ebird|nearby|notable|reference|hotspot|location|inat/i,
    reason: 'a sighting is a report from eBird or another observer, which is what these strings describe'
};
const DEFAULT_USER_NAME = {
    keys: /^auth\.username_placeholder$/,
    reason: 'the placeholder shows the literal default user name'
};

/**
 * One entry per glossary row that has words to avoid. The "Not" columns of the glossary document
 * and these lists are the same sets of words; copy-lint.test.ts fails when they differ either way.
 */
export const GLOSSARY: Record<string, readonly GlossaryTerm[]> = {
    en: [
        term('visit, capture or call', ['detection', 'detections']),
        term('visit', ['sighting', 'sightings'], { except: OTHER_PEOPLES_REPORTS }),
        term('model', ['classifier', 'classifiers']),
        term('naming threshold', ['confidence threshold', 'species threshold', 'classification threshold', 'score threshold', 'configured threshold']),
        term('Unknown bird', ['Unknown species', 'Unidentified bird', 'Unidentified visit']),
        term('bird finder', ['crop detector', 'crop detectors', 'bird detector', 'bird detectors', 'crop model', 'crop models']),
        term('score', ['probability', 'certainty']),
        term('AI', ['LLM', 'LLMs'], { exact: true }),
        term('Explorer', ['Go to Events', 'Events page', 'Events tab'], { exact: true }),
        term('Explorer', ['history page']),
        term('Health', ['system health', 'Errors page', 'Diagnostics page']),
        term('Needs your call', ['Needs review', 'Awaiting review', 'Pending review', 'review queue']),
        term('Garden animal', ['Garden wildlife', 'garden visitor', 'garden visitors', 'Garden creature', 'Garden creatures']),
        term('owner', ['admin', 'admins', 'administrator', 'administrators', 'operator', 'operators'], { except: DEFAULT_USER_NAME }),
        term('guest', ['anonymous user', 'anonymous users', 'public user', 'public users'])
    ],
    de: [
        term('Besuch, Aufnahme oder Ruf', ['Erkennung', 'Erkennungen']),
        term('Besuch', ['Sichtung', 'Sichtungen'], { except: OTHER_PEOPLES_REPORTS }),
        term('Eintrag', ['Datensatz', 'Datensatzes', 'Datensätze', 'Datensätzen']),
        term('Ruf', ['Audioerkennung', 'Audioerkennungen']),
        term('Modell', ['Klassifikator', 'Klassifikators', 'Klassifikatoren', 'Klassifizierer']),
        term('Benennungsschwelle', ['Konfidenzschwelle', 'Konfidenzschwellenwert', 'Artschwelle', 'Klassifizierungsschwelle']),
        term('Unbekannter Vogel', ['Unbekannte Art', 'Unbestimmter Vogel']),
        term('Vogelfinder', ['Vogeldetektor', 'Zuschnittdetektor', 'Zuschnittmodell', 'Crop-Detektor']),
        term('KI', ['LLM', 'LLMs'], { exact: true }),
        term('Explorer', ['Zu Ereignissen', 'Ereignisseite'], { exact: true }),
        term('Zustand', ['Systemgesundheit', 'Systemzustand']),
        term('Erfordert Ihre Entscheidung', ['Zu prüfen', 'Prüfung erforderlich', 'Prüfwarteschlange']),
        term('Gartentier', ['Garten-Wildtier', 'Gartenbesucher']),
        term('Besitzer', ['Eigentümer', 'Eigentümers', 'Betreiber', 'Betreibers', 'Inhaber', 'Admin', 'Administrator'], { except: DEFAULT_USER_NAME })
    ]
};

/**
 * Where a forbidden word is not the app's own noun, the glossary rule does not read it. Three
 * narrow cases, each documented in the glossary:
 *
 * - text inside `<code>`: an identifier, a setting name or a value, shown literally;
 * - a third-party product's own term for its own feature, which the owner will look for under
 *   that name in that product;
 * - a model's or a catalogue entry's proper name, as the registry spells it.
 */
const CODE_SPAN = /<code\b[^>]*>[\s\S]*?<\/code>/gi;
export const THIRD_PARTY_TERMS: readonly { term: string; owner: string }[] = [
    { term: 'motion detection', owner: 'Frigate: the setting that starts a recording' },
    { term: 'object detection', owner: 'Frigate: the detector that finds a bird in the frame' }
];
export const PROPER_NAMES: readonly string[] = ['Bird Crop Detector Accurate', 'Bird Crop Detector'];
const NOT_OUR_NOUNS = wholeWords([...THIRD_PARTY_TERMS.map((entry) => entry.term), ...PROPER_NAMES]);

/** The string as the glossary rule reads it: without code spans, third-party terms and proper names. */
function ownWords(value: string): string {
    return value.replace(CODE_SPAN, ' ').replace(new RegExp(NOT_OUR_NOUNS.source, 'giu'), ' ');
}

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

/** The errno names a network, a disk or a process can report (POSIX and Node's resolver). */
const ERRNO_NAMES =
    '2BIG ACCES ADDRINUSE ADDRNOTAVAIL AFNOSUPPORT AGAIN AI_AGAIN ALREADY BADF BUSY CANCELED CHILD CONNABORTED CONNREFUSED CONNRESET DEADLK DESTADDRREQ DQUOT EXIST FAULT FBIG HOSTDOWN HOSTUNREACH INPROGRESS INTR INVAL IO ISCONN ISDIR LOOP MFILE MLINK MSGSIZE NAMETOOLONG NETDOWN NETRESET NETUNREACH NFILE NOBUFS NODATA NODEV NOENT NOEXEC NOLCK NOMEM NOSPC NOSYS NOTCONN NOTDIR NOTEMPTY NOTFOUND NOTSOCK NOTSUP NOTTY NXIO OPNOTSUPP OVERFLOW PERM PIPE PROTO PROTONOSUPPORT RANGE ROFS SPIPE SRCH STALE TIMEDOUT TXTBSY WOULDBLOCK XDEV'
        .split(' ')
        .join('|');
const HTTP_REASONS =
    'Bad Request|Unauthorized|Payment Required|Forbidden|Not Found|Method Not Allowed|Not Acceptable|Request Timeout|Conflict|Gone|Payload Too Large|Unsupported Media Type|Unprocessable (?:Entity|Content)|Too Many Requests|Internal Server Error|Not Implemented|Bad Gateway|Service Unavailable|Gateway Timeout';
/** The transport's own words: an errno name, an HTTP status line, an exception's class name. */
const RAW_ERRORS: readonly RegExp[] = [
    new RegExp(`\\bE(?:${ERRNO_NAMES})\\b`),
    /\berrno\b/i,
    /\bTraceback\b/,
    // An exception class as a runtime prints it: "TypeError", "ReferenceError: x is not defined", "KeyError".
    /\b[A-Z][A-Za-z]*(?:Error|Exception)\b(?=:)|\b(?:Type|Reference|Syntax|Range|Network|Abort|Key|Value|Runtime|Timeout|Connection|Permission|FileNotFound|OS|IO)Error\b/,
    /\bFailed to fetch\b/,
    // A status line or its parts: "HTTP/1.1 429 Too Many Requests", "HTTP 502", "HTTP {status}", "502 Bad Gateway".
    /\bHTTP\/\d(?:\.\d)?(?![\w.])/,
    /\bHTTP[ -]?(?:\{\w+\}|[1-5]\d\d)(?!\d)/,
    new RegExp(`\\b[1-5]\\d\\d (?:${HTTP_REASONS})\\b`),
    /\b(?:Internal Server Error|Bad Gateway|Gateway Timeout|Service Unavailable|Too Many Requests)\b/,
    /\bstatus code\b/i
];

/** A sentence that hands over to whatever the server or an exception said. */
const BACKEND_PROSE = /[:：]\s*\{(?:error|err|message|msg|detail|details|exception)\}[.。]?$/;

/**
 * "Health status: degraded": a state with no cause, no consequence and nothing to do. The state
 * words are each language's own, since a translated notification is as empty as the English one.
 */
const STATUS_VALUES: Record<string, readonly string[]> = {
    en: ['degraded', 'unhealthy', 'healthy', 'error', 'failed', 'unknown', 'ok', 'warning', 'critical'],
    de: ['beeinträchtigt', 'eingeschränkt', 'fehlerhaft', 'Fehler', 'fehlgeschlagen', 'unbekannt', 'gesund', 'Warnung', 'kritisch'],
    es: ['degradado', 'error', 'fallido', 'desconocido', 'correcto', 'advertencia', 'crítico'],
    fr: ['dégradé', 'erreur', 'échec', 'inconnu', 'sain', 'avertissement', 'critique'],
    it: ['degradato', 'errore', 'non riuscito', 'sconosciuto', 'integro', 'avviso', 'critico'],
    pt: ['degradado', 'erro', 'falhou', 'desconhecido', 'íntegro', 'aviso', 'crítico'],
    ru: ['ухудшено', 'ошибка', 'сбой', 'неизвестно', 'в норме', 'предупреждение', 'критично'],
    ja: ['低下', 'エラー', '失敗', '不明', '正常', '警告', '重大'],
    zh: ['降级', '错误', '失败', '未知', '正常', '警告', '严重']
};
const STATUS_PLACEHOLDER = '\\{(?:status|state|level|health|severity)\\}';
function statusOnly(locale: string): RegExp {
    const words = [...new Set([...(STATUS_VALUES[locale] ?? []), ...STATUS_VALUES.en])].map(escaped);
    return new RegExp(`^[^{}.!?。！？]{0,40}\\s?[:：]\\s*(?:${STATUS_PLACEHOLDER}|${words.join('|')})[.。]?$`, 'iu');
}
const STATUS_ONLY: Record<string, RegExp> = Object.fromEntries(Object.keys(STATUS_VALUES).map((locale) => [locale, statusOnly(locale)]));
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

    const raw = RAW_ERRORS.map((pattern) => pattern.exec(value)).find((found) => found !== null);
    if (raw) add('raw-error', `"${raw[0]}" is the transport's wording; say the cause and the next step`);

    if (BACKEND_PROSE.test(value)) add('backend-prose', 'ends by quoting a raw message; word the cause here and keep the raw text in details');

    if (STATUS_NAMESPACES.has(namespaceOf(key)) && (STATUS_ONLY[locale] ?? STATUS_ONLY.en).test(value)) {
        add('status-only', 'states a status alone; say what it means and what to do');
    }

    const own = ownWords(value);
    for (const entry of GLOSSARY[locale] ?? []) {
        if (entry.except?.keys.test(key)) continue;
        const found = entry.pattern.exec(own);
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
