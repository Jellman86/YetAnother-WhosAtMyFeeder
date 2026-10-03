<script lang="ts">
    import { _ } from 'svelte-i18n';

    let {
        birdnetEnabled = false,
        notificationsActive = false,
        connected = false,
        className = 'gap-4',
        variant = 'compact'
    }: {
        birdnetEnabled?: boolean;
        notificationsActive?: boolean;
        connected?: boolean;
        className?: string;
        variant?: 'compact' | 'sidebar';
    } = $props();

    const tiles = $derived([
        {
            key: 'live',
            on: connected,
            short: $_('status.tile_live', { default: 'Live' }),
            name: $_('status.live_updates'),
            state: connected ? $_('status.online') : $_('status.offline'),
            onClass: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-300',
            icon: 'M5.6 18.4a9 9 0 0 1 0-12.8M18.4 5.6a9 9 0 0 1 0 12.8M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7M12 12h.01'
        },
        {
            key: 'audio',
            on: birdnetEnabled,
            short: $_('status.tile_audio', { default: 'Audio' }),
            name: $_('status.audio_analysis'),
            state: birdnetEnabled ? $_('common.enabled') : $_('common.disabled'),
            onClass: 'bg-brand-500/15 text-brand-600 dark:text-brand-300',
            icon: 'M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zM19 11a7 7 0 0 1-14 0M12 18v3'
        },
        {
            key: 'alerts',
            on: notificationsActive,
            short: $_('status.tile_alerts', { default: 'Alerts' }),
            name: $_('status.notifications'),
            state: notificationsActive ? $_('common.enabled') : $_('common.disabled'),
            onClass: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-300',
            icon: 'M15 17h5l-1.4-1.4a2 2 0 0 1-.6-1.4V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0m6 0H9'
        }
    ]);
</script>

{#if variant === 'sidebar'}
    <!--
        Three tiles rather than three sentences: an icon and a one-word name each. The state is in
        the icon itself (a slash through it when off) as well as its colour, and the full sentence
        is the tile's tooltip and its screen-reader text.
    -->
    <ul class="grid grid-cols-3 gap-1.5" role="status" aria-live="polite" data-status-tiles>
        {#each tiles as tile (tile.key)}
            <li
                class="flex flex-col items-center gap-1 rounded-lg py-1.5"
                title={`${tile.name}: ${tile.state}`}
                data-status-tile={tile.key}
                data-status-on={tile.on}
            >
                <span class="relative grid h-8 w-8 place-items-center rounded-full {tile.on ? tile.onClass : 'bg-slate-200/70 text-slate-400 dark:bg-slate-700/50 dark:text-slate-500'}">
                    {#if tile.key === 'live' && tile.on}
                        <span class="absolute inset-0 animate-ping rounded-full bg-emerald-400/20" aria-hidden="true"></span>
                    {/if}
                    <svg class="relative h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d={tile.icon} />
                        {#if !tile.on}<path d="M4 4l16 16" />{/if}
                    </svg>
                </span>
                <span class="text-[0.625rem] font-semibold {tile.on ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'}" aria-hidden="true">{tile.short}</span>
                <span class="sr-only">{tile.name}: {tile.state}</span>
            </li>
        {/each}
    </ul>
{:else}
    <div class={`flex items-center ${className}`}>
        {#if birdnetEnabled}
            <div class="group relative flex cursor-help items-center justify-center text-brand-500 dark:text-brand-400" title={$_('status.audio_active')}>
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-20"></span>
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
            </div>
        {/if}

        {#if notificationsActive}
            <div class="relative flex cursor-help items-center justify-center text-indigo-500 dark:text-indigo-400" title={$_('status.notifications_enabled')}>
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h6m-6 8 4-4h6a4 4 0 0 0 4-4V7a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v9a4 4 0 0 0 4 4z" /></svg>
            </div>
        {/if}

        <div class="flex cursor-help items-center gap-2" title={connected ? $_('status.system_online') : $_('status.system_offline')}>
            {#if connected}
                <div class="relative flex items-center justify-center text-accent-500 dark:text-accent-400">
                    <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-20"></span>
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
                </div>
            {:else}
                <div class="relative flex items-center justify-center text-red-500">
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </div>
            {/if}
        </div>
    </div>
{/if}
