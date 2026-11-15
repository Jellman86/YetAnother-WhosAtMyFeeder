<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { updateStatusStore } from '../stores/update_status.svelte';

    onMount(() => {
        updateStatusStore.load();
    });

    let { collapsed = false }: { collapsed?: boolean } = $props();

    let label = $derived(
        $_('update_banner.sidebar_title', {
            values: { version: updateStatusStore.latestVersion },
            default: `Update available: ${updateStatusStore.latestVersion}`
        })
    );
</script>

<!-- A row of the status list's own kind: the words say what it is, in the icon rail as its name. -->
{#if updateStatusStore.updateAvailable}
    <a
        href={updateStatusStore.status?.release_url}
        target="_blank"
        rel="noopener noreferrer"
        class={collapsed
            ? 'focus-ring mx-auto grid h-11 w-11 place-items-center rounded-lg text-brand-700 transition-colors hover:bg-brand-50 dark:text-brand-300 dark:hover:bg-brand-950/40'
            : 'focus-ring mt-1.5 flex min-h-7 items-center gap-2 rounded-md text-xs font-semibold leading-4 text-brand-700 transition-colors hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200'}
        title={collapsed ? label : undefined}
        aria-label={collapsed ? label : undefined}
        data-update-indicator
    >
        <svg class={collapsed ? 'h-5 w-5' : 'h-3 w-3 shrink-0'} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 10.5 12 6.75l3.75 3.75M12 6.75v10.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
        {#if !collapsed}
            <span class="min-w-0 wrap-break-word">{label}</span>
        {/if}
    </a>
{/if}
