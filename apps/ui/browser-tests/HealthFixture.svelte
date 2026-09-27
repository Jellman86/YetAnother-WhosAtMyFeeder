<script lang="ts">
    import HealthActivityTimeline from '../src/lib/components/HealthActivityTimeline.svelte';
    import type { Detection } from '../src/lib/api';
    import { buildHealthTimeline } from '../src/lib/utils/health-timeline';

    const detection: Detection = {
        frigate_event: 'browser-recorded', display_name: 'Prunella modularis',
        scientific_name: 'Prunella modularis', common_name: 'Dunnock', score: 0.96,
        camera_name: 'Feeder', detection_time: '2026-09-23T08:00:00Z'
    };
    const rows = buildHealthTimeline({
        visits: [{
            key: detection.frigate_event, species: detection.display_name, camera: detection.camera_name,
            frames: [detection], lead: detection, best: detection, startTime: detection.detection_time,
            endTime: detection.detection_time, needsReview: false, audioConfirmed: false
        }],
        filtered: [{
            eventId: 'browser-filtered', label: 'Prunella modularis', score: 0.2,
            reason: 'filter_low_confidence', timestamp: '2026-09-23T08:01:00Z'
        }],
        faults: [{
            eventId: 'browser-fault', label: null, score: null,
            reason: 'classify_snapshot_timeout', timestamp: '2026-09-23T07:59:00Z'
        }]
    });
    let mode = $state('events');
    let mounted = $state(true);
    let selected = $state('none');
</script>

<main style="padding: 16px; max-width: 1100px; margin: auto;">
    <h1>Health component regression fixture</h1>
    <label>Fixture state <select bind:value={mode}>
        <option value="events">Events</option><option value="empty">Empty</option><option value="loading">Loading</option>
    </select></label>
    <button onclick={() => (mounted = !mounted)}>Toggle mount</button>
    <output aria-label="Selected record">{selected}</output>
    <section style="margin-top: 16px; overflow: hidden; height: 240px;" aria-label="Clipping ancestor">
        {#if mounted}
            <HealthActivityTimeline
                rows={mode === 'events' ? rows : []}
                loading={mode === 'loading'}
                emptyMessage="No activity since startup"
                hiddenCount={mode === 'events' ? 2 : 0}
                onselect={(record) => (selected = record.frigate_event)}
            />
        {/if}
    </section>
    <div style="height: 1000px;" aria-hidden="true"></div>
</main>
