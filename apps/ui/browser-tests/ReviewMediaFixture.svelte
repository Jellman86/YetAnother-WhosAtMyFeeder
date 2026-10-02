<script lang="ts">
    import ReviewQueueModal from '../src/lib/components/ReviewQueueModal.svelte';
    import DetectionModal from '../src/lib/components/DetectionModal.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';
    import type { Detection } from '../src/lib/api';

    // Prop/auth boundary fixture. The actual queue and record own every candidate read and every
    // image; the spec supplies the HTTP responses. This is not backend or inference E2E.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.publicAccessEnabled = true;
    authStore.isAuthenticated = true;

    const params = new URLSearchParams(location.search);
    const surface = params.get('surface') ?? 'queue';
    if (params.get('theme') === 'dark') document.documentElement.classList.add('dark');

    const NAMES: Record<string, { common: string; scientific: string }> = {
        tit: { common: 'Eurasian Blue Tit', scientific: 'Cyanistes caeruleus' },
        robin: { common: 'European Robin', scientific: 'Erithacus rubecula' },
        wren: { common: 'Eurasian Wren', scientific: 'Troglodytes troglodytes' }
    };

    function capture(id: string, index = 0): Detection {
        const name = NAMES[id] ?? { common: id, scientific: id };
        return {
            frigate_event: id,
            display_name: name.common,
            common_name: name.common,
            scientific_name: name.scientific,
            camera_name: 'birdcam',
            detection_time: `2026-09-18T09:${String(28 + index).padStart(2, '0')}:00Z`,
            score: 0.66
        };
    }

    const queue = (params.get('queue') ?? 'tit,robin,wren').split(',').map(capture);
    let record = $state<Detection>(queue[0]);
    let open = $state(true);
    let events = $state<string[]>([]);
    window.reviewMedia = {
        setRecord(id) { record = capture(id); },
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

{#if surface === 'record'}
    <DetectionModal
        detection={record}
        classifierLabels={[]}
        llmReady={false}
        showVideoButton={false}
        onClose={() => {}}
        onViewSpecies={() => {}}
    />
{:else if open}
    <ReviewQueueModal
        {queue}
        labels={Object.values(NAMES).map((name) => params.get('labels') === 'scientific' ? name.scientific : name.common)}
        onidentify={(detection, species) => { events = [...events, `identify ${detection.frigate_event} ${species}`]; }}
        onhide={(detection) => { events = [...events, `hide ${detection.frigate_event}`]; }}
        onopen={(detection) => { events = [...events, `open ${detection.frigate_event}`]; }}
        onclose={() => { open = false; }}
    />
{/if}
<output class="sr-only" data-fixture-events>{events.join('\n')}</output>
