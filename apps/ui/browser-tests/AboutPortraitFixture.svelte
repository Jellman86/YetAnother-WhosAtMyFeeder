<script lang="ts">
    import About from '../src/lib/pages/About.svelte';
    import { authStore } from '../src/lib/stores/auth.svelte';
    import { detectionsStore } from '../src/lib/stores/detections.svelte';

    authStore.statusLoaded = true;
    authStore.statusHealthy = true;
    authStore.authRequired = true;
    authStore.publicAccessEnabled = true;
    authStore.isAuthenticated = false;

    let mounted = $state(true);
    window.aboutPortrait = {
        invalidate() { detectionsStore.publicHistoryVersion += 1; },
        setMounted(value) { mounted = value; }
    };
</script>

<main class="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
    {#if mounted}<About />{/if}
</main>
