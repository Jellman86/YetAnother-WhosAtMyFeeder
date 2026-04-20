import { getBackfillStatus, type BackfillJobStatus } from '../api/backfill';
import { authStore } from './auth.svelte';
import { jobProgressStore } from './job_progress.svelte';
import { syncBackfillJobProgress, type BackfillKind } from '../backfill/job-progress';
import type { ScopedBackfillProgress } from '../backfill/progress';

interface BackfillStatusStoreOptions {
    fetchBackfillStatus?: (kind: BackfillKind) => Promise<BackfillJobStatus | null>;
    /** @deprecated use activePollIntervalMs / idlePollIntervalMs instead */
    pollIntervalMs?: number;
    activePollIntervalMs?: number;
    idlePollIntervalMs?: number;
    hasOwnerAccess?: () => boolean;
}

export class BackfillStatusStore {
    private readonly fetcher: (kind: BackfillKind) => Promise<BackfillJobStatus | null>;
    private readonly activePollIntervalMs: number;
    private readonly idlePollIntervalMs: number;
    private readonly hasOwnerAccess: () => boolean;
    private refCount = 0;
    private pollTimer: ReturnType<typeof setTimeout> | null = null;
    private currentIntervalMs: number | null = null;
    private lastDetectionsStatus: BackfillJobStatus | null = null;
    private lastWeatherStatus: BackfillJobStatus | null = null;
    private detectionsScoped = $state<ScopedBackfillProgress>({ jobId: null, total: 0 });
    private weatherScoped = $state<ScopedBackfillProgress>({ jobId: null, total: 0 });

    constructor(options: BackfillStatusStoreOptions = {}) {
        this.fetcher = options.fetchBackfillStatus ?? ((kind) => getBackfillStatus(kind));
        const legacy = options.pollIntervalMs;
        this.activePollIntervalMs = options.activePollIntervalMs ?? legacy ?? 5000;
        this.idlePollIntervalMs = options.idlePollIntervalMs ?? 30_000;
        this.hasOwnerAccess = options.hasOwnerAccess ?? (() => authStore.showSettings);
    }

    retain(): () => void {
        this.refCount += 1;
        if (this.refCount === 1) {
            // Prime with an initial refresh and schedule based on resulting state.
            void this.tick();
        }

        return () => {
            this.refCount = Math.max(0, this.refCount - 1);
            if (this.refCount === 0 && this.pollTimer) {
                clearTimeout(this.pollTimer);
                this.pollTimer = null;
                this.currentIntervalMs = null;
            }
        };
    }

    private async tick() {
        await this.refresh();
        if (this.refCount <= 0) return;
        const hasActiveJob = this.isRunning(this.lastDetectionsStatus) || this.isRunning(this.lastWeatherStatus);
        const nextInterval = hasActiveJob ? this.activePollIntervalMs : this.idlePollIntervalMs;
        this.currentIntervalMs = nextInterval;
        if (this.pollTimer) clearTimeout(this.pollTimer);
        this.pollTimer = setTimeout(() => {
            void this.tick();
        }, nextInterval);
    }

    private isRunning(status: BackfillJobStatus | null): boolean {
        return !!status && status.status === 'running';
    }

    async refresh() {
        if (!this.hasOwnerAccess()) return;

        const [detections, weather] = await Promise.allSettled([
            this.fetcher('detections'),
            this.fetcher('weather')
        ]);

        if (detections.status === 'fulfilled') {
            this.lastDetectionsStatus = detections.value;
            this.detectionsScoped = syncBackfillJobProgress('detections', this.detectionsScoped, detections.value);
        }
        if (weather.status === 'fulfilled') {
            this.lastWeatherStatus = weather.value;
            this.weatherScoped = syncBackfillJobProgress('weather', this.weatherScoped, weather.value);
        }
    }
}

export const backfillStatusStore = new BackfillStatusStore();
