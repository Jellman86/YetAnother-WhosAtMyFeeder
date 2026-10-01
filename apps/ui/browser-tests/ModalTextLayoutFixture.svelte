<script lang="ts">
    import DetectionModal from '../src/lib/components/DetectionModal.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import type { Detection } from '../src/lib/api';

    // Prop/auth boundary fixture. The actual modal owns all candidate loading and rendering.
    // API responses and images are supplied by the spec; this is not backend/inference E2E.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.publicAccessEnabled = true;
    authStore.isAuthenticated = true;
    const detection: Detection = {
        frigate_event: 'long-camera-capture-abcdefghijklmnopqrstuvwxyz-0123456789',
        display_name: 'Schwarzflügel-Rotschnabel-Blütenbesucher',
        camera_name: 'Gartenfutterstelle_ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789',
        detection_time: '2026-10-01T12:00:00Z', score: 0.9, frigate_score: 0.8
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
