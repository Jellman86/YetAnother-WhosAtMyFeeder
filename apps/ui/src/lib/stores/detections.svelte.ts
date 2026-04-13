import { type Detection, fetchEvents, fetchEventsCount } from '../api';
import { logger } from '../utils/logger';
import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
import { toLocalYMD } from '../utils/date-only';
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';

export interface FrameResult {
    score: number;
    label: string;
    thumb?: string | null;
    frameIndex?: number | null;
}

export interface ReclassificationProgress {
    eventId: string;
    strategy?: string | null;
    currentFrame: number;
    totalFrames: number;
    frameIndex?: number | null;
    clipTotal?: number | null;
    modelName?: string | null;
    ramUsage?: string | null;
    frameResults: FrameResult[];
    status: 'running' | 'completed';
    startedAt: number;
    lastUpdateAt: number;
    completedAt?: number | null;
    results?: any; // Final results from backend
}

// Svelte 5 shared state
class DetectionsStore {
    detections = $state<Detection[]>([]);
    totalToday = $state(0);
    isLoading = $state(false);
    connected = $state(false);
    progressMap = $state<Map<string, ReclassificationProgress>>(new Map());
    mutationVersion = $state(0);
    patchMap = $state<Map<string, Partial<Detection>>>(new Map());

    private MAX_ITEMS = 50;
    private MAX_RECLASSIFICATION_FRAMES = 240;
    private MAX_PATCH_ITEMS = 2000;

    private readonly staleTracker = new StaleTracker(30_000); // 30 seconds
    private readonly unregister: () => void;

    constructor() {
        this.unregister = refreshCoordinator.register(() => this.refreshIfStale());
    }

    private markMutated() {
        this.mutationVersion += 1;
    }

    private rememberPatch(updated: Partial<Detection>) {
        const eventId = typeof updated?.frigate_event === 'string' ? updated.frigate_event.trim() : '';
        if (!eventId) return;

        const definedEntries = Object.entries(updated).filter(([, value]) => value !== undefined);
        if (definedEntries.length === 0) return;

        const patch = Object.fromEntries(definedEntries) as Partial<Detection>;
        const next = new Map(this.patchMap);
        const existing = next.get(eventId) ?? {};
        // Refresh insertion order for LRU-style pruning.
        next.delete(eventId);
        next.set(eventId, { ...existing, ...patch });

        while (next.size > this.MAX_PATCH_ITEMS) {
            const oldestKey = next.keys().next().value;
            if (!oldestKey) break;
            next.delete(oldestKey);
        }
        this.patchMap = next;
        this.markMutated();
    }

    async refreshIfStale(): Promise<void> {
        if (this.isLoading || !this.staleTracker.isStale()) return;
        await this.loadInitial();
    }

    async loadInitial() {
        this.isLoading = true;
        try {
            // Filter to last 3 days
            const d = new Date();
            d.setDate(d.getDate() - 3);
            const startDate = toLocalYMD(d);

            const [recent, countResult] = await Promise.all([
                fetchEvents({ 
                    limit: this.MAX_ITEMS,
                    startDate 
                }),
                fetchEventsCount({ 
                    startDate: toLocalYMD(),
                    endDate: toLocalYMD()
                })
            ]);
            this.detections = recent;
            this.totalToday = countResult.count;
            this.markMutated();
            this.staleTracker.touch();
        } catch (e) {
            if (isTransientRequestError(e)) {
                logger.warn('Initial detections fetch failed (transient)', {
                    message: getErrorMessage(e)
                });
            } else {
                logger.error('Failed to load initial detections', e);
            }
        } finally {
            this.isLoading = false;
        }
    }

    addDetection(detection: Detection) {
        if (!detection || typeof detection.frigate_event !== 'string' || detection.frigate_event.trim().length === 0) {
            logger.warn('Skipping invalid detection payload without event id', { detection });
            return;
        }
        this.rememberPatch(detection);
        if (!this.detections.find(d => d.frigate_event === detection.frigate_event)) {
            this.detections = [detection, ...this.detections].slice(0, this.MAX_ITEMS);
            this.totalToday++;
            this.markMutated();
        }
    }

    updateDetection(updated: Detection) {
        this.rememberPatch(updated);
        if (updated.is_hidden) {
            this.removeDetection(updated.frigate_event, updated.detection_time);
            return;
        }

        const index = this.detections.findIndex(d => d.frigate_event === updated.frigate_event);
        const definedEntries = Object.entries(updated).filter(([, value]) => value !== undefined);
        if (definedEntries.length === 0) return;
        const definedPatch = Object.fromEntries(definedEntries) as Partial<Detection>;
        if (index !== -1) {
            // Preserve existing fields when SSE payloads omit optional values.
            const existing = this.detections[index];
            const changed = definedEntries.some(([key, value]) => (existing as any)[key] !== value);
            if (!changed) return;
            this.detections[index] = { ...existing, ...definedPatch };
            this.markMutated();
        } else if (!updated.is_hidden) {
            this.addDetection(definedPatch as Detection);
        }
    }

    removeDetection(eventId: string, detectionDate?: string) {
        if (eventId) {
            const next = new Map(this.patchMap);
            next.delete(eventId);
            this.patchMap = next;
        }
        const wasInList = this.detections.find(d => d.frigate_event === eventId);
        if (wasInList) {
            this.detections = this.detections.filter(d => d.frigate_event !== eventId);
            this.markMutated();
        }

        const today = toLocalYMD();
        const isToday =
            detectionDate
                ? detectionDate.startsWith(today)
                : (wasInList && wasInList.detection_time.startsWith(today));

        if (isToday && this.totalToday > 0) {
            this.totalToday--;
        }
    }

    setConnected(status: boolean) {
        this.connected = status;
    }

    private toSafeInt(value: unknown, fallback: number, min = 0): number {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return fallback;
        return Math.max(min, Math.floor(parsed));
    }

    startReclassification(eventId: string, totalFrames: number = 15, strategy: string | null = null) {
        if (!eventId || typeof eventId !== 'string') return;
        const now = Date.now();
        const normalizedTotal = Math.min(
            this.MAX_RECLASSIFICATION_FRAMES,
            this.toSafeInt(totalFrames, 1, 1)
        );
        const existing = this.progressMap.get(eventId);
        if (
            existing &&
            existing.status === 'running' &&
            existing.currentFrame === 0 &&
            existing.totalFrames === normalizedTotal &&
            (existing.strategy ?? null) === strategy
        ) {
            return;
        }
        const newMap = new Map(this.progressMap);
        newMap.set(eventId, {
            eventId,
            strategy,
            currentFrame: 0,
            totalFrames: normalizedTotal,
            frameResults: [],
            status: 'running',
            startedAt: now,
            lastUpdateAt: now,
            completedAt: null
        });
        this.progressMap = newMap;
    }

    updateReclassificationProgress(
        eventId: string,
        currentFrame: number,
        totalFrames: number,
        frameScore: number,
        topLabel: string,
        frameThumb?: string | null,
        frameIndex?: number | null,
        clipTotal?: number | null,
        modelName?: string | null,
        ramUsage?: string | null
    ) {
        if (!eventId || typeof eventId !== 'string') return;
        const now = Date.now();
        const newMap = new Map(this.progressMap);
        const existing = newMap.get(eventId);
        
        if (existing) {
            const safeCurrentFrame = this.toSafeInt(currentFrame, existing.currentFrame, 0);
            const safeTotalFrames = this.toSafeInt(totalFrames, existing.totalFrames, 1);
            const boundedCurrentFrame = Math.min(this.MAX_RECLASSIFICATION_FRAMES, safeCurrentFrame);
            const boundedTotalFrames = Math.min(this.MAX_RECLASSIFICATION_FRAMES, safeTotalFrames);
            
            // Trust backend's total frames if it's explicitly provided and valid
            const nextTotalFrames = boundedTotalFrames > 0 
                ? boundedTotalFrames 
                : Math.max(1, existing.totalFrames, boundedCurrentFrame);
                
            const nextCurrentFrame = Math.min(
                nextTotalFrames,
                Math.max(existing.currentFrame, boundedCurrentFrame)
            );
            const slot = Math.min(
                nextTotalFrames - 1,
                Math.max(0, (boundedCurrentFrame > 0 ? boundedCurrentFrame : nextCurrentFrame) - 1)
            );
            const nextFrameIndex = frameIndex ?? existing.frameIndex ?? null;
            const nextClipTotal = clipTotal ?? existing.clipTotal ?? null;
            const nextModelName = modelName ?? existing.modelName ?? null;
            const nextRamUsage = ramUsage ?? existing.ramUsage ?? null;
            const previousFrame = existing.frameResults[slot];
            const safeFrameScore = Number.isFinite(frameScore) ? frameScore : 0;
            const safeTopLabel = typeof topLabel === 'string' ? topLabel : String(topLabel ?? '');
            const sameFrameResult = Boolean(
                previousFrame &&
                previousFrame.score === safeFrameScore &&
                previousFrame.label === safeTopLabel &&
                previousFrame.thumb === frameThumb &&
                previousFrame.frameIndex === frameIndex
            );
            if (
                sameFrameResult &&
                nextCurrentFrame === existing.currentFrame &&
                nextTotalFrames === existing.totalFrames &&
                nextFrameIndex === (existing.frameIndex ?? null) &&
                nextClipTotal === (existing.clipTotal ?? null) &&
                nextModelName === (existing.modelName ?? null) &&
                nextRamUsage === (existing.ramUsage ?? null)
            ) {
                return;
            }

            const frameResults = [...existing.frameResults];
            if (frameResults.length < nextTotalFrames) {
                frameResults.length = nextTotalFrames;
            }

            frameResults[slot] = {
                score: safeFrameScore,
                label: safeTopLabel,
                thumb: frameThumb,
                frameIndex
            };
            newMap.set(eventId, {
                ...existing,
                currentFrame: nextCurrentFrame,
                totalFrames: nextTotalFrames,
                frameIndex: nextFrameIndex,
                clipTotal: nextClipTotal,
                modelName: nextModelName,
                ramUsage: nextRamUsage,
                frameResults,
                status: 'running',
                lastUpdateAt: now
            });
            this.progressMap = newMap;
        }
    }

    completeReclassification(eventId: string, results: any) {
        const now = Date.now();
        const newMap = new Map(this.progressMap);
        const existing = newMap.get(eventId);
        if (existing) {
            newMap.set(eventId, {
                ...existing,
                status: 'completed',
                lastUpdateAt: now,
                completedAt: now,
                results
            });
            this.progressMap = newMap;
        }
    }

    pruneReclassifications(runningTimeoutMs: number = 90_000, completedRetentionMs: number = 35_000): boolean {
        const now = Date.now();
        const newMap = new Map(this.progressMap);
        let changed = false;

        for (const [eventId, progress] of newMap.entries()) {
            if (progress.status === 'running') {
                if (now - progress.lastUpdateAt > runningTimeoutMs) {
                    newMap.delete(eventId);
                    changed = true;
                }
                continue;
            }

            const completedAt = progress.completedAt ?? progress.lastUpdateAt;
            if (now - completedAt > completedRetentionMs) {
                newMap.delete(eventId);
                changed = true;
            }
        }

        if (changed) {
            this.progressMap = newMap;
        }
        return changed;
    }

    dismissReclassification(eventId: string) {
        const newMap = new Map(this.progressMap);
        newMap.delete(eventId);
        this.progressMap = newMap;
    }

    getReclassificationProgress(eventId: string): ReclassificationProgress | undefined {
        return this.progressMap.get(eventId);
    }

    getDetectionPatch(eventId: string): Partial<Detection> | undefined {
        return this.patchMap.get(eventId);
    }
}

export const detectionsStore = new DetectionsStore();
