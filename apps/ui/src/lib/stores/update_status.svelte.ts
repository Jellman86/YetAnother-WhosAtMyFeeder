import { fetchUpdateStatus, shouldShowUpdateBanner, type UpdateStatus } from '../api';
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';

// Dismissal is keyed on the version, so dismissing one update doesn't hide a later, newer one.
const DISMISSED_KEY = 'update-banner-dismissed-version';
export const UPDATE_STATUS_MAX_AGE_MS = 15 * 60 * 1000;

/**
 * Shared update-availability state so the update banner and the sidebar indicator stay in
 * sync from a single check, and a dismiss is honoured everywhere. An update prompt is never
 * critical, so a failed fetch just leaves the status null (nothing shown).
 */
export class UpdateStatusStore {
    status = $state<UpdateStatus | null>(null);
    dismissedVersion = $state<string | null>(null);
    private initialized = false;
    private loadPromise: Promise<void> | null = null;
    private pollTimer: ReturnType<typeof setInterval> | null = null;
    private readonly staleTracker = new StaleTracker(UPDATE_STATUS_MAX_AGE_MS);

    constructor() {
        refreshCoordinator.register(() => this.refreshIfStale());
    }

    async load(): Promise<void> {
        if (!this.initialized) {
            this.initialized = true;
            if (typeof localStorage !== 'undefined') {
                this.dismissedVersion = localStorage.getItem(DISMISSED_KEY);
            }
            this.startPolling();
        }
        await this.refreshIfStale();
    }

    async refreshIfStale(): Promise<void> {
        if (this.loadPromise) return this.loadPromise;
        if (!this.staleTracker.isStale()) return;

        this.loadPromise = (async () => {
            try {
                this.status = await fetchUpdateStatus();
                this.staleTracker.touch();
            } catch {
                // Keep a last-known status if one exists. A failed first check remains stale,
                // so navigation, visibility recovery, or the poll will retry automatically.
            } finally {
                this.loadPromise = null;
            }
        })();
        return this.loadPromise;
    }

    private startPolling(): void {
        if (this.pollTimer !== null || typeof window === 'undefined') return;
        this.pollTimer = window.setInterval(() => {
            if (document.hidden) return;
            void this.refreshIfStale();
        }, UPDATE_STATUS_MAX_AGE_MS);
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
