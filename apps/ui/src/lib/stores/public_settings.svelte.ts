import { fetchPublicSettings, type PublicSettings } from '../api/settings';

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
