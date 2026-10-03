<script lang="ts">
    import FieldLog from '../src/lib/components/FieldLog.svelte';
    import DayBar from '../src/lib/components/DayBar.svelte';
    import ReviewQueueCard from '../src/lib/components/ReviewQueueCard.svelte';
    import DeskContextCards from '../src/lib/components/DeskContextCards.svelte';
    import type { Detection } from '../src/lib/api';
    import type { DetectionVisit as ServerVisit } from '../src/lib/api/visits';
    import { fromServerVisit } from '../src/lib/utils/visit-grouping';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { settingsStore } from '../src/lib/stores/settings.svelte';
    import type { ReviewQueue } from '../src/lib/utils/review-queue';

    // The Dashboard's own composition, with the HTTP boundary supplied by the spec.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.isAuthenticated = true;
    const params = new URLSearchParams(location.search);
    const phase = params.get('state') ?? 'ready';
    if (params.get('theme') === 'dark') document.documentElement.classList.add('dark');
    if (params.get('clock') === '12h') authStore.timeFormat = '12h';
    // Settings name the cameras long before the day's totals arrive.
    if (params.get('cameras') === 'configured') {
        settingsStore.settings = { cameras: ['birdcam', 'nestcam'] } as unknown as NonNullable<typeof settingsStore.settings>;
    }
    const window = { startTime: '2026-10-02T00:00:00Z', endTime: '2026-10-03T00:00:00Z' };

    function record(id: string, overrides: Partial<Detection> = {}): Detection {
        return {
            frigate_event: id, display_name: 'Turdus merula', scientific_name: 'Turdus merula',
            common_name: 'Eurasian Blackbird', detection_time: '2026-10-02T10:44:04Z',
            camera_name: params.get('cameras') === 'two' && id.startsWith('cowbird') ? 'nestcam' : 'birdcam',
            score: 0.99, has_clip: true, ...overrides
        };
    }
    function visit(id: string, count: number, representative: Detection, extra: Partial<ServerVisit> = {}): ServerVisit {
        return {
            visit_id: id, start_time: '2026-10-02T10:42:21Z', end_time: representative.detection_time,
            capture_count: count, best_score: representative.score, needs_review: false, audio_confirmed: false,
            representative, latest: representative, peak_capture: null, ...extra
        };
    }
    const blackbird = record('blackbird');
    const serverVisits: ServerVisit[] = [
        visit('blackbird', 13, blackbird, {
            latest: record('blackbird-latest', { detection_time: '2026-10-02T10:44:47Z', score: 0.86 }),
            peak_capture: record('blackbird-peak', { bird_summary: { counted: 3, unknown: 0, excluded: 0, species: [], hint_only: false } })
        }),
        visit('dunnock', 1, record('dunnock', { display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock', detection_time: '2026-10-02T10:20:00Z', score: 0.89 }), { start_time: '2026-10-02T10:20:00Z' }),
        visit('cowbird', 3, record('cowbird', { display_name: 'Molothrus ater', scientific_name: 'Molothrus ater', common_name: 'Brown-headed Cowbird', detection_time: '2026-10-02T09:59:00Z', score: 0.77 }), {
            start_time: '2026-10-02T09:58:10Z',
            latest: record('cowbird-latest', { display_name: 'Molothrus ater', scientific_name: 'Molothrus ater', common_name: 'Brown-headed Cowbird', detection_time: '2026-10-02T09:59:30Z', score: 0.7 })
        }),
        visit('unknown', 2, record('unknown', { display_name: 'Unknown Bird', scientific_name: null, common_name: null, detection_time: '2026-10-02T09:40:00Z', score: 0.42 }), { needs_review: true, start_time: '2026-10-02T09:39:30Z' })
    ];
    const visits = phase === 'ready' ? serverVisits.map((item) => fromServerVisit(item, window)) : [];
    let selected = $state('none');
    let played = $state('none');
    let retried = $state(0);
    const emptyQueue: ReviewQueue = { items: [], total: 0, remaining: 0, oldest: null, reasons: new Map(), newSpeciesSightings: new Map() };
</script>

<main class="mx-auto max-w-3xl space-y-6 px-4 pb-8 pt-4">
    <output aria-label="Selected record">{selected}</output>
    <output aria-label="Played record">{played}</output>
    <output aria-label="Retries">{retried}</output>
    {#if phase !== 'ready'}
        <DayBar
            visitCount={null}
            countedBirds={0}
            countedCaptures={0}
            speciesCount={null}
            unresolvedCount={null}
            audioCalls={null}
            audioConfirmations={0}
            loading={phase === 'loading'}
            connected={false}
        />
    {/if}
    <FieldLog
        {visits}
        hiddenCount={phase === 'ready' ? 2 : 0}
        loading={phase === 'loading'}
        unavailable={phase === 'unavailable'}
        canIdentify={true}
        onselect={(detection) => (selected = detection.frigate_event)}
        onidentify={(detection) => (selected = `identify:${detection.frigate_event}`)}
        onplay={(detection) => (played = detection.frigate_event)}
        onretry={() => (retried += 1)}
    />
    {#if phase !== 'ready'}
        <ReviewQueueCard queue={emptyQueue} status={phase === 'loading' ? 'loading' : 'unavailable'} />
        <DeskContextCards detections={[]} visits={[]} cameraVisits={null} loading={phase === 'loading'} unavailable={phase === 'unavailable'} />
    {/if}
</main>
