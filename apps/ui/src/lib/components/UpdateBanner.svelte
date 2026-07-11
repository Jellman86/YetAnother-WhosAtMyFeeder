<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { shouldShowUpdateBanner } from '../api';
    import { updateStatusStore } from '../stores/update_status.svelte';

    // Keyed on the version so dismissing one update doesn't hide a later, newer one.
    const DISMISSED_KEY = 'update-banner-dismissed-version';

    let status = $derived(updateStatusStore.status);
    let dismissedVersion = $state<string | null>(null);

    let visible = $derived(shouldShowUpdateBanner(status, dismissedVersion));
    let currentDisplay = $derived((status?.current_version ?? '').split('+')[0]);

    onMount(() => {
        dismissedVersion = localStorage.getItem(DISMISSED_KEY);
        updateStatusStore.load();
    });

    function dismiss() {
        if (status?.latest_version) {
            dismissedVersion = status.latest_version;
            localStorage.setItem(DISMISSED_KEY, status.latest_version);
        }
    }
</script>

{#if visible && status}
    <div class="border-b border-teal-200/60 bg-gradient-to-r from-teal-50 via-emerald-50 to-white dark:border-teal-900/40 dark:from-teal-950/30 dark:via-emerald-950/20 dark:to-slate-950/40">
        <div class="mx-auto max-w-7xl px-4 py-3 sm:px-6 lg:px-8">
            <div class="flex items-start gap-3">
                <div class="mt-0.5 flex-shrink-0">
                    <svg class="h-5 w-5 text-teal-600 dark:text-teal-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16l-4-4m0 0l4-4m-4 4h18" transform="rotate(90 12 12)" />
                    </svg>
                </div>
                <div class="min-w-0 flex-1 text-sm text-teal-900 dark:text-teal-100">
                    {#if status.channel === 'dev'}
                        <span class="font-semibold">{$_('update_banner.title_dev', { values: { version: status.latest_version }, default: `A newer dev build is available (${status.latest_version})` })}</span>
                    {:else}
                        <span class="font-semibold">{$_('update_banner.title', { values: { version: status.latest_version }, default: `YA-WAMF ${status.latest_version} is available` })}</span>
                    {/if}
                    <span class="ml-1 opacity-90">{$_('update_banner.body', { values: { current: currentDisplay }, default: `You're running ${currentDisplay}. Pull the new image from your container manager to update.` })}</span>
                    <a href={status.release_url} target="_blank" rel="noopener noreferrer" class="ml-1 font-black underline underline-offset-2 hover:opacity-80">
                        {$_('update_banner.release_notes', { default: 'Release notes →' })}
                    </a>
                </div>
                <button
                    type="button"
                    onclick={dismiss}
                    class="ml-2 shrink-0 rounded-md p-1 text-teal-700 hover:bg-teal-100/60 dark:text-teal-300 dark:hover:bg-teal-900/40"
                    aria-label={$_('update_banner.dismiss', { default: 'Dismiss' })}
                >
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
        </div>
    </div>
{/if}
