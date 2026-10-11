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

<!-- The window, then every figure for it in one ruled band. Labels sit above their figures so a
     row of six reads across like a ledger; each figure names its scope beneath when it has one. -->
<div class="space-y-4" data-dashboard-day-bar>
    <div class="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div class="space-y-1">
            <p class="eyebrow">{$_('nav.dashboard')}</p>
            <h1 class="font-display text-3xl font-bold leading-tight text-slate-950 sm:text-4xl dark:text-white">
                {$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}
            </h1>
        </div>

        <p class="flex items-center gap-2 text-sm font-semibold">
            <span
                class="h-2 w-2 rounded-full {connected
                    ? 'bg-success-500 ring-4 ring-success-500/20'
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

    <dl class="card-base grid grid-cols-2 gap-px overflow-hidden sm:grid-cols-3 xl:auto-cols-fr xl:grid-flow-col xl:grid-cols-none xl:divide-x xl:divide-line-soft">
        {#snippet figure(label: string, value: number | null, tone: 'plain' | 'attention' | 'clear' = 'plain', note: string = '', title: string = '', hook: string = '')}
            <div class="flex min-w-0 flex-col gap-1.5 px-5 py-4" {title} data-day-bar-figure={hook || undefined}>
                <dt class="text-sm text-slate-600 first-letter:uppercase dark:text-slate-400">{label}</dt>
                <dd class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <span
                        class="figure text-3xl {tone === 'attention'
                            ? 'text-accent-700 dark:text-accent-300'
                            : 'text-slate-950 dark:text-white'}"
                    >
                        {#if value === null}{@render unmeasured()}{:else}{value}{/if}
                    </span>
                    {#if note && value !== null}
                        <span class="text-xs {tone === 'clear' ? 'text-success-700 dark:text-success-300' : 'text-slate-500 dark:text-slate-400'}">{note}</span>
                    {/if}
                </dd>
            </div>
        {/snippet}

        {@render figure($_('dashboard.day_bar.visits', { default: 'visits' }), visitCount)}
        {#if countedCaptures > 0}
            {@render figure(
                $_('dashboard.day_bar.birds_found', { default: 'birds found' }),
                countedBirds,
                'plain',
                $_('dashboard.day_bar.birds_scope_short', { values: { count: countedCaptures }, default: 'from {count} analyzed captures' }),
                $_('dashboard.day_bar.birds_scope', { values: { count: countedCaptures }, default: 'From {count} analyzed captures; birds may be missed' }),
                'counted-birds'
            )}
        {/if}
        {@render figure($_('dashboard.stats.species'), speciesCount)}
        {@render figure(
            $_('dashboard.day_bar.unresolved', { default: 'unresolved' }),
            unresolvedCount,
            unresolvedCount !== null && unresolvedCount > 0 ? 'attention' : 'clear',
            unresolvedCount === 0 ? $_('dashboard.day_bar.nothing_to_review', { default: 'nothing to review' }) : '',
            '',
            'unresolved'
        )}
        {#if audioCalls !== null}
            {@render figure($_('dashboard.day_bar.calls_heard', { default: 'calls heard' }), audioCalls)}
            {@render figure(
                $_('dashboard.day_bar.cross_confirmed', { default: 'cross-confirmed' }),
                audioConfirmations,
                audioConfirmations === 0 ? 'attention' : 'plain',
                $_('dashboard.day_bar.seen_and_heard', { default: 'seen and heard' })
            )}
        {/if}
    </dl>
</div>
