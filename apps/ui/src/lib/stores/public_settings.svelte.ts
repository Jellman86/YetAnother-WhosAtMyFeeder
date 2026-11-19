import { fetchPublicSettings, type PublicSettings } from '../api/settings';
import { visitGapMs } from '../utils/visit-grouping';
import { settingsStore } from './settings.svelte';

/**
 * The display preferences a viewer needs, read by guest and owner alike.
 *
 * `settingsStore` is fed by the owner-only `/api/settings`, so every read of the
 * form `settingsStore.settings?.x ?? fallback` silently gave a guest the fallback
 * rather than what the owner configured. Reads that shape what a visitor sees
 * belong here instead.
 */
class PublicSettingsStore {
    settings = $state<PublicSettings | null>(null);
    private request: Promise<void> | null = null;

    async load(): Promise<void> {
        // One flight at a time; several components ask for this on the same paint.
        if (this.request) return this.request;
        this.request = (async () => {
            try {
                this.settings = await fetchPublicSettings();
            } catch {
                // A viewer who cannot read the projection keeps the built-in defaults
                // rather than an empty interface.
                this.settings = null;
            } finally {
                this.request = null;
            }
        })();
        return this.request;
    }
}

export const publicSettingsStore = new PublicSettingsStore();

/**
 * The visit gap every grouping in the SPA uses. The owner's own settings come first, so a saved gap
 * applies at once; a guest reads it from the projection; both fall back to the default minute.
 */
export function savedVisitGapMs(): number {
    return visitGapMs(settingsStore.settings?.visit_gap_seconds ?? publicSettingsStore.settings?.visit_gap_seconds);
}
