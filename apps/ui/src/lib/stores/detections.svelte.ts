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
        if (index !== -1) {
            this.detections[index] = { ...this.detections[index], ...updated };
        } else if (!updated.is_hidden) {
            this.addDetection(updated);
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

    startReclassification(eventId: string) {
        const newMap = new Map(this.progressMap);
        newMap.set(eventId, {
            eventId,
            currentFrame: 0,
            totalFrames: 15,
            frameResults: [],
            status: 'running'
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
        const newMap = new Map(this.progressMap);
        const existing = newMap.get(eventId);
        
        if (existing) {
            const targetTotal = Math.max(existing.totalFrames, totalFrames);
            const frameResults = [...existing.frameResults];
            if (frameResults.length < targetTotal) {
                frameResults.length = targetTotal;
            }

            const slot = Math.max(1, currentFrame) - 1;
            frameResults[slot] = {
                score: frameScore,
                label: topLabel,
                thumb: frameThumb,
                frameIndex
            };
            newMap.set(eventId, {
                ...existing,
                currentFrame: Math.max(existing.currentFrame, currentFrame),
                totalFrames: Math.max(existing.totalFrames, totalFrames),
                frameIndex: frameIndex ?? existing.frameIndex ?? null,
                clipTotal: clipTotal ?? existing.clipTotal ?? null,
                modelName: modelName ?? existing.modelName ?? null,
                frameResults,
                status: 'running'
            });
            this.progressMap = newMap;
        }
    }

    completeReclassification(eventId: string, results: any) {
        const newMap = new Map(this.progressMap);
        const existing = newMap.get(eventId);
        if (existing) {
            newMap.set(eventId, {
                ...existing,
                status: 'completed',
                results
            });
            this.progressMap = newMap;
        }
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
