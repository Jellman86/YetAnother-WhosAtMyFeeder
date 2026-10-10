<script lang="ts">
    import SpeciesCheckSheet from '../src/lib/components/SpeciesCheckSheet.svelte';
    import Toast from '../src/lib/components/Toast.svelte';
    let open = $state(true);
    let changes = $state(0);
    const checks = [
        { key: 'Brown-headed Cowbird', displayName: 'Brown-headed Cowbird', scientificName: 'Molothrus ater' },
        { key: 'Eastern Gray Squirrel', displayName: 'Eastern Gray Squirrel', scientificName: 'Sciurus carolinensis' },
        { key: 'Plateau Striped Whiptail', displayName: 'Plateau Striped Whiptail', scientificName: 'Aspidoscelis velox' }
    ];
</script>
<h1>Leaderboard</h1>
<p data-check-changes>{changes}</p>
<button type="button" onclick={() => (open = true)}>Open checks</button>
{#if open}
    <SpeciesCheckSheet {checks} startKey="Brown-headed Cowbird" window={{ start: '2026-09-10T00:00:00Z', end: '2026-10-10T00:00:00Z' }} nearbyRadiusKm={50} onclose={() => (open = false)} onchanged={() => (changes += 1)} />
{/if}
<Toast />
