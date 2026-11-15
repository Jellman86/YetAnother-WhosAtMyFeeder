import { describe, expect, it } from 'vitest';
import source from './ModelEvaluation.svelte?raw';
import apiSource from '../api/model_eval.ts?raw';
import detectionSource from '../components/settings/DetectionSettings.svelte?raw';
import wizardSource from '../components/setup/ModelStep.svelte?raw';
import appSource from '../../App.svelte?raw';
import settingsSource from './Settings.svelte?raw';
import detectionSettingsSource from '../components/settings/DetectionSettings.svelte?raw';
import { authoredLocale } from '../i18n/authored-locales';
import { routeOffersRefresh } from '../app/route-title';

/**
 * Model evaluation is an owner page that was written apart from the rest of the app: English
 * typed into the markup, panels and checkboxes built by hand, options named after files, and a
 * raw server phrase as its only error. These hold it to the page contract everything else keeps.
 */
const markup = source.slice(source.indexOf('</script>') + '</script>'.length);

/**
 * The markup with every `{…}` expression, comment and tag left out: what remains is typed text.
 * Read one character at a time, because an expression may hold a `>` and a tag may hold braces.
 */
function typedText(component: string): string {
    let text = '';
    let braces = 0;
    let inTag = false;
    for (let index = 0; index < component.length; index += 1) {
        const char = component[index];
        if (braces === 0 && !inTag && component.startsWith('<!--', index)) {
            const end = component.indexOf('-->', index);
            index = end === -1 ? component.length : end + 2;
        } else if (char === '{') braces += 1;
        else if (char === '}') braces -= 1;
        else if (braces > 0) continue;
        else if (char === '<') inTag = true;
        else if (char === '>') inTag = false;
        else if (!inTag) text += char;
    }
    return text;
}

/** Each opening tag of one element, read to its own closing bracket. */
function openingTags(component: string, tag: string): string[] {
    return component.split(`<${tag}`).slice(1).map((tail) => tail.slice(0, tail.search(/>\s*\n|>$/m) + 1));
}

function leaves(value: unknown, prefix = ''): Array<[string, string]> {
    if (typeof value === 'string') return [[prefix, value]];
    if (!value || typeof value !== 'object') return [];
    return Object.entries(value).flatMap(([key, child]) => leaves(child, prefix ? `${prefix}.${key}` : key));
}

const english = Object.fromEntries(leaves(authoredLocale('en')));

describe('model evaluation reads in the owner’s language', () => {
    it('types no words into the markup, so every string can be translated', () => {
        expect(typedText(markup)).not.toMatch(/\p{L}/u);
    });

    it('names the page and its tab title through i18n, in sentence case', () => {
        expect(appSource).not.toContain("'Model Evaluation'");
        expect(appSource).not.toContain("'Benchmark every installed classifier");
        expect(appSource).toContain("$_('model_eval.page_title'");
        expect(appSource).toContain("$_('page_subtitle.model_evaluation'");
        expect(english['model_eval.page_title']).toBe('Model evaluation');
    });

    it('says the page title once: the first panel is named for what it does', () => {
        expect(english['model_eval.start.title']).not.toBe(english['model_eval.page_title']);
        expect(markup.match(/model_eval\.page_title/g)).toBeNull();
    });

    it('names no option, action or column after a file or an internal', () => {
        const labels = Object.entries(english).filter(([key]) =>
            key.startsWith('model_eval.') && !key.endsWith('file_download') && !key.includes('.problem.'));
        for (const [key, value] of labels) {
            expect(value, key).not.toMatch(/\.jsonl?\b|\.csv\b|\/config\/|sweep|artifact|harness|top-1|top-3|p95|baseline|subprocess|NaN/i);
        }
    });

    it('explains each option on the page, never in a hover-only tooltip', () => {
        expect(markup).not.toMatch(/\stitle=/);
        expect(markup).toContain("$_('model_eval.start.each_photo_desc'");
        expect(markup).toContain("$_('model_eval.start.all_models_desc'");
    });

    it('states the download before it starts and asks first', () => {
        expect(source).toContain('missingModelDownload(');
        expect(source).toContain("$_('model_eval.confirm_download.title'");
        // One sentence states the download on the page and in the question, chosen by what is known.
        expect(source).toContain('downloadStatement(reading.estimate)');
        for (const key of ['download_size', 'download_size_partial', 'download_size_unknown', 'download_unknown', 'download_none']) {
            expect(source, key).toContain(`$_('model_eval.start.${key}'`);
        }
        expect(markup).toContain('{downloadLine(download)}');
        expect(source).toContain("message: `${downloadLine(download)} ${$_('model_eval.start.download_note')}`");
    });

    it('says the download may take a while, that models stay on disk, and where to remove them', () => {
        const note = english['model_eval.start.download_note'];
        expect(note).toMatch(/may take a while/);
        expect(note).toMatch(/stay on disk until you delete their files in Settings → Detection → Models/);
        expect(markup).toContain("$_('model_eval.start.download_note')");
        // A size is never promised for a model that has none.
        expect(english['model_eval.start.download_size_unknown']).not.toMatch(/\{size\}|MB|GB/);
        expect(english['model_eval.start.download_size_partial']).toMatch(/no known size/);
    });

    it('uses no symbol as a word: a result is written out', () => {
        expect(source).not.toMatch(/[✓✗⚠×]/u);
    });
});

describe('model evaluation keeps the page quiet', () => {
    it('opens with one sentence and keeps the rest behind "How this works"', () => {
        const start = markup.slice(markup.indexOf('model-eval-start-title'), markup.indexOf('model-eval-results-title'));
        const beforeDisclosure = start.slice(0, start.indexOf('{#if howOpen}'));
        expect(beforeDisclosure.match(/<p\b/g)).toHaveLength(1);
        expect(beforeDisclosure).toContain("$_('model_eval.start.what')");
        for (const key of ['how.photos', 'how.cost', 'how.limit', 'how.checks']) {
            expect(start.slice(start.indexOf('{#if howOpen}')), key).toContain(`$_('model_eval.${key}')`);
        }
        expect(english['model_eval.start.what'].split('. ')).toHaveLength(1);
        expect(english['model_eval.checks.body'].split('. ')).toHaveLength(1);
    });

    it('explains the columns once, in a list anyone can open, and leaves one line under the table', () => {
        expect(markup).toContain('{#each columnMeanings as column}');
        expect(markup).not.toContain('model_eval.results.key');
        expect(markup.match(/model_eval\.results\.columns_hint/g)).toHaveLength(1);
        expect(english['model_eval.results.columns_hint']).toMatch(/How this works/);
    });

    it('discloses with plain words and a chevron: no chip, no dashed box', () => {
        expect(source).not.toContain('AdvancedSection');
        expect(markup).not.toMatch(/border-dashed/);
        expect(english['model_eval.start.options_show']).toBe('Show evaluation options');
        expect(markup.match(/\{@render disclosure\(/g)).toHaveLength(2);
        const control = openingTags(markup.slice(markup.indexOf('{#snippet disclosure')), 'button')[0];
        expect(control).toContain('aria-expanded={open}');
        expect(control).toContain('aria-controls={controls}');
        expect(markup).toContain("open ? 'rotate-180' : ''");
    });

    it('shows a model by the name Settings uses, never its identifier beneath', () => {
        const name = markup.slice(markup.indexOf('{#snippet modelName'), markup.indexOf('{#snippet cellValue'));
        expect(name).not.toContain('font-mono');
        expect(name).not.toContain('row.id');
        // The one monospace string left is the server folder beside the downloads.
        expect(markup.match(/font-mono/g)).toHaveLength(1);
    });

    it('writes every note the same quiet way, with amber only where the owner should look', () => {
        expect(markup.match(/\{@render noteLines\(/g)).toHaveLength(2);
        expect(source).toContain("critical: 'attention', warning: 'attention', info: 'neutral'");
        expect(english['model_eval.warning.severity.critical']).toBe('Needs a look');
        // Red is for a request that failed and a provider that did not run, not for a flagged model.
        expect(markup.match(/bg-red-50/g)).toHaveLength(1);
        expect(markup.slice(markup.indexOf('data-model-eval-stopped') - 200, markup.indexOf('data-model-eval-stopped'))).not.toContain('red');
    });

    it('writes a provider result in ordinary ink with a status dot, so it does not read as a link', () => {
        expect(source).not.toContain('TONE_TEXT');
        expect(source).not.toMatch(/text-success-\d|text-attention-\d/);
        expect(source).toContain("pass: 'bg-success-500'");
        expect(source).toContain("attention: 'bg-attention-500'");
        expect(markup).toContain("{TONE_DOT[cell.tone ?? 'neutral']}");
    });

    it('puts Delete in the Results header as a quiet action that still asks first', () => {
        const header = markup.slice(markup.indexOf('model-eval-results-title') - 400, markup.indexOf('<div class="mt-2 space-y-4">'));
        expect(header).toContain("$_('model_eval.results.delete'");
        expect(header).toMatch(/class="btn btn-ghost [^"]*text-red-700/);
        expect(header).toContain('justify-between');
        expect(markup).not.toContain('btn btn-danger"\n                        disabled={selectedIsRunning}');
        expect(source).toContain("$_('model_eval.confirm_delete.confirm'");
    });
});

describe('model evaluation is built from the shared kit', () => {
    it('draws every panel with the kit card, not hand-rolled chrome', () => {
        expect(markup).not.toMatch(/rounded-xl bg-white/);
        expect(markup).not.toMatch(/\bbg-white\b|dark:bg-slate-800\b/);
        const sections = openingTags(markup, 'section');
        expect(sections).toHaveLength(3);
        for (const section of sections) expect(section, section.slice(0, 80)).toMatch(/\bcard-base\b/);
    });

    it('uses the kit switch for its options instead of a raw checkbox', () => {
        expect(markup).not.toContain('type="checkbox"');
        expect(markup.match(/<SettingsToggle/g)).toHaveLength(2);
    });

    it('uses kit buttons at the touch-target floor', () => {
        const buttons = openingTags(markup, 'button');
        expect(buttons.length).toBeGreaterThanOrEqual(5);
        for (const button of buttons) expect(button, button.slice(0, 80)).toMatch(/class="btn btn-(primary|secondary|ghost|danger)\b/);
        expect(markup).not.toMatch(/\bmin-h-(?!11\b)\d+\b[^"]*\bbtn\b/);
    });

    it('keeps the closed palette and the constrained scale', () => {
        expect(source).not.toMatch(/\bgray-\d|\bblue-\d|\bamber-\d|\baccent-\d/);
        expect(markup).not.toMatch(/-\[[^\]]+\]/);
    });

    it('heads the page sections one level under the page title', () => {
        expect(markup).not.toContain('<h1');
        expect(markup.match(/<h2/g)).toHaveLength(3);
        expect(markup).not.toMatch(/<h4/);
    });
});

describe('model evaluation states what it measured, and nothing else', () => {
    it('decides loading, failed, empty and list in one tested place', () => {
        expect(source).toContain('historyPane({');
        for (const pane of ['loading', 'empty']) expect(markup).toContain(`pane === '${pane}'`);
        // A failed first read shows the problem alone: no chooser, and no claim of an empty list.
        expect(markup).toContain("{:else if pane !== 'failed'}");
    });

    it('reports a problem with its cause and next step, never the raw server phrase', () => {
        expect(source).toContain('evaluationProblem(');
        expect(source).not.toMatch(/error = \(e as Error\)\.message/);
        expect(source).not.toMatch(/\.catch\(\(\) => null\)/);
        for (const cause of ['already_running', 'signed_out', 'gone', 'server_fault', 'unreachable', 'refused']) {
            const copy = english[`model_eval.problem.cause.${cause}`];
            expect(copy, cause).toBeTruthy();
            // A cause is a sentence and a next step.
            expect(copy.split('. ').length, cause).toBeGreaterThanOrEqual(2);
        }
    });

    it('never renders what the server or an exception said, on this page or the two that share its runs', () => {
        // The run's failure, a model's check row, a skipped model and a warning are each read by code.
        expect(source).toContain('stopCause(selectedRun?.error_code)');
        expect(source).toContain('checkRowProblem(row.error)');
        expect(source).toContain('skipReason(skipped.reason)');
        for (const leak of ['selectedRun.error}', 'selectedRun.error ', 'text: row.error', 'warning.message', '.detail', 'issue.message', 'cause.message']) {
            expect(source, leak).not.toContain(leak);
        }
        expect(Object.keys(english).filter((key) => key.startsWith('model_eval.') && /\{detail\}|\{error\}|\{message\}/.test(english[key]))).toEqual([]);
        for (const [name, other] of [['DetectionSettings', detectionSource], ['ModelStep', wizardSource]] as const) {
            expect(other, name).toContain('stopCause(summary');
            expect(other, name).not.toMatch(/summary\??\.error\b(?!_code)/);
        }
    });

    it('has a sentence with a next step for every reason the server can give, and for one it cannot name', () => {
        const reasons = [
            ...['no_models', 'models_not_ready', 'finder_needs_provider_check', 'no_test_birds', 'no_test_photos', 'network', 'unexpected'].map((code) => `stopped.${code}`),
            ...['activation_failed', 'provider_sweep_failed', 'unknown'].map((code) => `checks.row.${code}`),
            ...['activation_failed', 'reload_failed', 'other'].map((code) => `skipped.${code}`),
            ...['provider_validation_failed', 'provider_validation_partial', 'unknown'].map((code) => `warning.${code}`)
        ];
        for (const reason of reasons) {
            const copy = english[`model_eval.${reason}`];
            expect(copy, reason).toBeTruthy();
            expect(copy.split(/[.;] /).length, reason).toBeGreaterThanOrEqual(2);
        }
    });

    it('takes the shape of a run from the generated API contract, not a hand-written copy', () => {
        expect(apiSource).toContain("components['schemas']['ModelEvalRunResponse']");
        expect(apiSource).not.toMatch(/interface ModelEval(RunSummary|ModelSummary|RunRow|ActiveStatus|Warning)\b/);
        expect(apiSource).not.toContain('available_artifacts?:');
    });

    it('offers Try again where a read failed', () => {
        expect(markup).toContain("$_('error.try_again'");
    });

    it('offers only the files the evaluation wrote', () => {
        expect(source).toContain('evaluationFiles(selectedRun?.available_artifacts)');
    });

    it('never shows placeholder accuracy or a latency spread for a compatibility-only run', () => {
        expect(source).toContain('isCompatibilityOnlyRun(selectedRun?.models)');
        expect(markup).toContain('{#if compatibilityOnly}');
    });

    it('marks a result in words as well as colour', () => {
        for (const kind of ['not_tested', 'did_not_load', 'unusable_output', 'reference', 'same', 'differs', 'ran']) {
            expect(english[`model_eval.checks.cell.${kind}`], kind).toBeTruthy();
        }
        for (const severity of ['critical', 'warning', 'info']) {
            expect(english[`model_eval.warning.severity.${severity}`], severity).toBeTruthy();
        }
    });
});

describe('model evaluation is operable and steady', () => {
    it('confirms the two actions that end or remove work, naming the effect', () => {
        expect(source).toContain("$_('model_eval.confirm_delete.confirm'");
        expect(source).toContain("$_('model_eval.confirm_stop.confirm'");
        expect(english['model_eval.confirm_delete.message']).toMatch(/cannot be undone/);
        // "Cancel" beside "Cancel run" misreads, so stopping is called stopping.
        expect(english['model_eval.confirm_stop.cancel']).toBe('Keep running');
    });

    it('explains in words why a running evaluation cannot be deleted', () => {
        expect(markup).toContain('disabled={selectedIsRunning}');
        expect(markup).toContain("$_('model_eval.results.delete_blocked'");
    });

    it('chooses a past evaluation with one kit select instead of a second list of rows', () => {
        expect(markup.match(/<select/g)).toHaveLength(1);
        expect(openingTags(markup, 'select')[0]).toContain('select-base');
        expect(markup).toContain("$_('model_eval.results.choose'");
    });

    it('lays a table out as labelled figures where its columns do not fit, by its own width', () => {
        expect(markup).toContain('@container');
        expect(markup).toContain('@2xl:hidden');
        expect(markup).toContain('hidden overflow-x-auto');
    });

    it('gives each scrolling table a name and a keyboard stop', () => {
        const scrollers = openingTags(markup, 'div').filter((tag) => tag.includes('overflow-x-auto'));
        expect(scrollers.length).toBeGreaterThanOrEqual(1);
        for (const scroller of scrollers) {
            expect(scroller).toContain('tabindex="0"');
            expect(scroller).toContain('role="group"');
            expect(scroller).toContain('aria-labelledby=');
        }
    });

    it('shows progress in the progress bar the rest of the app uses, with a name', () => {
        expect(markup).toContain('role="progressbar"');
        expect(markup).toContain("$_('model_eval.progress.label'");
    });

    it('holds its place while it reads, so nothing moves when the answer lands', () => {
        expect(markup).toContain('min-h-screen');
        expect(markup).toContain('motion-reduce:animate-none');
    });

    it('re-reads a finished evaluation once, not every two seconds', () => {
        expect(source).toContain('if (refreshInFlight) return;');
        expect(source).toContain('if (!document.hidden) void refresh();');
        expect(source).toContain('selectedRunId === list.active?.run_id');
    });

    it('answers the header’s Refresh like the other pages', () => {
        expect(routeOffersRefresh('model_evaluation')).toBe(true);
        expect(source).toContain('pageRefreshAction.register(');
    });
});

describe('the ways into model evaluation', () => {
    it('is linked from Settings, Detection, where models are chosen', () => {
        expect(detectionSettingsSource).toContain("$_('settings.detection.models_compare_link'");
        expect(settingsSource).toContain("onopenmodelevaluation={() => onNavigate?.('/diagnostics/model-eval')}");
    });

    it('is named plainly on the Debug tab and opened with a kit button', () => {
        expect(english['settings.debug.model_eval_title']).toBe('Model evaluation');
        expect(english['settings.debug.model_eval_open']).toBe('Open model evaluation');
        const opener = settingsSource.slice(settingsSource.indexOf('id="debug-model-evaluation"'));
        expect(openingTags(opener, 'button')[0]).toMatch(/class="btn btn-secondary\b/);
    });
});
