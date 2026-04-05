import { getBackfillStatus, type BackfillJobStatus } from '../api/backfill';
import { authStore } from './auth.svelte';
import { jobProgressStore } from './job_progress.svelte';
import { syncBackfillJobProgress, type BackfillKind } from '../backfill/job-progress';
import type { ScopedBackfillProgress } from '../backfill/progress';

interface BackfillStatusStoreOptions {
    fetchBackfillStatus?: (kind: BackfillKind) => Promise<BackfillJobStatus | null>;
    pollIntervalMs?: number;
    hasOwnerAccess?: () => boolean;
}

export class BackfillStatusStore {
    private readonly fetcher: (kind: BackfillKind) => Promise<BackfillJobStatus | null>;
    private readonly pollIntervalMs: number;
    private readonly hasOwnerAccess: () => boolean;
    private refCount = 0;
    private pollTimer: ReturnType<typeof setInterval> | null = null;
    private detectionsScoped = $state<ScopedBackfillProgress>({ jobId: null, total: 0 });
    private weatherScoped = $state<ScopedBackfillProgress>({ jobId: null, total: 0 });

    constructor(options: BackfillStatusStoreOptions = {}) {
        this.fetcher = options.fetchBackfillStatus ?? ((kind) => getBackfillStatus(kind));
        this.pollIntervalMs = options.pollIntervalMs ?? 2000;
        this.hasOwnerAccess = options.hasOwnerAccess ?? (() => authStore.showSettings);
    }

    retain(): () => void {
        this.refCount += 1;
        if (this.refCount === 1) {
            void this.refresh();
            this.pollTimer = setInterval(() => {
                void this.refresh();
            }, this.pollIntervalMs);
        }

        return () => {
            this.refCount = Math.max(0, this.refCount - 1);
            if (this.refCount === 0 && this.pollTimer) {
                clearInterval(this.pollTimer);
                this.pollTimer = null;
            }
        };
    }

    async refresh() {
        if (!this.hasOwnerAccess()) return;

        const [detections, weather] = await Promise.allSettled([
            this.fetcher('detections'),
            this.fetcher('weather')
        ]);

        if (detections.status === 'fulfilled') {
            this.detectionsScoped = syncBackfillJobProgress('detections', this.detectionsScoped, detections.value);
        }
        if (weather.status === 'fulfilled') {
            this.weatherScoped = syncBackfillJobProgress('weather', this.weatherScoped, weather.value);
        }
    }
}

export const backfillStatusStore = new BackfillStatusStore();
