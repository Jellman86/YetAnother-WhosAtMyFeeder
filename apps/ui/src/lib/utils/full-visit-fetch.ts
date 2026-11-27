import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';
import { fullVisitStore } from '../stores/full-visit.svelte';
import { toastStore } from '../stores/toast.svelte';

/** Fetch a capture's full clip from the recordings and say how it went: ready, partial or failed. */
export async function fetchFullVisitAndReport(frigateEvent: string): Promise<void> {
    const t = get(_);
    try {
        const complete = await fullVisitStore.fetchFullVisit(frigateEvent);
        if (complete) {
            toastStore.success(t('video_player.full_visit_ready', { default: 'Full clip ready' }));
        } else {
            toastStore.warning(t('video_player.partial_visit_ready', { default: 'A partial clip is ready; retry shortly for the complete clip.' }));
        }
    } catch (error) {
        toastStore.error(error instanceof Error ? error.message : t('video_player.full_visit_failed', { default: 'Could not fetch the full clip' }));
    }
}
