import { fetchUpdateStatus, shouldShowUpdateBanner, type UpdateStatus } from '../api';

// Dismissal is keyed on the version, so dismissing one update doesn't hide a later, newer one.
const DISMISSED_KEY = 'update-banner-dismissed-version';

/**
 * Shared update-availability state so the update banner and the sidebar indicator stay in
 * sync from a single check, and a dismiss is honoured everywhere. An update prompt is never
 * critical, so a failed fetch just leaves the status null (nothing shown).
 */
class UpdateStatusStore {
    status = $state<UpdateStatus | null>(null);
    dismissedVersion = $state<string | null>(null);
    private loaded = false;

    async load(): Promise<void> {
        if (this.loaded) return;
        this.loaded = true;
        if (typeof localStorage !== 'undefined') {
            this.dismissedVersion = localStorage.getItem(DISMISSED_KEY);
        }
        try {
            this.status = await fetchUpdateStatus();
        } catch {
            this.status = null;
        }
    }

    dismiss(): void {
        const version = this.status?.latest_version;
        if (!version) return;
        this.dismissedVersion = version;
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem(DISMISSED_KEY, version);
        }
    }

    /** True when an update exists at all (drives the subtle, persistent sidebar indicator). */
    get updateAvailable(): boolean {
        return this.status?.update_available === true;
    }

    /** True when the dismissable banner should show (an update the user hasn't dismissed). */
    get shouldShowBanner(): boolean {
        return shouldShowUpdateBanner(this.status, this.dismissedVersion);
    }

    get latestVersion(): string | null {
        return this.status?.latest_version ?? null;
    }
}

export const updateStatusStore = new UpdateStatusStore();
