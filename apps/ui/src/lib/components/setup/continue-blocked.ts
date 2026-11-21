import type { WizardLoadStatus } from './WizardLoadState.svelte';

type Translate = (key: string, options: { default: string }) => string;

/**
 * Why a step that only waits on its settings cannot continue yet. Empty once they have loaded:
 * any further reason is the step's own to give.
 */
export function loadBlockedReason(state: WizardLoadStatus, translate: Translate): string {
    if (state === 'loading') {
        return translate('setup.blocked.loading', { default: 'Continue is available once the current settings have loaded.' });
    }
    if (state === 'error') {
        return translate('setup.blocked.load_failed', {
            default: 'The current settings could not be loaded, so nothing here can be saved. Use “Retry loading settings” above.'
        });
    }
    return '';
}
