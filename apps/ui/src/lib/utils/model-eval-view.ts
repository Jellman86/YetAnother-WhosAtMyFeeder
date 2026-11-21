import { ApiRequestError } from '../api/core';
import type { DeviceMatrix, ModelEvalActiveStatus, ModelEvalModelSummary, ModelEvalWarning } from '../api/model_eval';
import { isTransientRequestError } from './error-handling';

/**
 * What the Model evaluation page may say, decided apart from its markup so each rule is tested
 * on its own (layout-patterns.md 3): a read that failed is never an empty list, a problem names
 * its cause, and a provider that was not tested is never given a result.
 */

export type HistoryPane = 'loading' | 'failed' | 'empty' | 'list';

export function historyPane(read: { loaded: boolean; failed: boolean; count: number }): HistoryPane {
    if (!read.loaded) return read.failed ? 'failed' : 'loading';
    return read.count === 0 ? 'empty' : 'list';
}

const RUN_ID_TIME = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})$/;

/** An evaluation is named by when it started. Its identifier is that time in UTC. */
export function evaluationStarted(run: { run_id: string; started_at?: string | null }): Date | null {
    if (run.started_at) {
        const recorded = new Date(run.started_at);
        if (!Number.isNaN(recorded.getTime())) return recorded;
    }
    const match = RUN_ID_TIME.exec(run.run_id);
    if (!match) return null;
    const [year, month, day, hour, minute, second] = match.slice(1).map(Number);
    const fromId = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
    return Number.isNaN(fromId.getTime()) || fromId.getUTCMonth() !== month - 1 ? null : fromId;
}

const KNOWN_PHASES = ['starting', 'building_panel', 'fetching_images', 'downloading_models', 'device_sweep', 'evaluating'] as const;
type EvaluationPhase = (typeof KNOWN_PHASES)[number] | 'working';

export interface EvaluationProgress {
    phase: EvaluationPhase;
    done: number;
    total: number;
    /** Null while the total is not known, so the bar shows work without inventing a share. */
    percent: number | null;
}

export function evaluationProgress(active: Pick<ModelEvalActiveStatus, 'phase' | 'progress'>): EvaluationProgress {
    const phase = (KNOWN_PHASES as readonly string[]).includes(active.phase) ? (active.phase as EvaluationPhase) : 'working';
    const done = active.progress?.done ?? 0;
    const total = active.progress?.total ?? 0;
    const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
    return { phase, done, total, percent };
}

export type EvaluationAction = 'history' | 'results' | 'start' | 'stop' | 'delete' | 'download';
type ProblemCause = 'already_running' | 'signed_out' | 'gone' | 'server_fault' | 'unreachable' | 'refused';

/**
 * What failed and why, as two keys the page translates. It holds nothing the server or the
 * browser said: that text can name paths, addresses and internals, and belongs in the logs.
 */
export interface EvaluationProblem {
    what: EvaluationAction;
    cause: ProblemCause;
}

export function evaluationProblem(what: EvaluationAction, error: unknown): EvaluationProblem {
    if (error instanceof ApiRequestError) {
        if (error.status === 409 && what === 'start') return { what, cause: 'already_running' };
        if (error.status === 401 || error.status === 403) return { what, cause: 'signed_out' };
        if (error.status === 404) return { what, cause: 'gone' };
        return { what, cause: error.status >= 500 ? 'server_fault' : 'refused' };
    }
    if (isTransientRequestError(error) || error instanceof TypeError) return { what, cause: 'unreachable' };
    return { what, cause: 'refused' };
}

const STOP_CAUSES = ['no_models', 'models_not_ready', 'finder_needs_provider_check', 'no_test_birds', 'no_test_photos', 'network'] as const;
export type StopCause = (typeof STOP_CAUSES)[number] | 'unexpected';

/** Why an evaluation stopped early, from the server's code. An unknown code is the honest unknown. */
export function stopCause(code: string | null | undefined): StopCause | null {
    if (!code) return null;
    return (STOP_CAUSES as readonly string[]).includes(code) ? (code as StopCause) : 'unexpected';
}

export type CheckRowProblem = 'activation_failed' | 'provider_sweep_failed' | 'unknown';

/** Why a model has no provider checks. Older files put raised text after the code. */
export function checkRowProblem(error: string): CheckRowProblem {
    const code = error.split(':', 1)[0].trim();
    return code === 'activation_failed' || code === 'provider_sweep_failed' ? code : 'unknown';
}

export type SkipReason = 'activation_failed' | 'reload_failed' | 'other';

export function skipReason(reason: string): SkipReason {
    return reason === 'activation_failed' || reason === 'reload_failed' ? reason : 'other';
}

export type EvaluationFileLabel = 'summary' | 'mix_ups' | 'speed' | 'each_photo' | 'provider_checks';

// The order the page lists them in: the headline first, the diagnostic files after.
const FILE_LABELS: ReadonlyArray<[name: string, label: EvaluationFileLabel]> = [
    ['summary.json', 'summary'],
    ['confusions.csv', 'mix_ups'],
    ['runtime.json', 'speed'],
    ['results.jsonl', 'each_photo'],
    ['device_matrix.json', 'provider_checks']
];

export function evaluationFiles(available: readonly string[] | undefined): Array<{ name: string; label: EvaluationFileLabel }> {
    const written = new Set(available ?? []);
    return FILE_LABELS.filter(([name]) => written.has(name)).map(([name, label]) => ({ name, label }));
}

const PLAIN_WARNINGS: ReadonlySet<string> = new Set([
    'low_shared_core', 'provider_fallback_active', 'incomplete_install', 'inference_health_unhealthy', 'region_mismatch',
    'provider_validation_failed', 'provider_validation_partial'
]);

/**
 * The translated sentence for a model's warning, with the figures the row measured. A code the
 * page does not know has its own sentence: the server's message is never the copy.
 */
export function warningCopy(
    model: ModelEvalModelSummary,
    warning: ModelEvalWarning
): { key: string; values: Record<string, number> } {
    if (warning.code === 'latency_drift_high') {
        const measured = model.mean_latency_ms;
        const loaded = model.startup_benchmark_ms;
        if (measured == null || loaded == null) return { key: 'latency_drift_high_plain', values: {} };
        return { key: 'latency_drift_high', values: { measured: Math.round(measured), loaded: Math.round(loaded) } };
    }
    if (warning.code === 'partial_vocabulary') {
        const outside = model.species_outside_vocabulary;
        const total = model.panel_species;
        if (outside == null || total == null) return { key: 'partial_vocabulary_plain', values: {} };
        return { key: 'partial_vocabulary', values: { outside, total } };
    }
    if (warning.code === 'high_abstention') {
        return { key: 'high_abstention', values: { share: Math.round((model.abstention_rate ?? 0) * 100) } };
    }
    return { key: PLAIN_WARNINGS.has(warning.code) ? warning.code : 'unknown', values: {} };
}

type MatrixRow = DeviceMatrix['models'][string] | NonNullable<DeviceMatrix['crop_detectors']>[string];

export type ProviderCheck =
    | { kind: 'not_tested' }
    | { kind: 'did_not_load' }
    | { kind: 'unusable_output' }
    | { kind: 'reference'; photos: number }
    | { kind: 'same'; photos: number; boxes: boolean }
    | { kind: 'differs'; same: number; photos: number; boxes: boolean }
    | { kind: 'ran' };

/** One cell of the provider checks: how a provider's answers compared with the CPU's. */
export function providerCheck(row: MatrixRow | undefined, provider: string): ProviderCheck {
    if (!row || row.error) return { kind: 'not_tested' };
    const entry = row.providers?.[provider] ?? row.devices?.[provider];
    if (!entry) return { kind: 'not_tested' };
    if (!entry.compiles) return { kind: 'did_not_load' };
    if (entry.finite === false) return { kind: 'unusable_output' };
    if (entry.baseline || provider === row.baseline_provider || provider === 'CPU') {
        return { kind: 'reference', photos: entry.images_evaluated ?? 0 };
    }
    const photos = entry.images_compared ?? 0;
    const boxes = row.comparison_kind === 'crop_box';
    if (entry.matches_cpu && photos) return { kind: 'same', photos, boxes };
    const rate = boxes ? entry.detection_match_rate : entry.top1_match_rate;
    if (typeof rate === 'number' && photos) return { kind: 'differs', same: Math.round(rate * photos), photos, boxes };
    return { kind: 'ran' };
}

const DOWNLOADED_KINDS: ReadonlySet<string> = new Set(['classifier', 'crop_detector']);

export interface DownloadEstimate {
    /** Bird models and bird finders that are not installed and ready. */
    count: number;
    /** The total of the sizes the registry knows. */
    megabytes: number;
    /** How many of them the registry gives no size for, so they are named apart from the total. */
    unknownSizes: number;
}

/** What "check every model" fetches first: the bird models and bird finders not yet installed. */
export function missingModelDownload(
    registry: ReadonlyArray<{ id: string; file_size_mb: number; artifact_kind?: string }>,
    installed: ReadonlyArray<{ id: string; ready?: boolean }>
): DownloadEstimate {
    const ready = new Set(installed.filter((model) => model.ready).map((model) => model.id));
    const missing = registry.filter((model) => DOWNLOADED_KINDS.has(model.artifact_kind ?? 'classifier') && !ready.has(model.id));
    const sized = missing.filter((model) => model.file_size_mb > 0);
    const megabytes = sized.reduce((sum, model) => sum + model.file_size_mb, 0);
    return { count: missing.length, megabytes: Math.round(megabytes * 10) / 10, unknownSizes: missing.length - sized.length };
}

export type DownloadStatement = 'nothing' | 'sized' | 'partly_sized' | 'unsized';

/** Which sentence states the download. A size is stated only for the models that have one. */
export function downloadStatement(estimate: DownloadEstimate): DownloadStatement {
    if (estimate.count === 0) return 'nothing';
    if (estimate.unknownSizes === 0) return 'sized';
    return estimate.unknownSizes < estimate.count ? 'partly_sized' : 'unsized';
}
