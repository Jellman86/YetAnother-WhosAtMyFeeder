<script lang="ts">
    import DetectionModal from '../src/lib/components/DetectionModal.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import type { Detection } from '../src/lib/api';

    // Prop and auth boundary fixture for the record's layout. The real dialog draws everything; the
    // spec answers its requests. `?record=short` is a record with no clip, no reference and no
    // lineage; the default is a long one with all of them. `?guest=true` opens it as a visitor. `?readings=` gives the long record
    // a snapshot reading that named another bird than its video reading.
    const query = new URLSearchParams(window.location.search);
    const short = query.get('record') === 'short';
    const readings = query.get('readings');
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.publicAccessEnabled = true;
    authStore.isAuthenticated = query.get('guest') !== 'true';
    authStore.enrichmentSummarySource = short ? 'disabled' : 'wikipedia';
    authStore.enrichmentSightingsSource = short ? 'disabled' : 'ebird';
    authStore.ebirdEnabled = !short;

    const detection: Detection = $state(short
        ? {
            frigate_event: 'record-layout-short',
            display_name: 'Robin',
            camera_name: 'feeder',
            detection_time: '2026-11-19T09:12:00Z',
            score: 0.74
        }
        : {
            frigate_event: 'record-layout-long',
            display_name: 'Eurasian Magpie',
            common_name: 'Eurasian Magpie',
            scientific_name: 'Pica pica',
            camera_name: 'greenhousecam',
            detection_time: '2026-11-19T15:31:00Z',
            score: 0.99,
            frigate_score: 0.71,
            has_clip: true,
            video_classification_status: 'completed',
            video_classification_label: 'Eurasian Magpie',
            video_classification_score: 0.99
        });
    if (!short && (readings === 'renamed' || readings === 'decided')) {
        Object.assign(detection, {
            score: 0.92,
            manual_tagged: readings === 'decided',
            video_classification_label: 'Pica pica',
            video_classification_score: 0.92,
            video_classification_input_source: 'model_crop',
            reading_agreement: 'disagree',
            snapshot_reading: { display_name: 'Carrion Crow', category_name: 'Corvus corone', scientific_name: 'Corvus corone', common_name: 'Carrion Crow', score: 0.81 }
        });
    } else if (!short && readings === 'kept') {
        Object.assign(detection, {
            display_name: 'Common Wood-Pigeon',
            common_name: 'Common Wood-Pigeon',
            scientific_name: 'Columba palumbus',
            category_name: 'Columba palumbus',
            video_classification_label: 'Pica pica',
            video_classification_score: 0.67,
            video_classification_input_source: 'model_crop',
            reading_agreement: 'disagree',
            snapshot_reading: { display_name: 'Common Wood-Pigeon', category_name: 'Columba palumbus', scientific_name: 'Columba palumbus', common_name: 'Common Wood-Pigeon', score: 0.99 }
        });
    }
</script>

<DetectionModal
    {detection}
    llmReady={false}
    onPlayVideo={short ? undefined : () => {}}
    onReclassify={readings ? () => {} : undefined}
    onClose={() => {}}
    onViewSpecies={() => {}}
/>
