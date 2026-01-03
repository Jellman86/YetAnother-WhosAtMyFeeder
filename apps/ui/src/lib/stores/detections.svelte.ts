import { type Detection, fetchEvents, fetchEventsCount } from '../api';

// Svelte 5 shared state
class DetectionsStore {
    detections = $state<Detection[]>([]);
    totalToday = $state(0);
    isLoading = $state(false);
    connected = $state(false);

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
}

export const detectionsStore = new DetectionsStore();
