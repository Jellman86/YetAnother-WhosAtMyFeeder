<script lang="ts">
    import { _ } from 'svelte-i18n';

    let {
        birdnetEnabled = false,
        notificationsActive = null,
        connected = false
    }: {
        birdnetEnabled?: boolean;
        /** Null when unread, as for a guest: the tile is left out rather than guessed. */
        notificationsActive?: boolean | null;
        connected?: boolean;
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
        ...(notificationsActive === null
            ? []
            : [{
                key: 'alerts',
                on: notificationsActive,
                short: $_('status.tile_alerts', { default: 'Alerts' }),
                name: $_('status.notifications'),
                state: notificationsActive ? $_('common.enabled') : $_('common.disabled'),
                onClass: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-300',
                icon: 'M15 17h5l-1.4-1.4a2 2 0 0 1-.6-1.4V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0m6 0H9'
            }])
    ]);
</script>

<!--
    Three tiles rather than three sentences: an icon and a one-word name each. The state is in
    the icon itself (a slash through it when off) as well as its colour, and the full sentence
    is the tile's tooltip and its screen-reader text.
-->
<ul class="grid {tiles.length === 3 ? 'grid-cols-3' : 'grid-cols-2'} gap-1.5" role="status" aria-live="polite" data-status-tiles>
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
            <span class="text-xs font-semibold {tile.on ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400 dark:text-slate-500'}" aria-hidden="true">{tile.short}</span>
            <span class="sr-only">{tile.name}: {tile.state}</span>
        </li>
    {/each}
</ul>
