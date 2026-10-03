<script lang="ts">
    import VisitCaptures from '../src/lib/components/VisitCaptures.svelte';
    import type { DetectionVisit, VisitOptions } from '../src/lib/api/visits';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import type { Detection } from '../src/lib/api';
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.isAuthenticated = true;
    const record: Detection = { frigate_event: 'first', display_name: 'Turdus merula', scientific_name: 'Turdus merula', common_name: 'Eurasian Blackbird', detection_time: '2026-10-02T10:42:21Z', camera_name: 'birdcam', score: 0.95, has_clip: true };
    let visit = $state<DetectionVisit>({ visit_id: 'first', start_time: record.detection_time, end_time: '2026-10-02T10:44:47Z', capture_count: 21, best_score: 0.95, needs_review: false, audio_confirmed: false, representative: record, latest: record, peak_capture: null });
    let window = $state<VisitOptions>({ startDate: '2026-10-02', endDate: '2026-10-02' });
    let selected = $state('none');
    let played = $state('none');
</script>
<main class="mx-auto max-w-3xl space-y-4 p-4">
    <h1>Shared visit timeline regression fixture</h1>
    <button class="btn btn-secondary" onclick={() => { window = { startDate: '2026-10-03', endDate: '2026-10-03' }; }}>Change window</button>
    <button class="btn btn-secondary" onclick={() => { visit = { ...visit, capture_count: 22, end_time: '2026-10-02T10:45:10Z' }; }}>New capture</button>
    <button class="btn btn-secondary" onclick={() => { authStore.isAuthenticated = false; authStore.publicAccessEnabled = true; }}>Guest access</button>
    <output aria-label="Selected record">{selected}</output>
    <output aria-label="Played record">{played}</output>
    <section class="card-base overflow-hidden"><VisitCaptures {visit} {window} onselect={record => selected = record.frigate_event} onplay={record => played = record.frigate_event} /></section>
</main>
