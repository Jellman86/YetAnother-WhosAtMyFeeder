<script lang="ts">
    import DetectionCard from '../src/lib/components/DetectionCard.svelte';
    import DetectionRow from '../src/lib/components/DetectionRow.svelte';
    import DetectionModal from '../src/lib/components/DetectionModal.svelte';
    import SettingsSegmented from '../src/lib/components/settings/_primitives/SettingsSegmented.svelte';
    import Toast from '../src/lib/components/Toast.svelte';
    import { toastStore } from '../src/lib/stores/toast.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import type { Detection } from '../src/lib/api';

    // One score drawn by every surface that shows it: the Explorer card, the list row and the
    // record. The spec supplies the HTTP boundary and switches the colour theme on <html>.
    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.isAuthenticated = true;
    const params = new URLSearchParams(location.search);
    const scores = [0.55, 0.62, 0.81, 0.94];

    function capture(score: number): Detection {
        return {
            frigate_event: `score-${Math.round(score * 100)}`,
            display_name: 'Dunnock',
            common_name: 'Dunnock',
            camera_name: 'birdcam',
            detection_time: '2026-10-01T12:00:00Z',
            score
        };
    }

    const recordScore = Number(params.get('record'));
    let chosen = $state<'cards' | 'list'>('cards');
    if (params.has('toasts')) {
        toastStore.show('Saved', 'success', 0);
        toastStore.show('Check the camera', 'warning', 0);
    }
</script>

<div class="space-y-6 p-4">
    <div class="grid grid-cols-2 gap-4">
        {#each scores as score (score)}
            <div data-surface="card" data-score={score}><DetectionCard detection={capture(score)} /></div>
        {/each}
    </div>
    <div class="card-base">
        {#each scores as score (score)}
            <div data-surface="row" data-score={score}><DetectionRow detection={capture(score)} /></div>
        {/each}
    </div>
    <div data-surface="chosen">
        <SettingsSegmented
            value={chosen}
            options={[{ value: 'cards', label: 'Cards' }, { value: 'list', label: 'List' }]}
            onchange={(next) => (chosen = next)}
            ariaLabelTemplate={(label) => label}
        />
        <button type="button" class="btn btn-primary min-h-11 px-4" data-primary-button>Apply</button>
    </div>
</div>
{#if Number.isFinite(recordScore) && recordScore > 0}
    <DetectionModal
        detection={capture(recordScore)}
        classifierLabels={[]}
        llmReady={false}
        showVideoButton={false}
        onClose={() => {}}
        onViewSpecies={() => {}}
    />
{/if}
<Toast />
