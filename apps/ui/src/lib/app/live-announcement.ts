import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';

/** What a screen reader is told when a bird arrives, in the page's language. */
export function newBirdAnnouncement(species: string, camera: string): string {
    return get(_)('common.live_new_bird', { default: 'New bird: {species} at {camera}', values: { species, camera } });
}
