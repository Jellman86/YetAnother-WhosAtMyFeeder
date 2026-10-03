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
        dunnock: { common: 'Dunnock', scientific: 'Prunella modularis' },
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
            score: id === 'dunnock' ? 0.9396 : 0.66
        };
    }

    let queue = $state((params.get('queue') ?? 'tit,robin,wren').split(',').map(capture));
    let record = $state<Detection>(queue[0]);
    // `page=tall` puts the queue over a long, scrolled dashboard the way the owner reaches it,
    // opened from a button rather than on load.
    const tallPage = params.get('page') === 'tall';
    let open = $state(!tallPage);
    // As on the dashboard, opening the full record closes the queue and opens the record.
    let handedOff = $state(false);
    let events = $state<string[]>([]);
    window.reviewMedia = {
        setRecord(id) { record = capture(id); },
        updateParent(identity) {
            const current = surface === 'record' ? record : queue[0];
            if (current) Object.assign(current, identity);
        },
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

{#if tallPage}
    <div style="height: 1400px" aria-hidden="true"></div>
    <button type="button" data-open-queue onclick={() => { open = true; }}>Open the queue</button>
    <div style="height: 2000px" aria-hidden="true"></div>
{/if}
<!-- Two blocks in the dashboard's order, so the queue hands over to the record as it does there. -->
{#if surface !== 'record' && open}
    <ReviewQueueModal
        {queue}
        labels={Object.values(NAMES).map((name) => params.get('labels') === 'scientific' ? name.scientific : name.common)}
        onidentify={(detection, species) => { events = [...events, `identify ${detection.frigate_event} ${species}`]; }}
        onhide={(detection) => { events = [...events, `hide ${detection.frigate_event}`]; }}
        onopen={(detection) => {
            events = [...events, `open ${detection.frigate_event}`];
            if (tallPage) { open = false; record = detection; handedOff = true; }
        }}
        onclose={() => { open = false; }}
    />
{/if}
{#if surface === 'record' || handedOff}
    <DetectionModal
        detection={record}
        classifierLabels={[]}
        llmReady={false}
        showVideoButton={false}
        onClose={() => { handedOff = false; }}
        onViewSpecies={() => {}}
    />
{/if}
<output class="sr-only" data-fixture-events>{events.join('\n')}</output>
