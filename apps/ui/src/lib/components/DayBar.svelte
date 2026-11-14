<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { DayBarSlots } from '../utils/day-bar';
    import type { LiveFeedState } from '../utils/live-feed-state';

    /** A null figure has not been measured: it is never shown as zero. */
    interface Props {
        visitCount: number | null;
        countedBirds: number | null;
        countedCaptures: number | null;
        speciesCount: number | null;
        unresolvedCount: number | null;
        /** Other work may wait on a person (a species check), so zero unresolved is not "nothing to review". */
        othersAwaitReview?: boolean;
        audioCalls: number | null;
        audioConfirmations: number | null;
        /** The optional figures, decided from configuration so loading never adds a cell. */
        slots: DayBarSlots;
        /** Only a measured broker session is called live; see live-feed-state.ts. */
        feed: LiveFeedState;
        /** Unmeasured figures are still being read, rather than unavailable. */
        loading?: boolean;
        /** The same for the microphone's reading, which arrives on its own. */
        audioLoading?: boolean;
    }

    let {
        visitCount,
        countedBirds,
        countedCaptures,
        speciesCount,
        unresolvedCount,
        othersAwaitReview = false,
        audioCalls,
        audioConfirmations,
        slots,
        feed,
        loading = false,
        audioLoading = false
    }: Props = $props();

    const feedTone = $derived(feed === 'live' ? 'live' : feed === 'broker_down' || feed === 'frigate_down' ? 'attention' : 'neutral');
    const feedLabel = $derived.by(() => {
        switch (feed) {
            case 'live':
                return $_('dashboard.live_feed');
            case 'connecting':
                return $_('status.feed_connecting', { default: 'Connecting to the MQTT broker' });
            case 'broker_down':
                return $_('status.feed_broker_down', { default: 'Not receiving camera events. The MQTT broker is not connected.' });
            case 'frigate_down':
                return $_('status.feed_frigate_down', { default: 'Frigate is not answering, so new detections cannot be saved' });
            case 'app_only':
                return $_('status.feed_app_only', { default: 'Connected to YA-WAMF' });
            default:
                return $_('dashboard.day_bar.reconnecting', { default: 'Reconnecting…' });
        }
    });
</script>

{#snippet unmeasured(pending: boolean)}
    {#if pending}
        <span class="inline-block h-3.5 w-5 translate-y-0.5 rounded-sm bg-slate-200 animate-pulse motion-reduce:animate-none dark:bg-slate-700" aria-hidden="true" data-loading-placeholder></span>
        <span class="sr-only">{$_('dashboard.day_bar.loading', { default: 'still loading' })}</span>
    {:else}
        <span aria-hidden="true">–</span>
        <span class="sr-only">{$_('dashboard.day_bar.unavailable', { default: 'not available' })}</span>
    {/if}
{/snippet}

<!-- The window, then every figure for it in one ruled band. Labels sit above their figures so a
     row of six reads across like a ledger; each figure names its scope beneath when it has one.
     Columns follow the bar's own width in rem, so a larger text size narrows them as a smaller
     screen does. -->
<div class="day-bar space-y-4" data-dashboard-day-bar>
    <div class="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div class="min-w-0 space-y-1">
            <p class="eyebrow">{$_('nav.dashboard')}</p>
            <h1 class="day-bar-window font-display text-3xl font-bold leading-tight text-slate-950 sm:text-4xl sm:leading-10 dark:text-white">
                {$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}
            </h1>
        </div>

        <p class="flex max-w-full items-center gap-2 text-sm font-semibold" data-day-bar-feed={feed}>
            <span
                class="h-2 w-2 shrink-0 rounded-full {feedTone === 'live'
                    ? 'bg-success-500 ring-4 ring-success-500/20'
                    : feedTone === 'attention'
                      ? 'bg-attention-500 ring-4 ring-attention-500/20'
                      : 'bg-slate-400 dark:bg-slate-500'}"
                aria-hidden="true"
            ></span>
            <span class={feedTone === 'live'
                ? 'text-success-700 dark:text-success-300'
                : feedTone === 'attention'
                  ? 'text-attention-800 dark:text-attention-200'
                  : 'text-slate-600 dark:text-slate-400'}>
                {feedLabel}
            </span>
        </p>
    </div>

    <dl class="day-bar-figures card-base grid overflow-hidden">
        <!-- A figure that carries a note holds its line while it is read, so the note arriving
             does not make the band taller. -->
        {#snippet figure(hook: string, label: string, value: number | null, pending: boolean, tone: 'plain' | 'attention' | 'clear' = 'plain', note: string = '', title: string = '', noted: boolean = false)}
            <div class="flex min-w-0 flex-col gap-1.5 px-5 py-4" {title} data-day-bar-figure={hook}>
                <dt class="wrap-break-word text-sm text-slate-600 first-letter:uppercase dark:text-slate-400">{label}</dt>
                <dd class="flex min-w-0 flex-col gap-1">
                    <span
                        class="figure text-3xl {tone === 'attention'
                            ? 'text-attention-700 dark:text-attention-300'
                            : 'text-slate-950 dark:text-white'}"
                    >
                        {#if value === null}{@render unmeasured(pending)}{:else}{value}{/if}
                    </span>
                    {#if note && value !== null}
                        <span class="min-w-0 wrap-break-word text-xs {tone === 'clear' ? 'text-success-700 dark:text-success-300' : 'text-slate-500 dark:text-slate-400'}">{note}</span>
                    {:else if noted && value === null && pending}
                        <span class="flex h-4 items-center" aria-hidden="true">
                            <span class="h-2.5 w-20 max-w-full rounded-sm bg-slate-200 animate-pulse motion-reduce:animate-none dark:bg-slate-700" data-loading-placeholder></span>
                        </span>
                    {/if}
                </dd>
            </div>
        {/snippet}

        {@render figure('visits', $_('dashboard.day_bar.visits', { default: 'visits' }), visitCount, loading)}
        {#if slots.countedBirds}
            {@render figure(
                'counted-birds',
                $_('dashboard.day_bar.birds_found', { default: 'birds found' }),
                countedBirds,
                loading,
                'plain',
                countedCaptures === null ? '' : $_('dashboard.day_bar.birds_scope_short', { values: { count: countedCaptures }, default: 'from {count, plural, one {# analyzed capture} other {# analyzed captures}}' }),
                countedCaptures === null ? '' : $_('dashboard.day_bar.birds_scope', { values: { count: countedCaptures }, default: 'From {count, plural, one {# analyzed capture} other {# analyzed captures}}; birds may be missed' }),
                true
            )}
        {/if}
        {@render figure('species', $_('dashboard.stats.species'), speciesCount, loading)}
        {@render figure(
            'unresolved',
            $_('dashboard.day_bar.unresolved', { default: 'unresolved' }),
            unresolvedCount,
            loading,
            unresolvedCount !== null && unresolvedCount > 0 ? 'attention' : 'clear',
            unresolvedCount === 0 && !othersAwaitReview ? $_('dashboard.day_bar.nothing_to_review', { default: 'nothing to review' }) : '',
            '',
            true
        )}
        {#if slots.audio}
            {@render figure('calls-heard', $_('dashboard.day_bar.calls_heard', { default: 'calls heard' }), audioCalls, audioLoading)}
            {@render figure(
                'cross-confirmed',
                $_('dashboard.day_bar.cross_confirmed', { default: 'cross-confirmed' }),
                audioConfirmations,
                loading,
                'plain',
                $_('dashboard.day_bar.seen_and_heard', { default: 'seen and heard' }),
                '',
                true
            )}
        {/if}
    </dl>
</div>

<style>
    /* Measured in rem against the bar itself: the same screen at a larger text size is a narrower
       bar, and the figures step down to fewer columns rather than clipping their labels. */
    .day-bar {
        container-type: inline-size;
    }

    .day-bar-figures {
        grid-template-columns: minmax(0, 1fr);
    }

    .day-bar-figures > div + div {
        border-top: 1px solid rgb(var(--line-soft));
    }

    @container (width < 16rem) {
        .day-bar-window {
            font-size: 1.5rem;
            line-height: 2rem;
        }
    }

    @container (width >= 16rem) {
        .day-bar-figures {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }

        .day-bar-figures > div + div {
            border-top: 0;
        }
    }

    @container (width >= 30rem) {
        .day-bar-figures {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
    }

    /* Wide enough for every figure in one ruled row. */
    @container (width >= 56rem) {
        .day-bar-figures {
            grid-template-columns: none;
            grid-auto-columns: minmax(0, 1fr);
            grid-auto-flow: column;
        }

        .day-bar-figures > div + div {
            border-left: 1px solid rgb(var(--line-soft));
        }
    }
</style>
