import type { ClassifierStatus } from '../api/classifier';
import type { GardenIdentificationStatus } from '../api/garden';
import { identificationStatus, type IdentificationStatus } from './identification-models';

/**
 * How ready a model is to do its work, in one vocabulary for every surface that says so:
 * Settings › Models, the wizard's review, About and Garden records.
 *
 * - `checking`: nothing has reported yet, so no state is claimed.
 * - `missing`: its files are not on this install.
 * - `queued`: its download has been started and has not finished.
 * - `validating`: installed, and being checked on this hardware.
 * - `failed`: installed, and it could not be loaded.
 * - `loading`: installed, and being loaded; nothing does its work until that ends.
 * - `ready`: installed and waiting for work.
 * - `running`: doing its work now, on evidence that it is.
 * - `unknown`: a report arrived and gave no evidence either way, so no state is claimed.
 *
 * The server's `identification_readiness` uses the same words for the states it can measure, and
 * both are held to `backend/tests/fixtures/model_readiness_cases.json`.
 */
export type ModelReadiness = 'checking' | 'missing' | 'queued' | 'validating' | 'failed' | 'loading' | 'ready' | 'running' | 'unknown';

/**
 * Work this app started on a model, which the model's own report does not show. Every surface
 * reads it from the one store (`stores/model_activity.svelte.ts`), so a download started on the
 * Models page is a download on About, in the wizard's review and on a Garden record too.
 */
export type ActivityPhase = 'downloading' | 'validating';

/** The phase a guided install is in, from the stage that is running now. */
export function activityPhase(stages: ReadonlyArray<{ id: string; state: string }>): ActivityPhase | null {
    const running = stages.find((stage) => stage.state === 'running');
    if (!running) return null;
    return running.id === 'download' ? 'downloading' : 'validating';
}

/** The identification model's state, from the classifier's report worded by `identificationStatus`. */
export function identificationReadiness(status: IdentificationStatus, phase: ActivityPhase | null = null): ModelReadiness {
    if (status.kind === 'checking') return 'checking';
    // A download replaces whatever files are here, so it is the state while it runs.
    if (phase === 'downloading') return 'queued';
    if (status.kind === 'missing') return 'missing';
    if (phase === 'validating') return 'validating';
    if (status.kind === 'failed' || status.kind === 'unavailable') return 'failed';
    if (status.kind === 'loading' || status.kind === 'unknown') return status.kind;
    return status.kind === 'planned' ? 'ready' : 'running';
}

/** The same reading straight from a classifier report: what every surface but the sentence uses. */
export function classifierReadiness(status: ClassifierStatus | null, phase: ActivityPhase | null = null): ModelReadiness {
    return identificationReadiness(identificationStatus(status), phase);
}

/** The model a classifier report is about: the key its activity is recorded under. */
export function reportedModelId(status: ClassifierStatus | null): string | null {
    return status?.effective_model_id ?? status?.active_model_id ?? null;
}

/** Garden's automatic check model (SpeciesNet's tracked-crop variant), which every new capture waits on. */
const GARDEN_CHECK_VARIANT = '4.0.3a';

/**
 * What stands between a Garden capture and its automatic check.
 *
 * The model has a readiness like any other. Two things are not the model's state and are kept as
 * what was measured, each with its own way out: Garden's species data could not be read, and
 * Garden's service stopped with an error of its own (a worker that would not stop). Neither is a
 * model that "could not load", and neither is fixed by setting a model up.
 */
export type GardenCheckState =
    | { kind: 'model'; readiness: ModelReadiness }
    | { kind: 'blocked'; blocker: 'species_data'; detail: null }
    | { kind: 'blocked'; blocker: 'service'; detail: string };

export function gardenCheckState(identification: GardenIdentificationStatus | null, phase: ActivityPhase | null = null): GardenCheckState {
    if (!identification) return { kind: 'model', readiness: 'checking' };
    const error = identification.error?.trim();
    if (error) return { kind: 'blocked', blocker: 'service', detail: error };
    if (!identification.catalogue_ready) return { kind: 'blocked', blocker: 'species_data', detail: null };
    if (phase === 'downloading') return { kind: 'model', readiness: 'queued' };
    const installed = identification.models.some((model) => model.variant === GARDEN_CHECK_VARIANT && model.installed);
    if (!installed) return { kind: 'model', readiness: 'missing' };
    return { kind: 'model', readiness: identification.busy ? 'running' : 'ready' };
}

/** Whether Garden's check can run on a capture now: its model is here and nothing blocks it. */
export function gardenCheckAvailable(state: GardenCheckState): boolean {
    return state.kind === 'model' && (state.readiness === 'ready' || state.readiness === 'running');
}

/** Whether setting the check model up is what clears the wait: only when the model is what is missing. */
export function gardenCheckNeedsSetup(state: GardenCheckState | null): boolean {
    return state?.kind === 'model' && state.readiness === 'missing';
}

/** How far the read of Garden's status has got: still going, failed, or answered. */
export type GardenStatusRead = 'loading' | 'failed' | 'read';

/**
 * Whether an owner can confirm a waiting capture by hand, and what to tell them.
 *
 * Manual override is the way round the automatic check, so it waits only while that check is on
 * its way: its status is being read, or its model is downloading or being checked. It opens as
 * soon as the check can run, and also once the check is known not to be able to run here (the
 * model is not here, could not load, or Garden itself is blocked), because an owner offline, or
 * with a download that keeps failing, must still be able to decide. Then the dialog says so.
 * After a read that failed, nothing was measured: it stays closed and offers a retry. Dismissal is
 * a reversible action and is never gated on any of this.
 */
export type ManualOverride =
    | { state: 'open'; note: 'by_hand' | null }
    | { state: 'closed'; cause: 'reading' | 'unread' | 'working' };

const ON_ITS_WAY: ReadonlySet<ModelReadiness> = new Set(['checking', 'queued', 'validating', 'loading']);

export function gardenManualOverride(read: GardenStatusRead, check: GardenCheckState): ManualOverride {
    if (read === 'loading') return { state: 'closed', cause: 'reading' };
    if (read === 'failed') return { state: 'closed', cause: 'unread' };
    if (gardenCheckAvailable(check)) return { state: 'open', note: null };
    if (check.kind === 'model' && ON_ITS_WAY.has(check.readiness)) return { state: 'closed', cause: 'working' };
    return { state: 'open', note: 'by_hand' };
}

/** The one thing to do about a state. Null while the app is working, or when nothing is needed. */
export function readinessAction(readiness: ModelReadiness): 'download' | 'recover' | null {
    if (readiness === 'missing') return 'download';
    if (readiness === 'failed') return 'recover';
    return null;
}

/**
 * How the chosen model is recovered, so that it always has a primary action when it needs one.
 * A model that is not here is downloaded. One that is here and could not be loaded has its files
 * fetched again when they are incomplete and can be fetched; otherwise it is checked on this
 * hardware and loaded again, which is also the only recovery a bundled model has.
 */
export type ChosenRecovery = 'download' | 'repair_download' | 'revalidate';

export function chosenRecovery(readiness: ModelReadiness, files: { installed: boolean; complete: boolean; bundled: boolean }): ChosenRecovery | null {
    const action = readinessAction(readiness);
    if (action === null) return null;
    if (!files.installed) return 'download';
    if (!files.complete && !files.bundled) return 'repair_download';
    return 'revalidate';
}

/**
 * Whether a model's setup button is the page's primary action. While the chosen model needs a
 * download or a recovery, that is the one primary action and every other model's is secondary, so
 * the shortest way back to a working feeder is the only loud button on the page.
 */
export function setupEmphasis(chosen: ModelReadiness, subject: 'chosen' | 'other'): 'primary' | 'secondary' {
    if (readinessAction(chosen) === null) return 'primary';
    return subject === 'chosen' ? 'primary' : 'secondary';
}

/**
 * The tone a state is shown in. Green is for evidence the model can do its work; amber for a state
 * a person has to act on; everything the app is doing or could not read stays neutral.
 */
export function readinessTone(readiness: ModelReadiness): 'ok' | 'attention' | 'neutral' {
    if (readiness === 'ready' || readiness === 'running') return 'ok';
    return readinessAction(readiness) !== null ? 'attention' : 'neutral';
}

type Translate = (key: string, options?: { default?: string }) => string;

/** The word for a state, the same wherever a model's state is printed. */
export function readinessLabel(readiness: ModelReadiness, t: Translate): string {
    switch (readiness) {
        case 'checking':
            return t('settings.models.readiness_checking', { default: 'Checking…' });
        case 'missing':
            return t('settings.models.readiness_missing', { default: 'Needs a download' });
        case 'queued':
            return t('settings.models.readiness_queued', { default: 'Downloading' });
        case 'validating':
            return t('settings.models.readiness_validating', { default: 'Being checked on this hardware' });
        case 'failed':
            return t('settings.models.readiness_failed', { default: 'Could not load' });
        case 'loading':
            return t('settings.models.readiness_loading', { default: 'Loading' });
        case 'ready':
            return t('settings.models.readiness_ready', { default: 'Ready' });
        case 'running':
            return t('settings.models.readiness_running', { default: 'Running' });
        case 'unknown':
            return t('settings.models.readiness_unknown', { default: 'Not reported' });
    }
}
