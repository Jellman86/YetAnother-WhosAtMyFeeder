<script lang="ts">
    import CountedBirds from '../src/lib/components/CountedBirds.svelte';
    import FieldLog from '../src/lib/components/FieldLog.svelte';
    import type { BirdObservation, Detection, SnapshotCandidate } from '../src/lib/api';
    import { groupDetectionsIntoVisits } from '../src/lib/utils/visit-grouping';

    // Boundary fixture: the API is mocked by the spec and every scene is a synthetic SVG with
    // a declared size. It exercises rendering and state, not inference or stored media.
    const params = new URLSearchParams(location.search);
    const scenario = params.get('case') ?? 'cardinal';
    const SCENE = 'fixture__full_frame__f150__abc';

    function bird(id: number, box: number[], species: string, extra: Partial<BirdObservation> = {}): BirdObservation {
        return {
            id,
            bird_index: id - 1,
            candidate_id: `${SCENE}__observed__${id}`,
            clip_variant: 'event',
            frame_index: 150,
            crop_box: box,
            detector_confidence: 0.8,
            species,
            classifier_label: species,
            classifier_score: 0.9,
            manual_species: false,
            is_hidden: false,
            ...extra
        };
    }

    function scene(id: string, url: string | null, extra: Partial<SnapshotCandidate> = {}): SnapshotCandidate {
        return {
            candidate_id: id,
            source_mode: 'full_frame',
            clip_variant: 'event',
            frame_index: 150,
            ranking_score: 0.5,
            selected: false,
            snapshot_source: 'hq_candidate_full_frame',
            image_url: url,
            thumbnail_url: `/api/fixture/${id}-thumb.svg`,
            ...extra
        };
    }

    // The reporter's Cardinal Intensive geometry: portrait from frame 75, birds counted on frame 150.
    const portrait: SnapshotCandidate = {
        ...scene('fixture__model_crop__f75__def', '/api/fixture/portrait.svg'),
        source_mode: 'model_crop',
        frame_index: 75,
        crop_box: [1418, 1231, 1673, 1517],
        selected: true
    };
    const cardinal = [
        bird(3, [858, 1151, 967, 1352], 'Unknown Bird', { classifier_label: 'Poecile hudsonicus', classifier_score: 0.27, detector_confidence: 0.19 }),
        bird(4, [1454, 1265, 1642, 1494], 'Cardinalis cardinalis', { classifier_score: 0.69, detector_confidence: 0.86 })
    ];

    function manyBirds(): BirdObservation[] {
        return Array.from({ length: 60 }, (_, index) => {
            const column = index % 10;
            const row = Math.floor(index / 10);
            const box = [100 + column * 360, 100 + row * 330, 260 + column * 360, 260 + row * 330];
            const species = index < 3 ? 'House Finch' : index === 3 ? 'Unknown Bird' : `Species ${index}`;
            return bird(index + 1, box, species, { is_hidden: index >= 58 });
        });
    }

    const setups: Record<string, { birds: BirdObservation[]; candidates: SnapshotCandidate[]; photograph: SnapshotCandidate | null }> = {
        cardinal: { birds: cardinal, candidates: [portrait, scene('fixture__full_frame__f75__ghi', '/api/fixture/f75.svg', { frame_index: 75 }), scene(SCENE, '/api/fixture/scene-3840.svg')], photograph: portrait },
        many: { birds: manyBirds(), candidates: [scene(SCENE, '/api/fixture/scene-3840.svg')], photograph: null },
        resized: { birds: cardinal, candidates: [scene(SCENE, '/api/fixture/scene-960.svg')], photograph: null },
        thumbnail: { birds: cardinal, candidates: [scene(SCENE, null)], photograph: null },
        missing: { birds: cardinal, candidates: [scene(SCENE, '/api/fixture/missing.svg')], photograph: null },
        late: { birds: cardinal, candidates: [scene(SCENE, '/api/fixture/scene-slow.svg')], photograph: null },
        empty: { birds: [], candidates: [], photograph: null }
    };
    const setup = setups[scenario] ?? setups.cardinal;

    let birds = $state<BirdObservation[]>(setup.birds);
    let candidates = $state<SnapshotCandidate[]>(setup.candidates);
    let generation = $state(1);
    let staleCount = $state(0);
    let changedCount = $state(0);
    let opened = $state('');

    /** Stands in for a reread or recount of the same capture, on a different counted frame. */
    function recount(): void {
        const regenerated = 'fixture__full_frame__f200__xyz';
        candidates = [scene(regenerated, '/api/fixture/scene-1920.svg', { frame_index: 200 })];
        birds = [
            bird(4, [400, 300, 700, 600], 'Cardinalis cardinalis', { frame_index: 200, candidate_id: `${regenerated}__observed__0` })
        ];
        generation += 1;
    }

    const day = '2026-09-30T12:';
    const logDetections: Detection[] = [
        { frigate_event: 'visit-a-1', display_name: 'House Finch', score: 0.92, detection_time: `${day}04:00Z`, camera_name: 'feeder', bird_summary: { counted: 2, unknown: 0, excluded: 0, species: [{ species: 'House Finch', count: 2 }], hint_only: false } },
        { frigate_event: 'visit-a-2', display_name: 'House Finch', score: 0.95, detection_time: `${day}03:00Z`, camera_name: 'feeder', bird_summary: { counted: 3, unknown: 1, excluded: 0, species: [{ species: 'House Finch', count: 2 }], hint_only: false } },
        { frigate_event: 'visit-b', display_name: 'Northern Cardinal', score: 0.9, detection_time: `${day}01:00Z`, camera_name: 'feeder', bird_summary: { counted: 0, unknown: 0, excluded: 1, species: [], hint_only: false } },
        { frigate_event: 'visit-c', display_name: 'Blue Tit', score: 0.88, detection_time: '2026-09-30T11:30:00Z', camera_name: 'feeder', bird_summary: null },
        { frigate_event: 'visit-d', display_name: 'Great Tit', score: 0.87, detection_time: '2026-09-30T11:00:00Z', camera_name: 'feeder', bird_summary: { counted: 1, unknown: 0, excluded: 0, species: [{ species: 'Great Tit', count: 1 }], hint_only: false } }
    ];
    const visits = groupDetectionsIntoVisits(logDetections, { reviewThreshold: 0.5 });
</script>

{#if scenario === 'fieldlog'}
    <FieldLog {visits} showHeader={false} onselect={(detection) => { opened = detection.frigate_event; }} />
    <p data-fixture-opened>{opened}</p>
{:else}
    <div class="space-y-3">
        <CountedBirds
            eventId="fixture-event"
            {birds}
            {candidates}
            photograph={setup.photograph}
            speciesOptions={['House Finch', 'Northern Cardinal']}
            {generation}
            countingAvailable={scenario === 'empty'}
            error={params.get('state') === 'error'}
            loading={params.get('state') === 'loading'}
            onretry={() => { generation += 1; }}
            onchanged={(updated) => { changedCount += 1; birds = birds.map((item) => item.id === updated.id ? updated : item); }}
            onstale={() => { staleCount += 1; }}
        />
        <button type="button" class="btn btn-ghost min-h-11" onclick={recount} data-fixture-recount>Recount</button>
        <p data-fixture-stale>{staleCount}</p>
        <p data-fixture-changed>{changedCount}</p>
    </div>
{/if}
