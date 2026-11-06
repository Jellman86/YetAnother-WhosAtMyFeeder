<script lang="ts">
    import { onMount } from 'svelte';
    import { initKeyboardShortcuts } from '../src/lib/utils/keyboard-shortcuts';
    import { gardenHistory } from '../src/lib/stores/garden_history.svelte';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';
    import Events from '../src/lib/pages/Events.svelte';
    import SpeciesDetailModal from '../src/lib/components/SpeciesDetailModal.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { settingsStore } from '../src/lib/stores/settings.svelte';
    import Toast from '../src/lib/components/Toast.svelte';

    // Real pages own loading and controls; the spec supplies the HTTP boundary.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    const params = new URLSearchParams(location.search);
    // guest=1: a public visitor while the owner has Garden animals on; visitors never read settings.
    const guest = params.get('guest') === '1';
    authStore.isAuthenticated = !guest;
    authStore.publicAccessEnabled = guest;
    authStore.gardenAnimalsEnabled = guest;
    // garden=1: the owner has the Garden beta on for one camera, or for those gardencams lists.
    // garden=0: switched off, as a saved setting says it.
    const gardenCameras = params.get('gardencams')?.split(',').filter(Boolean) ?? ['patio'];
    const garden = params.get('garden') === '1' ? { beta_garden_animals: true, garden_cameras: gardenCameras } : params.get('garden') === '0' ? { beta_garden_animals: false } : {};
    if (!guest) settingsStore.settings = { enrichment_summary_provider: 'disabled', ...garden } as unknown as NonNullable<typeof settingsStore.settings>;
    const surface = params.get('surface');
    // The app's global Escape handler must not consume native capture-panel dismissal.
    onMount(() => {
        const releaseShortcuts = initKeyboardShortcuts({ Escape: () => {} });
        const invalidateGarden = () => gardenHistory.invalidate();
        window.addEventListener('fixture-garden-change', invalidateGarden);
        return () => {
            releaseShortcuts();
            window.removeEventListener('fixture-garden-change', invalidateGarden);
        };
    });
    if (params.get('theme') === 'dark') document.documentElement.classList.add('dark');
</script>

{#if surface === 'species'}
    <SpeciesDetailModal speciesName="Cyanistes caeruleus" onclose={() => {}} />
{:else}
    <button class="btn btn-secondary" onclick={() => detectionsStore.addDetection({ frigate_event: 'incoming', display_name: 'Turdus merula', scientific_name: 'Turdus merula', camera_name: 'birdcam', detection_time: new Date().toISOString(), score: 0.95 })}>Notify new capture</button>
    <Events />
{/if}
<!-- Garden review announces each saved decision; the app shell normally provides this. -->
{#if params.get('garden') === '1'}<Toast />{/if}
