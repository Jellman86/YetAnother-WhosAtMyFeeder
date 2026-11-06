<script lang="ts">
    import DetectionModal from '../src/lib/components/DetectionModal.svelte';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import type { Detection } from '../src/lib/api';

    // Prop/auth boundary fixture. The actual modal owns all candidate loading and rendering.
    // API responses and images are supplied by the spec; this is not backend/inference E2E.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.publicAccessEnabled = true;
    authStore.isAuthenticated = true;
    const requestedStatus = new URLSearchParams(window.location.search).get('videoStatus');
    const videoStatus = requestedStatus === 'pending' || requestedStatus === 'processing' ? requestedStatus : undefined;
    const detection: Detection = {
        video_classification_status: videoStatus,
        frigate_event: 'long-camera-capture-abcdefghijklmnopqrstuvwxyz-0123456789',
        display_name: 'Schwarzflügel-Rotschnabel-Blütenbesucher',
        camera_name: 'Gartenfutterstelle_ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789',
        detection_time: '2026-10-01T12:00:00Z', score: 0.9, frigate_score: 0.8
    };
    // `?controls=true` adds what brings the audio-context and edit-name controls on screen.
    if (new URLSearchParams(window.location.search).get('controls') === 'true') {
        detection.scientific_name = 'Prunella modularis';
        detection.audio_context_species = ['Dunnock'];
    }
    if (new URLSearchParams(window.location.search).get('observedProgress') === 'true') {
        detectionsStore.startReclassification(detection.frigate_event, 7, 'auto_video');
        for (let frame = 1; frame <= 3; frame += 1) {
            detectionsStore.updateReclassificationProgress(detection.frigate_event, frame, 7, 0.9, 'House Sparrow');
        }
    }
</script>

<DetectionModal
    {detection}
    llmReady={false}
    showVideoButton={false}
    onClose={() => {}}
    onViewSpecies={() => {}}
/>
