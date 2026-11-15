import { describe, expect, it } from 'vitest';
import source from './ModelEvaluation.svelte?raw';
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
        // The disclosure's own `title` prop is its visible heading, not a tooltip.
        expect(markup.replace(/<AdvancedSection[^>]*>/, '')).not.toMatch(/\stitle=/);
        expect(markup).toContain("$_('model_eval.start.each_photo_desc'");
        expect(markup).toContain("$_('model_eval.start.all_models_desc'");
    });

    it('states the download before it starts and asks first', () => {
        expect(source).toContain('missingModelDownload(');
        expect(source).toContain("$_('model_eval.confirm_download.title'");
        expect(markup).toContain("$_('model_eval.start.download_size'");
    });

    it('uses no symbol as a word: a result is written out', () => {
        expect(source).not.toMatch(/[✓✗⚠×]/u);
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
            // A cause is a sentence and, unless the request was simply refused, a next step.
            if (cause !== 'refused') expect(copy.split('. ').length, cause).toBeGreaterThanOrEqual(2);
        }
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
