import type { SetupSectionState, SetupSectionStatus } from '../../api/setup';
import { readinessLabel, readinessTone, type ModelReadiness } from '../../settings/model-readiness';

type Translate = (key: string, options?: { default?: string }) => string;

/**
 * The badge beside a section on the review step. Where the server measured or the owner chose a
 * state, the badge names that state; "Configured" is left for sections with nothing more to say.
 * The model's word comes from the classifier's runtime report, as the model step's does: a model
 * that is only chosen says so, one that is absent needs a download, and one whose files are here
 * but could not be loaded is never called ready.
 */
export function reviewStatusLabel(section: SetupSectionState, t: Translate, model: ModelReadiness | null = null): string {
    if (modelFollowsReadiness(section, model)) return readinessLabel(model, t);
    switch (section.detail_code) {
        case 'account_auth_disabled':
            return t('setup.status.no_password', { default: 'No password' });
        case 'connection_connected':
            return t('setup.status.connected', { default: 'Connected' });
        case 'connection_unreachable':
            return t('setup.status.unreachable', { default: 'Not reachable' });
        case 'model_missing':
            return t('setup.status.model_missing', { default: 'Needs a download' });
        case 'model_failed':
            return t('setup.status.model_failed', { default: 'Could not load' });
        case 'model_loading':
            return t('setup.status.model_loading', { default: 'Loading' });
        case 'model_ready':
            return t('setup.status.model_ready', { default: 'Ready' });
        case 'model_running':
            return t('setup.status.model_running', { default: 'Running' });
        case 'model_selected':
        case 'model_fallback':
            return t('setup.status.model_chosen', { default: 'Chosen' });
    }
    if (section.status === 'ok') return t('setup.status.ok', { default: 'Configured' });
    if (section.status === 'attention') return t('setup.status.attention', { default: 'Needs attention' });
    return t('setup.status.optional', { default: 'Optional' });
}

/** The badge's tone. Green is for a measured state, so a model that was only chosen stays neutral. */
export function reviewStatusTone(section: SetupSectionState, model: ModelReadiness | null = null): SetupSectionStatus {
    if (modelFollowsReadiness(section, model)) {
        const tone = readinessTone(model);
        return tone === 'neutral' ? 'optional' : tone;
    }
    if (section.detail_code === 'model_selected' || section.detail_code === 'model_fallback') return 'optional';
    return section.status;
}

/**
 * The model row reads the classifier's own report, in the words the model step uses, whenever a
 * report arrived: one that carries no evidence reads "Not reported", never the server's "Chosen"
 * or an earlier "Running". The server's word is kept only when there is no report to read (`null`,
 * or still being fetched). A retired model or a detector saved as the classifier is the server's
 * finding and stays.
 */
function modelFollowsReadiness(section: SetupSectionState, model: ModelReadiness | null): model is ModelReadiness {
    if (section.id !== 'model' || model === null || model === 'checking') return false;
    return section.detail_code !== 'model_retired' && section.detail_code !== 'model_wrong_kind';
}
