<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        visitCount: number;
        speciesCount: number;
        unresolvedCount: number;
        audioCalls: number | null;
        audioConfirmations: number;
        connected: boolean;
    }

    let {
        visitCount,
        speciesCount,
        unresolvedCount,
        audioCalls,
        audioConfirmations,
        connected
    }: Props = $props();
</script>

<div
    class="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-slate-200/70 pb-3 dark:border-slate-700/50"
    data-dashboard-day-bar
>
    <h1 class="font-display text-lg font-bold text-slate-950 dark:text-white">
        {$_('dashboard.day_bar.today', { default: 'Today' })}
    </h1>

    <dl class="flex flex-wrap items-baseline gap-x-5 gap-y-2 text-xs">
        <div class="flex items-baseline gap-1.5">
            <dd class="font-display text-base font-bold tabular-nums text-slate-900 dark:text-white">
                {visitCount}
            </dd>
            <dt class="text-slate-500 dark:text-slate-400">
                {$_('dashboard.day_bar.visits', { default: 'visits' })}
            </dt>
        </div>
        <div class="flex items-baseline gap-1.5">
            <dd class="font-display text-base font-bold tabular-nums text-slate-900 dark:text-white">
                {speciesCount}
            </dd>
            <dt class="text-slate-500 dark:text-slate-400">
                {$_('dashboard.stats.species')}
            </dt>
        </div>
        <div class="flex items-baseline gap-1.5" data-day-bar-unresolved>
            <dd
                class="font-display text-base font-bold tabular-nums {unresolvedCount > 0
                    ? 'text-accent-700 dark:text-accent-300'
                    : 'text-slate-900 dark:text-white'}"
            >
                {unresolvedCount}
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

    <p class="ml-auto flex items-center gap-1.5 text-xs font-semibold">
        <span
            class="h-1.5 w-1.5 rounded-full {connected
                ? 'bg-emerald-500'
                : 'bg-slate-400 dark:bg-slate-500'}"
            aria-hidden="true"
        ></span>
        <span class={connected ? 'text-emerald-700 dark:text-emerald-300' : 'text-slate-500 dark:text-slate-400'}>
            {connected
                ? $_('dashboard.live_feed')
                : $_('dashboard.day_bar.reconnecting', { default: 'Reconnecting…' })}
        </span>
    </p>
</div>
