import type { SetupSectionState, SetupSectionStatus } from '../../api/setup';

type Translate = (key: string, options?: { default?: string }) => string;

/**
 * The badge beside a section on the review step. Where the server measured or the owner chose a
 * state, the badge names that state; "Configured" is left for sections with nothing more to say.
 * A model is "Installed" only when its files were found: one that is merely chosen says so, and
 * one that is absent needs a download, as the model step says of the same install.
 */
export function reviewStatusLabel(section: SetupSectionState, t: Translate): string {
    switch (section.detail_code) {
        case 'account_auth_disabled':
            return t('setup.status.no_password', { default: 'No password' });
        case 'connection_connected':
            return t('setup.status.connected', { default: 'Connected' });
        case 'connection_unreachable':
            return t('setup.status.unreachable', { default: 'Not reachable' });
        case 'model_missing':
            return t('setup.status.model_missing', { default: 'Needs a download' });
        case 'model_installed':
            return t('setup.status.model_installed', { default: 'Installed' });
        case 'model_selected':
        case 'model_fallback':
            return t('setup.status.model_chosen', { default: 'Chosen' });
    }
    if (section.status === 'ok') return t('setup.status.ok', { default: 'Configured' });
    if (section.status === 'attention') return t('setup.status.attention', { default: 'Needs attention' });
    return t('setup.status.optional', { default: 'Optional' });
}

/** The badge's tone. Green is for a measured state, so a model that was only chosen stays neutral. */
export function reviewStatusTone(section: SetupSectionState): SetupSectionStatus {
    if (section.detail_code === 'model_selected' || section.detail_code === 'model_fallback') return 'optional';
    return section.status;
}
