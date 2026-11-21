<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Snippet } from 'svelte';
    import AddObservationLink from './AddObservationLink.svelte';
    import CameraStatus from './CameraStatus.svelte';
    import NotificationCenter from './NotificationCenter.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import PageHeader from './ui/PageHeader.svelte';
    import type { AddObservationEntry } from '../app/add-observation';

    type Props = {
        /** Omitted where the page brings its own h1, as the Dashboard's day bar does. */
        title?: string;
        subtitle?: string;
        onNavigate?: (path: string) => void;
        onPrefetch?: (path: string) => void;
        actions?: Snippet;
        /** The owner's page controls. A guest can use none of them. */
        showOwnerActions?: boolean;
        notificationsCurrent?: boolean;
        /** The page registers a refresh once it loads: hold the control's place until then. */
        refreshExpected?: boolean;
        /** Whether the header offers the owner Add observation, and whether this is that page. */
        addObservation?: AddObservationEntry;
    };

    let {
        title,
        subtitle,
        onNavigate,
        onPrefetch,
        actions,
        showOwnerActions = true,
        notificationsCurrent = false,
        refreshExpected = false,
        addObservation = { inHeader: false, inMenu: false, current: false }
    }: Props = $props();

    function goSettings() {
        onNavigate?.('/settings');
    }
</script>

<!-- The shell's header: the page's title from the shared PageHeader, and the owner's page controls
     beside it. The Dashboard brings its own h1 (its day bar), so there the controls stand alone. -->
{#snippet controls()}
    {#if actions}
        {@render actions()}
    {:else if showOwnerActions}
        {#if pageRefreshAction.available || refreshExpected}
            <!-- Disabled until the page has loaded and can be refreshed. -->
            <button
                type="button"
                onclick={() => void pageRefreshAction.run()}
                disabled={!pageRefreshAction.available || pageRefreshAction.refreshing}
                class="grid min-h-11 min-w-11 place-items-center rounded-xl text-muted transition-colors duration-200 hover:bg-surface-raised hover:text-strong focus-ring disabled:opacity-60 disabled:cursor-wait"
                title={$_('common.refresh')}
                aria-label={$_('common.refresh')}
                aria-busy={pageRefreshAction.refreshing}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 {pageRefreshAction.refreshing ? 'animate-spin' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
            </button>
        {/if}
        <!-- After Refresh, which comes and goes with the page, so this keeps one place on every page. -->
        {#if addObservation.inHeader}
            <AddObservationLink variant="icon" current={addObservation.current} {onNavigate} {onPrefetch} />
        {/if}
        <CameraStatus />
        <NotificationCenter
            current={notificationsCurrent}
            onNavigate={(path) => onNavigate?.(path)}
            buttonClass="relative grid min-h-11 min-w-11 place-items-center rounded-xl text-muted transition-colors duration-200 hover:bg-surface-raised hover:text-strong focus-ring"
        />
        <button
            type="button"
            onclick={goSettings}
            class="grid min-h-11 min-w-11 place-items-center rounded-xl text-muted transition-colors duration-200 hover:bg-surface-raised hover:text-strong focus-ring"
            title={$_('nav.settings')}
            aria-label={$_('nav.settings')}
        >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
        </button>
    {/if}
{/snippet}

{#if title}
    <PageHeader {title} {subtitle} actions={controls} />
{:else}
    <header class="mb-2 flex justify-end">
        <div class="ml-auto flex max-w-full flex-wrap items-center justify-end gap-1">
            {@render controls()}
        </div>
    </header>
{/if}
