<script lang="ts">
    import DetectionModal from '../src/lib/components/DetectionModal.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';
    import type { Detection } from '../src/lib/api';

    // Prop/auth boundary fixture. The actual modal owns all candidate loading and rendering.
    // API responses and images are supplied by the spec; this is not backend/inference E2E.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.publicAccessEnabled = true;
    authStore.isAuthenticated = true;
    let detection = $state<Detection>({
        frigate_event: 'A',
        display_name: 'Capture A',
        camera_name: 'Fixture feeder',
        detection_time: '2026-10-01T12:00:00Z',
        score: 0.9
    });
    window.snapshotRace = {
        completeAnalysis(id = 'A') {
            detectionsStore.startReclassification(id, 15, 'video');
            detectionsStore.completeReclassification(id, [], 'success');
        },
        progressAnalysis(frames) {
            detectionsStore.startReclassification('A', frames, 'video');
            for (let frame = 1; frame <= frames; frame += 1) {
                detectionsStore.updateReclassificationProgress('A', frame, frames, 0.5, 'Fixture bird');
            }
        },
        setCapture(id) { detection = { ...detection, frigate_event: id, display_name: `Capture ${id}` }; },
        setOwner(owner) { authStore.isAuthenticated = owner; },
        setSummary(counted) { detection = { ...detection, bird_summary: { counted, unknown: 0, excluded: 0, species: [{ species: 'Fixture bird', count: counted }], hint_only: false } }; }
    };
</script>

<DetectionModal
    {detection}
    classifierLabels={[]}
    llmReady={false}
    showVideoButton={false}
    onClose={() => {}}
    onViewSpecies={() => {}}
/>
