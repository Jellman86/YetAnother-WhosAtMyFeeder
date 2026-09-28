<script lang="ts">
    import CountedBirds from '../src/lib/components/CountedBirds.svelte';
    import type { BirdObservation, SnapshotCandidate } from '../src/lib/api';

    let birds = $state<BirdObservation[]>([
        { id: 1, bird_index: 0, candidate_id: 'crop-one', clip_variant: 'event', frame_index: 1, crop_box: [40, 35, 95, 90], detector_confidence: 0.8, species: 'House Finch', classifier_label: 'House Finch', classifier_score: 0.91, manual_species: false, is_hidden: false },
        { id: 2, bird_index: 1, candidate_id: 'crop-two', clip_variant: 'event', frame_index: 1, crop_box: [195, 50, 245, 105], detector_confidence: 0.72, species: 'Unknown Bird', classifier_label: null, classifier_score: 0.25, manual_species: false, is_hidden: false }
    ]);
    const candidates = [{ candidate_id: 'whole', source_mode: 'full_frame', clip_variant: 'event', frame_index: 1, image_url: '/api/fixture/whole.svg', thumbnail_url: null }] as SnapshotCandidate[];
</script>

<CountedBirds
    eventId="fixture-event"
    {birds}
    {candidates}
    speciesOptions={['House Finch', 'Northern Cardinal']}
    onchanged={(updated) => { birds = birds.map((bird) => bird.id === updated.id ? updated : bird); }}
/>
