<script lang="ts">
    import SpeciesChecks from '../src/lib/components/SpeciesChecks.svelte';
    import Toast from '../src/lib/components/Toast.svelte';
    import type { ShowcaseRow } from '../src/lib/leaderboard/showcase';
    const owner = new URLSearchParams(location.search).get('viewer') !== 'guest';
    let kept = $state(0);
    const row = (key: string, scientificName: string, count: number): ShowcaseRow => ({
        key, displayName: key, scientificName, count, photo: null, reference: null, flagged: true
    } as ShowcaseRow);
    const checks = [row('Red Junglefowl', 'Gallus gallus', 8), row('Plateau Striped Whiptail', 'Aspidoscelis velox', 1)];
</script>
<p data-kept-changes>{kept}</p>
<SpeciesChecks
    {checks}
    countLabel={(count) => (count === 1 ? 'visit' : 'visits')}
    nearbyRadiusKm={50}
    onopen={() => {}}
    oncheck={owner ? () => {} : undefined}
    keptBirds={owner ? [{ bird: 'chicken', species: 'Red Junglefowl', declared: false }] : []}
    onkept={() => (kept += 1)}
/>
<Toast />
