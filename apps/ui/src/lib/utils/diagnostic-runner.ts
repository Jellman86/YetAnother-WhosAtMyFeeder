import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';

/**
 * Shared types and runner for guided diagnostics rendered by DiagnosticDialog.
 * See docs/standards/diagnostics-and-dialogs.md — one stage per *independently
 * verified* check, and a stage only turns green when its check actually passed.
 */
export type DiagnosticStageState = 'pending' | 'running' | 'passed' | 'failed' | 'skipped';

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

/**
 * Run ordered checks one at a time, publishing the evolving stage list through
 * `apply` after every transition. Stops at the first failure and marks the rest
 * skipped. Never fabricates a pass — each stage reflects its own check's result.
 */
export async function runSequentialDiagnostic(
    steps: DiagnosticStep[],
    apply: (stages: DiagnosticStage[]) => void
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
        if (failed) {
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
    return { ok: !failed, message: finalMessage };
}
