<script lang="ts">
    import { _ } from 'svelte-i18n';

    /** A null figure has not been measured: it is never shown as zero. */
    interface Props {
        visitCount: number | null;
        countedBirds: number;
        countedCaptures: number;
        speciesCount: number | null;
        unresolvedCount: number | null;
        audioCalls: number | null;
        audioConfirmations: number;
        connected: boolean;
        /** Unmeasured figures are still being read, rather than unavailable. */
        loading?: boolean;
    }

    let {
        visitCount,
        countedBirds,
        countedCaptures,
        speciesCount,
        unresolvedCount,
        audioCalls,
        audioConfirmations,
        connected,
        loading = false
    }: Props = $props();
</script>

{#snippet unmeasured()}
    {#if loading}
        <span class="inline-block h-3.5 w-5 translate-y-0.5 rounded bg-slate-200 animate-pulse motion-reduce:animate-none dark:bg-slate-700" aria-hidden="true" data-loading-placeholder></span>
        <span class="sr-only">{$_('dashboard.day_bar.loading', { default: 'still loading' })}</span>
    {:else}
        <span aria-hidden="true">–</span>
        <span class="sr-only">{$_('dashboard.day_bar.unavailable', { default: 'not available' })}</span>
    {/if}
{/snippet}

<div
    class="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-slate-200/70 pb-3 dark:border-slate-700/50"
    data-dashboard-day-bar
>
    <h1 class="font-display text-lg font-bold text-slate-950 dark:text-white">
        {$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}
    </h1>

    <dl class="flex flex-wrap items-baseline gap-x-4 gap-y-1.5 text-xs sm:gap-x-5 sm:gap-y-2">
        <div class="flex items-baseline gap-1.5">
            <dd class="font-display text-base font-bold tabular-nums text-slate-900 dark:text-white">
                {#if visitCount === null}{@render unmeasured()}{:else}{visitCount}{/if}
            </dd>
            <dt class="text-slate-500 dark:text-slate-400">
                {$_('dashboard.day_bar.visits', { default: 'visits' })}
            </dt>
        </div>
        {#if countedCaptures > 0}
            <div class="flex items-baseline gap-1.5" title={$_('dashboard.day_bar.birds_scope', { values: { count: countedCaptures }, default: 'From {count} analyzed captures; birds may be missed' })} data-day-bar-counted-birds>
                <dd class="font-display text-base font-bold tabular-nums text-slate-900 dark:text-white">{countedBirds}</dd>
                <dt class="text-slate-500 dark:text-slate-400">{$_('dashboard.day_bar.birds_found', { default: 'birds found' })}<span class="sr-only">. {$_('dashboard.day_bar.birds_scope', { values: { count: countedCaptures }, default: 'From {count} analyzed captures; birds may be missed' })}</span></dt>
            </div>
        {/if}
        <div class="flex items-baseline gap-1.5">
            <dd class="font-display text-base font-bold tabular-nums text-slate-900 dark:text-white">
                {#if speciesCount === null}{@render unmeasured()}{:else}{speciesCount}{/if}
            </dd>
            <dt class="text-slate-500 dark:text-slate-400">
                {$_('dashboard.stats.species')}
            </dt>
        </div>
        <div class="flex items-baseline gap-1.5" data-day-bar-unresolved>
            <dd
                class="font-display text-base font-bold tabular-nums {unresolvedCount !== null && unresolvedCount > 0
                    ? 'text-accent-700 dark:text-accent-300'
                    : 'text-slate-900 dark:text-white'}"
            >
                {#if unresolvedCount === null}{@render unmeasured()}{:else}{unresolvedCount}{/if}
            </dd>
            <dt class="text-slate-500 dark:text-slate-400">
                {$_('dashboard.day_bar.unresolved', { default: 'unresolved' })}
            </dt>
        </div>
        {#if audioCalls !== null}
            <div class="flex items-baseline gap-1.5">
                <dd class="font-display text-base font-bold tabular-nums text-slate-900 dark:text-white">
                    {audioCalls}
                </dd>
                <dt class="text-slate-500 dark:text-slate-400">
                    {$_('dashboard.day_bar.calls_heard', { default: 'calls heard' })}
                </dt>
            </div>
            <div class="flex items-baseline gap-1.5">
                <dd
                    class="font-display text-base font-bold tabular-nums {audioConfirmations === 0
                        ? 'text-accent-700 dark:text-accent-300'
                        : 'text-slate-900 dark:text-white'}"
                >
                    {audioConfirmations}
                </dd>
                <dt class="text-slate-500 dark:text-slate-400">
                    {$_('dashboard.day_bar.cross_confirmed', { default: 'cross-confirmed' })}
                </dt>
            </div>
        {/if}
    </dl>

    <p class="flex items-center gap-1.5 text-xs font-semibold sm:ml-auto">
        <span
            class="h-1.5 w-1.5 rounded-full {connected
                ? 'bg-success-500'
                : 'bg-slate-400 dark:bg-slate-500'}"
            aria-hidden="true"
        ></span>
        <span class={connected ? 'text-success-700 dark:text-success-300' : 'text-slate-500 dark:text-slate-400'}>
            {connected
                ? $_('dashboard.live_feed')
                : $_('dashboard.day_bar.reconnecting', { default: 'Reconnecting…' })}
        </span>
    </p>
</div>
