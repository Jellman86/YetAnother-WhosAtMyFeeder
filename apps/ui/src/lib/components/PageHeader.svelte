<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Snippet } from 'svelte';
    import CameraStatus from './CameraStatus.svelte';
    import NotificationCenter from './NotificationCenter.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';

    type Props = {
        title: string;
        subtitle?: string;
        onNavigate?: (path: string) => void;
        actions?: Snippet;
    };

    let { title, subtitle, onNavigate, actions }: Props = $props();

    function goSettings() {
        onNavigate?.('/settings');
    }
</script>

<header class="mb-6 flex items-start justify-between gap-4">
    <div class="min-w-0 flex-1 space-y-1">
        <h1 class="font-display text-3xl font-bold leading-tight text-slate-900 sm:text-4xl dark:text-white">{title}</h1>
        {#if subtitle}
            <p class="text-base text-slate-600 dark:text-slate-400">{subtitle}</p>
        {/if}
    </div>
    <div class="flex items-center gap-1 shrink-0">
        {#if actions}
            {@render actions()}
        {:else}
            {#if pageRefreshAction.available}
                <button
                    type="button"
                    onclick={() => void pageRefreshAction.run()}
                    disabled={pageRefreshAction.refreshing}
                    class="grid min-h-11 min-w-11 place-items-center rounded-xl text-slate-500 transition-colors duration-200 hover:bg-surface-raised hover:text-slate-900 focus-ring dark:text-slate-400 dark:hover:text-white disabled:opacity-60 disabled:cursor-wait"
                    title={$_('common.refresh')}
                    aria-label={$_('common.refresh')}
                    aria-busy={pageRefreshAction.refreshing}
                >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 {pageRefreshAction.refreshing ? 'animate-spin' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            {/if}
            <CameraStatus />
            <NotificationCenter
                onNavigate={(path) => onNavigate?.(path)}
                buttonClass="relative grid min-h-11 min-w-11 place-items-center rounded-xl text-slate-500 transition-colors duration-200 hover:bg-surface-raised hover:text-slate-900 focus-ring dark:text-slate-400 dark:hover:text-white"
            />
            <button
                type="button"
                onclick={goSettings}
                class="grid min-h-11 min-w-11 place-items-center rounded-xl text-slate-500 transition-colors duration-200 hover:bg-surface-raised hover:text-slate-900 focus-ring dark:text-slate-400 dark:hover:text-white"
                title={$_('nav.settings')}
                aria-label={$_('nav.settings')}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
            </button>
        {/if}
    </div>
</header>
