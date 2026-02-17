import { type Detection, fetchEvents, fetchEventsCount } from '../api';
import { logger } from '../utils/logger';
import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';

export interface FrameResult {
    score: number;
    label: string;
    thumb?: string | null;
    frameIndex?: number | null;
}

export interface ReclassificationProgress {
    eventId: string;
    currentFrame: number;
    totalFrames: number;
    frameIndex?: number | null;
    clipTotal?: number | null;
    modelName?: string | null;
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

    private MAX_ITEMS = 50;

    async loadInitial() {
        this.isLoading = true;
        try {
            // Filter to last 3 days
            const d = new Date();
            d.setDate(d.getDate() - 3);
            const startDate = d.toISOString().split('T')[0];

            const [recent, countResult] = await Promise.all([
                fetchEvents({ 
                    limit: this.MAX_ITEMS,
                    startDate 
                }),
                fetchEventsCount({ 
                    startDate: new Date().toISOString().split('T')[0],
                    endDate: new Date().toISOString().split('T')[0]
                })
            ]);
            this.detections = recent;
            this.totalToday = countResult.count;
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
        if (!this.detections.find(d => d.frigate_event === detection.frigate_event)) {
            this.detections = [detection, ...this.detections].slice(0, this.MAX_ITEMS);
            this.totalToday++;
        }
    }

    updateDetection(updated: Detection) {
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
        } else if (!updated.is_hidden) {
            this.addDetection(definedPatch as Detection);
        }
    }

    removeDetection(eventId: string, detectionDate?: string) {
        const wasInList = this.detections.find(d => d.frigate_event === eventId);
        if (wasInList) {
            this.detections = this.detections.filter(d => d.frigate_event !== eventId);
        }

        const today = new Date().toISOString().split('T')[0];
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

    startReclassification(eventId: string, totalFrames: number = 15) {
        const now = Date.now();
        const normalizedTotal = Math.max(1, totalFrames);
        const existing = this.progressMap.get(eventId);
        if (
            existing &&
            existing.status === 'running' &&
            existing.currentFrame === 0 &&
            existing.totalFrames === normalizedTotal
        ) {
            return;
        }
        const newMap = new Map(this.progressMap);
        newMap.set(eventId, {
            eventId,
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
        modelName?: string | null
    ) {
        const now = Date.now();
        const newMap = new Map(this.progressMap);
        const existing = newMap.get(eventId);
        
        if (existing) {
            const slot = Math.max(1, currentFrame) - 1;
            const nextCurrentFrame = Math.max(existing.currentFrame, currentFrame);
            const nextTotalFrames = Math.max(existing.totalFrames, totalFrames);
            const nextFrameIndex = frameIndex ?? existing.frameIndex ?? null;
            const nextClipTotal = clipTotal ?? existing.clipTotal ?? null;
            const nextModelName = modelName ?? existing.modelName ?? null;
            const previousFrame = existing.frameResults[slot];
            const sameFrameResult = Boolean(
                previousFrame &&
                previousFrame.score === frameScore &&
                previousFrame.label === topLabel &&
                previousFrame.thumb === frameThumb &&
                previousFrame.frameIndex === frameIndex
            );
            if (
                sameFrameResult &&
                nextCurrentFrame === existing.currentFrame &&
                nextTotalFrames === existing.totalFrames &&
                nextFrameIndex === (existing.frameIndex ?? null) &&
                nextClipTotal === (existing.clipTotal ?? null) &&
                nextModelName === (existing.modelName ?? null)
            ) {
                return;
            }

            const frameResults = [...existing.frameResults];
            if (frameResults.length < nextTotalFrames) {
                frameResults.length = nextTotalFrames;
            }

            frameResults[slot] = {
                score: frameScore,
                label: topLabel,
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

    pruneReclassifications(runningTimeoutMs: number = 90_000, completedRetentionMs: number = 15_000): boolean {
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
}

export const detectionsStore = new DetectionsStore();
