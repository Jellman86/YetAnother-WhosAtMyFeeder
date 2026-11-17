import { getModelEvalDeviceMatrix, getModelEvalRun, listModelEvalRuns, startModelEvalRun, type DeviceMatrix } from '../api/model_eval';
import { stopCause } from '../utils/model-eval-view';

/** Why a device check has no result, in a form the page words for the reader. */
export type DeviceCheckProblem =
    | { kind: 'stopped'; cause: string }
    | { kind: 'results_unavailable' }
    | { kind: 'message'; text: string };

const POLL_MS = 2000;

/**
 * One device compatibility check for Identifying birds. The model list starts one for a single
 * bird finder and Hardware starts one for every installed model, so both read the same check and
 * its dialog: whichever started it, neither can start a second while it runs.
 */
export class DeviceCheck {
    running = $state(false);
    allModels = $state(false);
    phase = $state<string | null>(null);
    progress = $state<{ done: number; total: number; label: string } | null>(null);
    matrix = $state.raw<DeviceMatrix | null>(null);
    problem = $state.raw<DeviceCheckProblem | null>(null);
    runtimeRefreshFailed = $state(false);
    dialogOpen = $state(false);
    dialogRunId = $state(0);

    #poll: ReturnType<typeof setInterval> | null = null;
    #pollInFlight = false;
    // Identifies the newest check so a superseded poll's late reply is ignored.
    #check = 0;
    // Models the latest check covered, so Retry repeats the same scope. Empty means every installed model.
    #modelIds: string[] = [];
    #settle: () => void = () => {};
    readonly #refreshRuntime: () => Promise<boolean>;

    /**
     * `refreshRuntime` reads the live runtime back from the workers: a check can move classification
     * onto a newly validated provider, so the runtime shown afterwards must be read, not assumed.
     */
    constructor(refreshRuntime: () => Promise<boolean> = async () => true) {
        this.#refreshRuntime = refreshRuntime;
    }

    async #refreshAfterCheck(): Promise<void> {
        this.runtimeRefreshFailed = !(await this.#refreshRuntime());
    }

    #stopPolling(): void {
        if (this.#poll) clearInterval(this.#poll);
        this.#poll = null;
    }

    /** Starts a check and resolves once it has finished, failed or been superseded. */
    async run(modelIds: string[] = []): Promise<void> {
        this.#stopPolling();
        this.#settle();
        const settled = new Promise<void>((resolve) => (this.#settle = resolve));
        this.#modelIds = modelIds;
        this.dialogOpen = true;
        this.dialogRunId += 1;
        this.runtimeRefreshFailed = false;
        this.problem = null;
        this.matrix = null;
        this.running = true;
        this.phase = 'starting';
        this.progress = null;
        const check = ++this.#check;
        let seenActive = false;
        try {
            const { run_id } = await startModelEvalRun({
                sweep_devices: true,
                compat_only: true,
                sweep_all_models: modelIds.length === 0 && this.allModels,
                model_ids: modelIds
            });
            if (check !== this.#check) return settled;
            this.#poll = setInterval(async () => {
                if (this.#pollInFlight || document.hidden) return;
                this.#pollInFlight = true;
                try {
                    const list = await listModelEvalRuns();
                    if (check !== this.#check) return;
                    if (list.active && list.active.run_id === run_id) {
                        seenActive = true;
                        this.phase = list.active.phase ?? null;
                        this.progress = list.active.progress ?? null;
                        return;
                    }
                    if (!seenActive) {
                        const summary = await getModelEvalRun(run_id).catch(() => null);
                        if (check !== this.#check) return;
                        const stopped = stopCause(summary?.error_code);
                        if (!summary?.finished_at && !stopped) return;
                        if (stopped) {
                            this.#stopPolling();
                            this.running = false;
                            this.phase = 'error';
                            this.problem = { kind: 'stopped', cause: stopped };
                            this.dialogRunId += 1;
                            await this.#refreshAfterCheck();
                            this.#settle();
                            return;
                        }
                    }
                    this.#stopPolling();
                    this.running = false;
                    this.phase = 'complete';
                    try {
                        const matrix = await getModelEvalDeviceMatrix(run_id);
                        if (check !== this.#check) return;
                        if (matrix) this.matrix = matrix;
                        else this.problem = { kind: 'results_unavailable' };
                    } catch (error) {
                        if (check !== this.#check) return;
                        this.matrix = null;
                        this.problem = error instanceof Error && error.message.trim()
                            ? { kind: 'message', text: error.message }
                            : { kind: 'results_unavailable' };
                    }
                    this.dialogRunId += 1;
                    if (check === this.#check) await this.#refreshAfterCheck();
                    this.#settle();
                } catch {
                    /* transient: keep polling */
                } finally {
                    this.#pollInFlight = false;
                }
            }, POLL_MS);
        } catch (error) {
            if (check !== this.#check) return settled;
            this.running = false;
            this.problem = { kind: 'message', text: (error as Error).message };
            this.#settle();
        }
        return settled;
    }

    /** Runs the last check again, over the same models. */
    retry(): Promise<void> {
        return this.run(this.#modelIds);
    }

    /** Stops listening for a check's result, when the page that shows it goes away. */
    dispose(): void {
        this.#check += 1;
        this.#stopPolling();
        this.#settle();
    }
}

type Translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }) => string;

/** The reason a check has no result, in the reader's words. */
export function deviceCheckProblemText(problem: DeviceCheckProblem, translate: Translate): string {
    if (problem.kind === 'stopped') return translate(`model_eval.stopped.${problem.cause}`);
    if (problem.kind === 'message') return problem.text;
    return translate('settings.detection.compat_results_unavailable', { default: 'Compatibility results could not be loaded. Please retry.' });
}
