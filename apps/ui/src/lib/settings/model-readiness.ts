import type { GardenIdentificationStatus } from '../api/garden';
import type { IdentificationStatus } from './identification-models';

/**
 * How ready a model is to do its work, in one vocabulary for every surface that says so:
 * Settings › Models, the wizard's review, About and Garden records.
 *
 * - `checking`: nothing has reported yet, so no state is claimed.
 * - `missing`: its files are not on this install.
 * - `queued`: its download has been started and has not finished.
 * - `validating`: installed, and being checked on this hardware.
 * - `failed`: installed, and it could not be loaded.
 * - `ready`: installed and waiting for work.
 * - `running`: doing its work now.
 */
export type ModelReadiness = 'checking' | 'missing' | 'queued' | 'validating' | 'failed' | 'ready' | 'running';

/** Work the page itself started on the model, which the model's own report does not show. */
export interface ModelActivity {
    downloading?: boolean;
    validating?: boolean;
}

/** The identification model's state, from the classifier's report worded by `identificationStatus`. */
export function identificationReadiness(status: IdentificationStatus, activity: ModelActivity = {}): ModelReadiness {
    if (status.kind === 'checking') return 'checking';
    if (status.kind === 'missing') return activity.downloading ? 'queued' : 'missing';
    if (activity.validating) return 'validating';
    if (status.kind === 'failed' || status.kind === 'unavailable') return 'failed';
    return status.kind === 'planned' ? 'ready' : 'running';
}

/** Garden's automatic check model (SpeciesNet's tracked-crop variant), which every new capture waits on. */
const GARDEN_CHECK_VARIANT = '4.0.3a';

/** The same state for Garden's automatic check model. A status that could not be read is never ready. */
export function gardenCheckReadiness(identification: GardenIdentificationStatus | null, activity: ModelActivity = {}): ModelReadiness {
    if (!identification) return 'checking';
    if (identification.error || !identification.catalogue_ready) return 'failed';
    const installed = identification.models.some((model) => model.variant === GARDEN_CHECK_VARIANT && model.installed);
    if (!installed) return activity.downloading ? 'queued' : 'missing';
    return identification.busy ? 'running' : 'ready';
}

/** The one thing to do about a state. Null while the app is working, or when nothing is needed. */
export function readinessAction(readiness: ModelReadiness): 'download' | 'recover' | null {
    if (readiness === 'missing') return 'download';
    if (readiness === 'failed') return 'recover';
    return null;
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
        case 'ready':
            return t('settings.models.readiness_ready', { default: 'Ready' });
        case 'running':
            return t('settings.models.readiness_running', { default: 'Running' });
    }
}
