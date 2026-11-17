// @ts-nocheck: this audit reads and rewrites its baseline under Vitest's Node environment; Node
// types are intentionally absent from the browser application tsconfig.
/**
 * The copy-lint gate. docs/standards/glossary.md is the standard; copy-lint.ts finds the strings
 * that break it; this test counts the findings per rule and per "language/namespace" and compares
 * them with copy-lint.baseline.json.
 *
 * The counts may only fall. A scope whose count rises fails, as does a scope the baseline does
 * not list. A scope whose count falls fails too, until the baseline is lowered with it in the
 * same change, so a fixed string can never be quietly unfixed later:
 *
 *   npm run copy:baseline
 *
 * A rule whose baseline is empty is simply a rule: nothing may break it.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { loweredCounts, lowerBaseline, raisedCounts, ruleTotals } from '../../../scripts/copy-baseline.mjs';
import { authoredLocale } from './authored-locales';
import { COPY_RULES, GLOSSARY, PROPER_NAMES, THIRD_PARTY_TERMS, lintCopy, lintDictionaries, type CopyCounts, type CopyRule } from './copy-lint';
import { SUPPORTED_LOCALES } from './locale-partition';

const BASELINE_PATH = join(process.cwd(), 'src/lib/i18n/copy-lint.baseline.json');
const GLOSSARY_PATH = join(process.cwd(), '../../docs/standards/glossary.md');
const MODEL_REGISTRY_PATH = join(process.cwd(), '../../backend/app/services/model_manager.py');

function rules(locale: string, key: string, value: string): CopyRule[] {
    return lintCopy(locale, key, value).map((finding) => finding.rule);
}

describe('the copy lint', () => {
    it('finds an em dash used as punctuation, not a lone dash standing for no value', () => {
        expect(rules('en', 'about.intro', 'Runs locally — nothing leaves')).toEqual(['em-dash']);
        expect(rules('en', 'common.empty_value', '—')).toEqual([]);
    });

    it('finds an error that names no cause and no next step, in each language', () => {
        expect(rules('en', 'errors.generic', 'Something went wrong.')).toEqual(['vague-error']);
        expect(rules('en', 'errors.generic', 'Could not save. Please try again later.')).toEqual(['vague-error']);
        expect(rules('de', 'errors.generic', 'Ein Fehler ist aufgetreten.')).toEqual(['vague-error']);
        expect(rules('fr', 'errors.generic', 'Une erreur est survenue.')).toEqual(['vague-error']);
        expect(rules('ja', 'errors.generic', 'エラーが発生しました')).toEqual(['vague-error']);
        expect(rules('en', 'errors.frigate', 'Frigate did not answer. Check its address in Settings › Connection.')).toEqual([]);
    });

    it('finds errno names, HTTP status lines and exception names shown as copy', () => {
        expect(rules('en', 'errors.a', 'ECONNREFUSED while reaching Frigate')).toEqual(['raw-error']);
        expect(rules('en', 'errors.b', 'Frigate answered HTTP {status}')).toEqual(['raw-error']);
        expect(rules('de', 'errors.c', 'Frigate meldete 502 Bad Gateway')).toEqual(['raw-error']);
        expect(rules('en', 'errors.d', 'TypeError: Failed to fetch')).toEqual(['raw-error']);
    });

    it('does not mistake an address, a protocol name or HTTPS advice for a raw error', () => {
        expect(rules('en', 'settings.url', 'Start the address with http:// or https://')).toEqual([]);
        expect(rules('en', 'settings.https', 'This page is served over HTTP, so passwords can be read. Serve it over HTTPS.')).toEqual([]);
    });

    it('finds a sentence that ends by quoting whatever the server said', () => {
        expect(rules('en', 'garden.move_failed', 'Could not move this photo: {message}')).toEqual(['backend-prose']);
        expect(rules('en', 'garden.move_failed', 'Could not move this photo: {error}.')).toEqual(['backend-prose']);
        expect(rules('en', 'garden.score', 'Species score: {score}')).toEqual([]);
    });

    it('finds a notification that states a status and nothing else', () => {
        expect(rules('en', 'notifications.system_health_message', 'Health status: {status}')).toEqual(['status-only']);
        expect(rules('en', 'notifications.system_health_message', 'Health status: degraded')).toEqual(['status-only']);
        expect(rules('en', 'notifications.health', 'Health needs attention: Frigate did not answer. Open Health to see when it last did.')).toEqual([]);
    });

    it('leaves a labelled fact outside the notification namespaces alone', () => {
        expect(rules('en', 'detection.reference_conservation', 'Conservation status: {status}')).toEqual([]);
    });

    it('finds a word the glossary replaced and names the word to use', () => {
        expect(lintCopy('en', 'dashboard.total', '{count} detections today')).toEqual([
            { rule: 'glossary', detail: '"detections": the glossary says "visit, capture or call"' }
        ]);
        expect(rules('en', 'shortcuts.go_events', 'Go to Events')).toEqual(['glossary']);
        expect(rules('en', 'settings.auth.username', 'Admin username')).toEqual(['glossary']);
        expect(rules('de', 'visits.owner_confirmed', 'Vom Eigentümer bestätigt')).toEqual(['glossary']);
        expect(rules('de', 'about.pipeline.classifier', 'Klassifikator')).toEqual(['glossary']);
    });

    it('keeps a word where it means something else: the motion detector, the Frigate event, a compound noun', () => {
        expect(rules('en', 'garden.motion', 'Needs the motion detector under Garden models')).toEqual([]);
        expect(rules('en', 'settings.connection.mqtt', 'The broker Frigate publishes its events to')).toEqual([]);
        expect(rules('de', 'garden.motion_coverage', 'Vogelerkennung und Kameralast pausieren')).toEqual([]);
    });

    it('keeps "sighting" for other people’s reports and the literal default user name', () => {
        expect(rules('en', 'about.outbound.ebird_desc', 'Recent sightings near the feeder.')).toEqual([]);
        // The species dialog's eBird section and its map markers are eBird's reports too.
        expect(rules('en', 'species_detail.recent_sightings', 'Recent sightings')).toEqual([]);
        expect(rules('en', 'common.map_sighting', 'Sighting location')).toEqual([]);
        expect(rules('en', 'dashboard.summary', '{count} sightings today')).toEqual(['glossary']);
        expect(rules('en', 'auth.username_placeholder', 'admin')).toEqual([]);
    });

    it('finds informal German, and only in German', () => {
        expect(rules('de', 'setup.welcome', 'Richte dein Futterhaus ein')).toEqual(['informal-address']);
        expect(rules('de', 'setup.welcome', 'Wenn du möchtest')).toEqual(['informal-address']);
        expect(rules('de', 'setup.welcome', 'Richten Sie Ihr Futterhaus ein')).toEqual([]);
        expect(rules('en', 'settings.models', 'the model dir is read-only')).toEqual([]);
    });

    it('finds a number or a placeholder joined to its unit by a breaking space', () => {
        expect(rules('en', 'settings.models.size_mb', '{size} MB')).toEqual(['unit-spacing']);
        expect(rules('en', 'health.disk', '955 MB of 30.79 GB')).toEqual(['unit-spacing']);
        expect(rules('en', 'health.cpu', 'CPU now 39 %')).toEqual(['unit-spacing']);
        expect(rules('en', 'settings.models.size_mb', '{size} MB')).toEqual([]);
        expect(rules('en', 'health.cpu', 'CPU now {percent}%')).toEqual([]);
    });

    it('does not read an ordinary word after a number as a unit', () => {
        expect(rules('en', 'jobs.summary', '{count} models, 3 minutes, 2 hidden, 4 species')).toEqual([]);
    });

    it('leaves a forbidden word alone inside a code span, in another product’s term and in a catalogue name', () => {
        expect(rules('en', 'setup.cameras.hint', 'Enable motion detection in Frigate for this camera.')).toEqual([]);
        expect(rules('en', 'setup.cameras.hint', 'Frigate needs object detection on the same stream.')).toEqual([]);
        expect(rules('en', 'settings.debug.field', 'The <code>detection</code> field holds the Frigate ID.')).toEqual([]);
        expect(rules('en', 'settings.debug.field', 'Set <code class="x">detections.min_score</code> for each camera.')).toEqual([]);
        expect(rules('en', 'model_eval.checks.row', 'Bird Crop Detector')).toEqual([]);
        expect(rules('en', 'model_eval.checks.row', 'Bird Crop Detector Accurate (YOLOX-Tiny)')).toEqual([]);
    });

    it('still refuses the same words as the app’s own nouns, beside an exempt phrase or not', () => {
        expect(rules('en', 'setup.cameras.hint', 'Motion detection starts a clip; each detection is then named.')).toEqual(['glossary']);
        expect(rules('en', 'settings.debug.field', 'The <code>id</code> of this detection')).toEqual(['glossary']);
        expect(rules('en', 'detection.detector_unavailable', 'Install a crop detector to find additional birds.')).toEqual(['glossary']);
        expect(rules('en', 'audio.hidden', 'Audio detection hidden.')).toEqual(['glossary']);
    });

    it('gives every third-party term the product that owns it', () => {
        expect(THIRD_PARTY_TERMS.filter((entry) => !/^(?:Frigate|BirdNET-Go)\b.{10,}/.test(entry.owner))).toEqual([]);
    });

    it('keeps every catalogue name in the model registry clear of the glossary rule', () => {
        const registry = readFileSync(MODEL_REGISTRY_PATH, 'utf8');
        const names = [...new Set([...registry.matchAll(/"name":\s*"([^"]+)"/g)].map((match) => match[1]))];
        expect(names.length).toBeGreaterThan(10);
        expect(names).toContain(PROPER_NAMES[1]);
        expect(names.filter((name) => rules('en', 'settings.models.name', name).includes('glossary')), 'add the name to PROPER_NAMES in copy-lint.ts').toEqual([]);
    });

    it('finds the whole errno family, HTTP status lines and exception prefixes through the dictionary gate', () => {
        const report = lintDictionaries({
            en: {
                errors: {
                    disk: 'Could not save the photo: ENOSPC',
                    limit: 'HTTP/1.1 429 Too Many Requests',
                    script: 'ReferenceError: value is not defined',
                    refused: 'Frigate said EHOSTUNREACH',
                    python: 'KeyError while reading the model list',
                    custom: 'ModelLoadException: weights missing',
                    reason: 'eBird answered 403 Forbidden',
                    plain: 'Frigate did not answer. Check its address in Settings → Cameras.',
                    words: 'This page was not found. An error log is kept in Health. EVA-02 is not installed.'
                }
            }
        });
        expect(report.counts).toEqual({ 'raw-error': { 'en/errors': 7 } });
        expect(report.lines.filter((line) => line.startsWith('raw-error')).map((line) => line.split(' ')[2])).toEqual([
            'errors.disk:', 'errors.limit:', 'errors.script:', 'errors.refused:', 'errors.python:', 'errors.custom:', 'errors.reason:'
        ]);
    });

    it('finds a status-only notification in each of the nine languages, and not a sentence that explains', () => {
        const examples: Record<string, [statusOnly: string, explained: string]> = {
            en: ['Health status: degraded', 'Health needs attention: Frigate has not answered since 08:14.'],
            de: ['Zustand: Fehler', 'Zustand: Frigate antwortet seit 08:14 nicht mehr.'],
            es: ['Estado del sistema: degradado', 'Estado: Frigate no responde desde las 08:14.'],
            fr: ['État du système : dégradé', 'État : Frigate ne répond plus depuis 08:14.'],
            it: ['Stato del sistema: degradato', 'Stato: Frigate non risponde dalle 08:14.'],
            pt: ['Estado do sistema: degradado', 'Estado: o Frigate não responde desde as 08:14.'],
            ru: ['Состояние системы: ошибка', 'Состояние: Frigate не отвечает с 08:14.'],
            ja: ['システム状態: エラー', 'システム状態: Frigate が 08:14 から応答していません。'],
            zh: ['系统状态：错误', '系统状态：Frigate 自 08:14 起没有响应。']
        };
        expect(Object.keys(examples).sort()).toEqual([...SUPPORTED_LOCALES].sort());
        for (const [locale, [statusOnly, explained]] of Object.entries(examples)) {
            expect(rules(locale, 'notifications.system_health_message', statusOnly), `${locale}: ${statusOnly}`).toEqual(['status-only']);
            expect(rules(locale, 'notifications.system_health_message', explained), `${locale}: ${explained}`).toEqual([]);
        }
    });

    it('counts per rule and "language/namespace", and reports keys another language lacks', () => {
        const report = lintDictionaries({
            en: { nav: { explorer: 'Explorer', events: 'Go to Events' }, about: { title: 'About' } },
            de: { nav: { explorer: 'Explorer' } }
        });
        expect(report.counts).toEqual({ glossary: { 'en/nav': 1 }, 'missing-key': { 'de/nav': 1, 'de/about': 1 } });
        expect(report.lines).toContain('missing-key de about.title: present in en, missing here');
    });
});

/** The words in the last column of each term row under one heading of the glossary document. */
function forbiddenInGlossary(document: string, heading: string, isTermRow: (firstCell: string) => boolean): string[] {
    const start = document.indexOf(`\n## ${heading}`);
    const end = document.indexOf('\n## ', start + 1);
    return document
        .slice(start, end === -1 ? undefined : end)
        .split('\n')
        .filter((line) => line.startsWith('|'))
        .map((line) => line.split('|').slice(1, -1).map((cell) => cell.trim()))
        .filter((cells) => cells.length === 3 && isTermRow(cells[0]))
        .flatMap((cells) => cells[2].split(',').map((word) => word.trim()).filter(Boolean));
}

describe('the glossary and the lint', () => {
    const document = readFileSync(GLOSSARY_PATH, 'utf8');
    const listed: Record<string, string[]> = {
        en: forbiddenInGlossary(document, '1. Terms', (cell) => cell.startsWith('**')),
        de: forbiddenInGlossary(document, '2. German terms', (cell) => cell !== 'English' && !cell.startsWith('-'))
    };
    const context: Record<string, (word: string) => string> = {
        en: (word) => `Then ${word} is shown here.`,
        de: (word) => `Hier steht ${word} im Satz.`
    };

    it('cover the same languages', () => {
        expect(Object.keys(GLOSSARY).sort()).toEqual(Object.keys(listed).sort());
    });

    for (const [locale, terms] of Object.entries(GLOSSARY)) {
        const enforced = terms.flatMap((entry) => entry.avoid);

        it(`${locale}: every word the glossary forbids is enforced, and every enforced word is in the glossary`, () => {
            expect(listed[locale].length).toBeGreaterThan(20);
            expect([...enforced].sort(), 'the "Not" columns of docs/standards/glossary.md and GLOSSARY in copy-lint.ts must list the same words').toEqual([...listed[locale]].sort());
            expect(new Set(enforced).size, 'a word belongs to one term').toBe(enforced.length);
        });

        it(`${locale}: every forbidden word fails in a sentence, and the finding names the term to use`, () => {
            const passed = terms.flatMap((entry) =>
                entry.avoid.filter((word) => {
                    const findings = lintCopy(locale, 'dashboard.note', context[locale](word));
                    return !findings.some((finding) => finding.rule === 'glossary' && finding.detail.includes(`"${entry.use}"`));
                })
            );
            expect(passed).toEqual([]);
        });

        it(`${locale}: the term each row keeps is written in the glossary`, () => {
            const kept = terms.flatMap((entry) => entry.use.split(/, | or | oder /));
            expect(kept.filter((word) => !document.includes(word))).toEqual([]);
        });
    }

    it('refuses the forbidden words a reviewer found passing', () => {
        expect(rules('en', 'shortcuts.go_history', 'Open the history page')).toEqual(['glossary']);
        expect(rules('en', 'detection.score', 'Probability: {score}')).toEqual(['glossary']);
        expect(rules('en', 'settings.public_access.note', 'An anonymous user sees the last 30 days.')).toEqual(['glossary']);
        expect(rules('de', 'events.open', 'Datensatz öffnen')).toEqual(['glossary']);
    });

    it('matches a forbidden word whole, so a longer word or a compound is not mistaken for it', () => {
        expect(rules('de', 'garden.motion_coverage', 'Vogelerkennung und Kameralast pausieren')).toEqual([]);
        expect(rules('en', 'settings.auth.note', 'Administration is under Settings.')).toEqual([]);
        expect(rules('de', 'first_run.admin_username', 'Admin-Benutzername')).toEqual(['glossary']);
        // The old German label is matched in any case: lower case, it still names the queue.
        expect(rules('de', 'garden.pending', 'Zu prüfen')).toEqual(['glossary']);
        expect(rules('de', 'dashboard.day_bar.nothing_to_review', 'nichts zu prüfen')).toEqual(['glossary']);
        expect(rules('de', 'garden.explorer.empty_pending', 'Keine Gartenaufnahmen zu prüfen')).toEqual(['glossary']);
        // The sentences that use the verb are exempt by key, so the same words elsewhere still count.
        expect(rules('de', 'detection.upstream_check.not_checked', 'Öffnen Sie diesen Eintrag erneut, um es zu prüfen.')).toEqual([]);
        expect(rules('de', 'visits.capture_actions', 'Öffnen Sie eine Aufnahme, um die Bestimmung zu prüfen.')).toEqual([]);
        expect(rules('de', 'dashboard.some_new_key', 'Öffnen Sie eine Aufnahme, um die Bestimmung zu prüfen.')).toEqual(['glossary']);
    });

    it('gives every exemption a reason', () => {
        const exemptions = Object.values(GLOSSARY).flat().flatMap((entry) => (entry.except ? [entry.except] : []));
        expect(exemptions.filter((exemption) => exemption.reason.trim().length < 20)).toEqual([]);
    });
});

describe('the baseline updater', () => {
    const baseline = { glossary: { 'en/about': 3, 'de/about': 2 }, 'raw-error': { 'en/jobs': 1 } };

    it('lowers counts that fell and drops a scope that reached none', () => {
        const measured = { glossary: { 'en/about': 1 } };
        expect(lowerBaseline(baseline, measured)).toEqual({ next: measured, raised: [] });
    });

    it('refuses a rise rather than absorbing it, in a listed scope, a new scope or a new rule', () => {
        const risen = lowerBaseline(baseline, {
            glossary: { 'en/about': 4, 'en/nav': 1 },
            'vague-error': { 'de/errors': 1 }
        });
        expect(risen.next).toBeNull();
        expect(risen.raised).toEqual(['glossary en/about: 3 -> 4', 'glossary en/nav: 0 -> 1', 'vague-error de/errors: 0 -> 1']);
    });

    it('lets CI refuse a branch whose committed baseline allows more than its base', () => {
        expect(raisedCounts(baseline, { glossary: { 'en/about': 3, 'de/about': 3 } })).toEqual(['glossary de/about: 2 -> 3']);
        expect(raisedCounts(baseline, { glossary: { 'en/about': 2 } })).toEqual([]);
    });

    it('names the counts a copy pass lowered, so the baseline is lowered with them', () => {
        expect(loweredCounts(baseline, { glossary: { 'en/about': 3 } })).toEqual(['glossary de/about: 2 -> 0', 'raw-error en/jobs: 1 -> 0']);
    });
});

describe('the copy-lint gate', () => {
    const dictionaries = Object.fromEntries(SUPPORTED_LOCALES.map((locale) => [locale, authoredLocale(locale)]));
    const report = lintDictionaries(dictionaries);
    const measured = report.counts as Record<string, Record<string, number>>;
    const committed: CopyCounts = existsSync(BASELINE_PATH) ? JSON.parse(readFileSync(BASELINE_PATH, 'utf8')) : {};

    if (process.env.UPDATE_COPY_BASELINE === '1') {
        // The updater only ever lowers: a rise is refused and nothing is written.
        // The first run has nothing to lower from, so it records what it measured.
        const { next, raised } = existsSync(BASELINE_PATH) ? lowerBaseline(committed, measured) : { next: measured, raised: [] };
        if (!next) throw new Error(`[copy] refusing to raise the baseline:\n  ${raised.join('\n  ')}\nReword the copy instead (docs/standards/glossary.md).`);
        const ordered = Object.fromEntries(
            COPY_RULES.filter((rule) => next[rule]).map((rule) => [rule, Object.fromEntries(Object.entries(next[rule]).sort(([a], [b]) => a.localeCompare(b)))])
        );
        writeFileSync(BASELINE_PATH, JSON.stringify(ordered, null, 2) + '\n');
        console.log(`[copy] baseline lowered: ${JSON.stringify(ruleTotals(ordered))}`);
    }

    const baseline: Record<string, Record<string, number>> = existsSync(BASELINE_PATH) ? JSON.parse(readFileSync(BASELINE_PATH, 'utf8')) : {};

    it('lets no namespace add copy that breaks the glossary', () => {
        const raised = raisedCounts(baseline, measured);
        const scopes = new Set(raised.map((line) => line.split(':')[0]));
        // The findings in the scopes that rose, so the failure names the strings to reword.
        const findings = report.lines.filter((line) => {
            const [rule, locale, key] = line.split(' ');
            return scopes.has(`${rule} ${locale}/${key.split('.')[0]}`);
        });
        expect({ raised, findings }, 'reword the copy to follow docs/standards/glossary.md').toEqual({ raised: [], findings: [] });
    });

    it('has its baseline lowered whenever copy is fixed', () => {
        expect(loweredCounts(baseline, measured), 'run `npm run copy:baseline` and commit the lowered baseline').toEqual([]);
    });

    it('lists only rules the lint knows', () => {
        expect(Object.keys(baseline).filter((rule) => !COPY_RULES.includes(rule as CopyRule))).toEqual([]);
    });
});
