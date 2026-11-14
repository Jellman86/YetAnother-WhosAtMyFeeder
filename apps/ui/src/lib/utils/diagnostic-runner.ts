import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';

/**
 * Shared types and runner for guided diagnostics rendered by DiagnosticDialog.
 * See docs/standards/diagnostics-and-dialogs.md — one stage per *independently
 * verified* check, and a stage only turns green when its check actually passed.
 */
// `warning` is an honest "it ran, but with a caveat" outcome (e.g. a device that
// produces results differing from the CPU baseline) — passing would overstate it,
// failing would understate it.
export type DiagnosticStageState = 'pending' | 'running' | 'passed' | 'failed' | 'skipped' | 'warning';

export interface DiagnosticStage {
    id: string;
    label: string;
    state: DiagnosticStageState;
    message: string;
}

export interface DiagnosticResult {
    ok: boolean;
    message: string;
    // Optional secondary line (e.g. a provider "retry after" hint).
    hint?: string;
}

export interface DiagnosticStep {
    id: string;
    label: string;
    /** Runs the real check. `status: 'ok'` marks the stage passed; anything else fails it. */
    run: () => Promise<{ status: string; message: string }>;
}

export interface DiagnosticRunOptions {
    /**
     * The checks do not depend on each other, so a failure must not stop the next one: marking
     * it "not run because an earlier step failed" would claim a dependency that is not there.
     */
    independent?: boolean;
}

/**
 * Run ordered checks one at a time, publishing the evolving stage list through
 * `apply` after every transition. Stops at the first failure and marks the rest
 * skipped, unless the checks are independent. Never fabricates a pass — each stage
 * reflects its own check's result.
 */
export async function runSequentialDiagnostic(
    steps: DiagnosticStep[],
    apply: (stages: DiagnosticStage[]) => void,
    options: DiagnosticRunOptions = {}
): Promise<DiagnosticResult> {
    const runningMessage = get(_)('common.testing', { default: 'Checking…' });
    const skippedMessage = get(_)('diagnostics.step_skipped', {
        default: 'Not run because an earlier step failed.'
    });
    const genericFailure = get(_)('diagnostics.step_failed', { default: 'The check did not pass.' });

    const stages: DiagnosticStage[] = steps.map((step) => ({
        id: step.id,
        label: step.label,
        state: 'pending',
        message: ''
    }));
    apply([...stages]);

    let failed = false;
    let finalMessage = '';
    for (let i = 0; i < steps.length; i++) {
        if (failed && !options.independent) {
            stages[i] = { ...stages[i], state: 'skipped', message: skippedMessage };
            apply([...stages]);
            continue;
        }
        stages[i] = { ...stages[i], state: 'running', message: runningMessage };
        apply([...stages]);
        try {
            const result = await steps[i].run();
            const ok = result.status === 'ok';
            stages[i] = { ...stages[i], state: ok ? 'passed' : 'failed', message: result.message || genericFailure };
            finalMessage = result.message || finalMessage;
            if (!ok) failed = true;
        } catch (error) {
            finalMessage = error instanceof Error && error.message.trim() ? error.message : genericFailure;
            stages[i] = { ...stages[i], state: 'failed', message: finalMessage };
            failed = true;
        }
        apply([...stages]);
    }
    if (options.independent && failed) {
        // Each stage already carries its own failure; the summary says which ones, once.
        const failedLabels = stages.filter((stage) => stage.state === 'failed').map((stage) => stage.label);
        finalMessage = get(_)('common.checks_failed', {
            values: { failed: failedLabels.length, total: stages.length, labels: failedLabels.join(', ') },
            default: '{failed} of {total} checks did not pass: {labels}.'
        });
    }
    return { ok: !failed, message: finalMessage };
}

/**
 * The line under the checklist. Each row already states its own outcome, so a result that only
 * repeats a row is replaced by a count that names what did not pass: every outcome is on screen once.
 */
export function diagnosticHeadline(result: DiagnosticResult, stages: DiagnosticStage[]): string {
    const said = result.message.trim();
    const repeatsARow = stages.some((stage) => stage.state !== 'pending' && stage.message.trim() === said);
    if (!repeatsARow) return result.message;
    const translate = get(_);
    if (result.ok) {
        return stages.length === 1
            ? translate('common.check_passed', { default: 'The check passed.' })
            : translate('common.checks_passed', { values: { total: stages.length }, default: 'All {total} checks passed.' });
    }
    const unmet = stages.filter((stage) => stage.state === 'failed' || stage.state === 'warning').map((stage) => stage.label);
    return translate('common.checks_failed', {
        values: { failed: unmet.length, total: stages.length, labels: unmet.join(', ') },
        default: '{failed} of {total} checks did not pass: {labels}.'
    });
}
