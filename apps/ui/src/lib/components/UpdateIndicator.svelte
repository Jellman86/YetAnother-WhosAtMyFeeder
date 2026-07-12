<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { updateStatusStore } from '../stores/update_status.svelte';

    onMount(() => {
        updateStatusStore.load();
    });

    let label = $derived(
        $_('update_banner.sidebar_title', {
            values: { version: updateStatusStore.latestVersion },
            default: `Update available: ${updateStatusStore.latestVersion}`
        })
    );
</script>

{#if updateStatusStore.updateAvailable}
    <a
        href={updateStatusStore.status?.release_url}
        target="_blank"
        rel="noopener noreferrer"
        class="relative flex items-center justify-center rounded-lg p-1 text-teal-600 transition-all duration-200 hover:bg-teal-50 focus-ring dark:text-teal-400 dark:hover:bg-teal-950/40"
        title={label}
        aria-label={label}
    >
        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 10.5 12 6.75l3.75 3.75M12 6.75v10.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
        <span class="absolute right-0 top-0 flex h-1.5 w-1.5">
            <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-400 opacity-75"></span>
            <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-teal-500"></span>
        </span>
    </a>
{/if}
