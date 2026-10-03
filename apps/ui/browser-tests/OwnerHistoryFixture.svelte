<script lang="ts">
    import { onMount } from 'svelte';
    import { initKeyboardShortcuts } from '../src/lib/utils/keyboard-shortcuts';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';
    import Events from '../src/lib/pages/Events.svelte';
    import SpeciesDetailModal from '../src/lib/components/SpeciesDetailModal.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { settingsStore } from '../src/lib/stores/settings.svelte';

    // Real pages own loading and controls; the spec supplies the HTTP boundary.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.isAuthenticated = true;
    settingsStore.settings = { enrichment_summary_provider: 'disabled' } as unknown as NonNullable<typeof settingsStore.settings>;
    const params = new URLSearchParams(location.search);
    const surface = params.get('surface');
    // The app's global Escape handler must not consume native capture-panel dismissal.
    onMount(() => initKeyboardShortcuts({ Escape: () => {} }));
    if (params.get('theme') === 'dark') document.documentElement.classList.add('dark');
</script>

{#if surface === 'species'}
    <SpeciesDetailModal speciesName="Cyanistes caeruleus" onclose={() => {}} />
{:else}
    <button class="btn btn-secondary" onclick={() => detectionsStore.addDetection({ frigate_event: 'incoming', display_name: 'Turdus merula', scientific_name: 'Turdus merula', camera_name: 'birdcam', detection_time: new Date().toISOString(), score: 0.95 })}>Notify new capture</button>
    <Events />
{/if}
