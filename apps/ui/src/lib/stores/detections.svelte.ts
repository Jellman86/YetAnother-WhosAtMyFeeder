import { type Detection, fetchEvents, fetchEventsCount } from '../api';

export interface ReclassificationProgress {
    eventId: string;
    currentFrame: number;
    totalFrames: number;
    frameScore: number;
    topLabel: string;
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
            const [recent, countResult] = await Promise.all([
                fetchEvents({ limit: this.MAX_ITEMS }),
                fetchEventsCount({ 
                    startDate: new Date().toISOString().split('T')[0],
                    endDate: new Date().toISOString().split('T')[0]
                })
            ]);
            this.detections = recent;
            this.totalToday = countResult.count;
        } catch (e) {
            console.error('Failed to load initial detections', e);
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
            // If it's a new high-score detection we didn't have before
            this.addDetection(updated);
        }
    }

    removeDetection(eventId: string, detectionDate?: string) {
        // Check if it was in our recent list
        const wasInList = this.detections.find(d => d.frigate_event === eventId);
        if (wasInList) {
            this.detections = this.detections.filter(d => d.frigate_event !== eventId);
        }

        // Always decrement today's total if the detection was from today
        // (if date not provided, we check if it was in the list and today)
        const today = new Date().toISOString().split('T')[0];
        const isToday = detectionDate 
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
            totalFrames: 15, // default max_frames
            frameScore: 0,
            topLabel: ''
        });
        this.progressMap = newMap;
    }

    updateReclassificationProgress(eventId: string, currentFrame: number, totalFrames: number, frameScore: number, topLabel: string) {
        const newMap = new Map(this.progressMap);
        newMap.set(eventId, {
            eventId,
            currentFrame,
            totalFrames,
            frameScore,
            topLabel
        });
        this.progressMap = newMap;
    }

    completeReclassification(eventId: string) {
        const newMap = new Map(this.progressMap);
        newMap.delete(eventId);
        this.progressMap = newMap;
    }

    getReclassificationProgress(eventId: string): ReclassificationProgress | undefined {
        return this.progressMap.get(eventId);
    }
}

export const detectionsStore = new DetectionsStore();
