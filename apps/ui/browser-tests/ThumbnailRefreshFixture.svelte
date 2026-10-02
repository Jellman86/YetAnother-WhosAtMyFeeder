<script lang="ts">
    import DetectionCard from '../src/lib/components/DetectionCard.svelte';
    import DetectionPreview from '../src/lib/components/DetectionPreview.svelte';
    import ReviewQueueCard from '../src/lib/components/ReviewQueueCard.svelte';
    import Notifications from '../src/lib/pages/Notifications.svelte';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';
    import { notificationCenter } from '../src/lib/stores/notification_center.svelte';
    import type { Detection } from '../src/lib/api';

    // Every list surface that draws a capture's thumbnail, side by side. The spec supplies the
    // images; the store calls stand in for the live reclassification events.
    function capture(id: string): Detection {
        return {
            frigate_event: id,
            display_name: `Capture ${id}`,
            common_name: `Capture ${id}`,
            camera_name: 'birdcam',
            detection_time: '2026-10-01T12:00:00Z',
            score: 0.8
        };
    }

    const a = capture('A');
    const b = capture('B');
    notificationCenter.clear();
    notificationCenter.add({ id: 'detection:A', type: 'detection', title: 'Capture A', meta: { event_id: 'A' } });
    notificationCenter.add({ id: 'detection:B', type: 'detection', title: 'Capture B', meta: { event_id: 'B' } });

    window.thumbnailRefresh = {
        progressAnalysis(id, frames) {
            detectionsStore.startReclassification(id, frames, 'video');
            for (let frame = 1; frame <= frames; frame += 1) {
                detectionsStore.updateReclassificationProgress(id, frame, frames, 0.5, 'Fixture bird');
            }
        },
        completeAnalysis(id) {
            detectionsStore.startReclassification(id, 15, 'video');
            detectionsStore.completeReclassification(id, [], 'success');
        }
    };
</script>

<div class="grid grid-cols-2 gap-4 p-4">
    <div data-surface="card-A"><DetectionCard detection={a} /></div>
    <div data-surface="card-B"><DetectionCard detection={b} /></div>
</div>
<div class="p-4" data-surface="queue-card">
    <ReviewQueueCard queue={{ items: [a, b], total: 2, remaining: 0, oldest: a, reasons: new Map(), newSpeciesSightings: new Map() }} />
</div>
<div class="p-4" data-surface="preview">
    <DetectionPreview detection={a} frames={[a, b]} frameCount={2} primaryName="Capture A" />
</div>
<div class="p-4" data-surface="notifications"><Notifications /></div>
