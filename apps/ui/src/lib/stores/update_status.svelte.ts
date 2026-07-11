import { fetchUpdateStatus, type UpdateStatus } from '../api';

/**
 * Shared update-availability state so the update banner and the sidebar indicator
 * stay in sync from a single check. An update prompt is never critical, so a failed
 * fetch just leaves the status null (nothing shown).
 */
class UpdateStatusStore {
    status = $state<UpdateStatus | null>(null);
    private loaded = false;

    async load(): Promise<void> {
        if (this.loaded) return;
        this.loaded = true;
        try {
            this.status = await fetchUpdateStatus();
        } catch {
            this.status = null;
        }
    }

    get updateAvailable(): boolean {
        return this.status?.update_available === true;
    }

    get latestVersion(): string | null {
        return this.status?.latest_version ?? null;
    }
}

export const updateStatusStore = new UpdateStatusStore();
