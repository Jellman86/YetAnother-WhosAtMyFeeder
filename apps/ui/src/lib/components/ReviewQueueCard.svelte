<script lang="ts">
    import { getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { reviewReasonMessage, type ReviewQueue } from '../utils/review-queue';
    import MediaImage from './MediaImage.svelte';
    import { formatDate, formatTime } from '../utils/datetime';
    import { needsYourCall, type ReadingStatus, type SpeciesChecksView } from '../utils/needs-your-call';
    import type { DomesticBirdKey } from '../utils/domestic-birds';
    import KeptBirdOffers from './KeptBirdOffers.svelte';
    import { _, locale } from 'svelte-i18n';
    import { displayDistance } from '../utils/display-distance.svelte';

    interface Props {
        queue: ReviewQueue;
        /** Until the history is read, an empty queue is unknown, not "nothing waiting". */
        status?: ReadingStatus;
        checks: SpeciesChecksView;
        onreview?: (detection: Detection) => void;
        onreviewall?: () => void;
        onretry?: () => void;
        onopenchecks?: () => void;
        onretrychecks?: () => void;
        onkept?: (bird: DomesticBirdKey) => void;
    }

    let { queue, status = 'ready', checks, onreview, onreviewall, onretry, onopenchecks, onretrychecks, onkept }: Props = $props();

    const call = $derived(
        needsYourCall({ canReview: true, queueStatus: status, queueTotal: queue.total, checksStatus: checks.status, checkCount: checks.names.length })
    );

    // A long list of names would bury the sentence; the rest are counted and named on the Species page.
    const NAMED_CHECKS = 3;
    const checkNames = $derived.by(() => {
        const named = checks.names.slice(0, NAMED_CHECKS);
        const rest = checks.names.length - named.length;
        if (rest > 0) named.push($_('dashboard.review_queue.checks_more', { values: { count: rest }, default: '{count} more' }));
        return new Intl.ListFormat($locale ?? 'en', { style: 'long', type: 'conjunction' }).format(named);
    });

    // The queue reaches back further than today, so a bare time would be ambiguous.
    function when(detection: Detection): string {
        const at = new Date(detection.detection_time);
        if (Number.isNaN(at.getTime())) return '';
        const isToday = at.toDateString() === new Date().toDateString();
        return isToday
            ? formatTime(detection.detection_time)
            : `${formatDate(detection.detection_time)} ${formatTime(detection.detection_time)}`;
    }

    // A detection the queue holds always has a reason; one without is waiting on its score.
    function reason(detection: Detection): string {
        const message = reviewReasonMessage(
            queue.reasons.get(detection.frigate_event) ?? 'low_score',
            queue.newSpeciesSightings.get(detection.frigate_event) ?? 1
        );
        return $_(message.key, { values: message.values, default: message.default });
    }
</script>

<section
    class="rounded-2xl border p-5 {call.total > 0
        ? 'border-attention-300 bg-attention-50/70 dark:border-attention-800/70 dark:bg-attention-950/25'
        : 'border-line-soft bg-surface'}"
    data-dashboard-review-queue
    aria-labelledby="review-queue-title"
>
    <header class="flex items-center gap-2">
        <svg
            class="h-4 w-4 {call.total > 0
                ? 'text-attention-700 dark:text-attention-300'
                : 'text-slate-600 dark:text-slate-400'}"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
        >
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 21V4h9l-1 3h6l-2 4 2 4h-9l-1-3H5" />
        </svg>
        <h2 id="review-queue-title" class="font-display text-xl font-bold text-slate-950 dark:text-white">
            {$_('dashboard.review_queue.title', { default: 'Needs your call' })}
        </h2>
        {#if call.total > 0}
            <span
                class="ml-auto rounded-full bg-attention-500 px-2 py-0.5 text-xs font-bold text-attention-950"
                data-review-queue-count
            >
                {call.total}
            </span>
        {/if}
    </header>

    {#if call.nothingWaiting}
        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">
            {$_('dashboard.review_queue.empty', {
                default: 'Every visit in the last 24 hours has a species. Nothing waiting on you.'
            })}
        </p>
    {:else if call.visits === 'loading'}
        <p role="status" class="sr-only">
            {$_('dashboard.review_queue.loading', { default: 'Checking for visits that need you…' })}
        </p>
        <div class="mt-3 space-y-2" aria-hidden="true">
            {#each ['w-28', 'w-20'] as width (width)}
                <div class="flex items-center gap-2.5 px-1.5">
                    <span class="h-8 w-8 shrink-0 rounded-lg bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                    <span class="h-3 rounded-sm bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60 {width}" data-loading-placeholder></span>
                </div>
            {/each}
        </div>
    {:else if call.visits === 'unavailable'}
        <p class="mt-2 text-xs text-slate-600 dark:text-slate-300">
            {$_('dashboard.review_queue.unavailable', {
                default: 'The queue could not be checked, so it is not known whether anything is waiting.'
            })}
        </p>
        {#if onretry}
            <button type="button" class="btn btn-secondary mt-3 min-h-11 px-3 text-xs" onclick={() => onretry?.()}>
                {$_('dashboard.field_log.retry', { default: 'Try again' })}
            </button>
        {/if}
    {:else if call.visits === 'clear'}
        <p class="mt-2 text-xs text-slate-600 dark:text-slate-400" data-review-queue-visits-clear>
            {$_('dashboard.review_queue.visits_clear', { default: 'Every visit in the last 24 hours has a species.' })}
        </p>
    {:else}
        {#if call.visits === 'stale'}
            <p class="mt-2 text-xs text-slate-600 dark:text-slate-300" data-review-queue-visits-stale>
                {$_('dashboard.review_queue.visits_stale', {
                    default: 'The visit history could not be read again, so this list may be out of date.'
                })}
            </p>
            {#if onretry}
                <button type="button" class="btn btn-secondary mt-2 min-h-11 px-3 text-xs" onclick={() => onretry?.()}>
                    {$_('dashboard.field_log.retry', { default: 'Try again' })}
                </button>
            {/if}
        {/if}
        <ul class="mt-3 space-y-2">
            {#each queue.items as detection (detection.frigate_event)}
                <li>
                    <button
                        class="flex w-full items-center gap-2.5 rounded-xl px-1.5 py-1.5 text-left transition-colors hover:bg-white/70 focus-ring dark:hover:bg-slate-800/60"
                        onclick={() => onreview?.(detection)}
                    >
                        <MediaImage
                            sources={[getThumbnailUrl(detection.frigate_event, detectionsStore.settledMediaVersion(detection.frigate_event))]}
                            alt=""
                            loading="lazy"
                            decoding="async"
                            width={32}
                            height={32}
                            class="h-8 w-8 shrink-0 rounded-lg bg-slate-100 object-cover dark:bg-slate-800"
                            iconClass="h-4 w-4"
                        />
                        <span class="min-w-0 flex-1">
                            <span class="block truncate text-xs font-semibold text-slate-800 dark:text-slate-100">
                                {detection.display_name}
                            </span>
                            <!-- Why it waits comes first; a phone drops the camera to keep it whole. -->
                            <span class="block truncate text-2xs text-slate-600 dark:text-slate-400">
                                <span class="font-semibold text-attention-800 dark:text-attention-300" data-review-queue-reason>{reason(detection)}</span>
                                · {when(detection)}<span class="hidden sm:inline" data-review-queue-camera> · {detection.camera_name}</span>
                            </span>
                        </span>
                        <span class="shrink-0 text-2xs font-bold tabular-nums text-attention-800 dark:text-attention-300">
                            {Math.round((detection.score ?? 0) * 100)}%
                        </span>
                    </button>
                </li>
            {/each}
        </ul>

        {#if queue.remaining > 0}
            <p class="mt-2 text-2xs text-slate-600 dark:text-slate-400">
                {$_('dashboard.review_queue.remaining', {
                    values: { count: queue.remaining },
                    default: '{count} more waiting'
                })}
            </p>
        {/if}

        <button class="btn btn-primary mt-3 min-h-11 w-full px-3 py-2 text-xs" onclick={() => onreviewall?.()}>
            {$_('dashboard.review_queue.work_through', { default: 'Work through the queue' })}
        </button>
    {/if}

    {#if !call.nothingWaiting && call.checks !== 'clear' && call.checks !== 'off'}
        <div class="mt-3 border-t border-line-soft pt-3" data-review-queue-checks={call.checks}>
            {#if call.checks === 'loading'}
                <p role="status" class="sr-only">
                    {$_('dashboard.review_queue.checks_loading', { default: 'Checking for species that may be misnamed…' })}
                </p>
                <span class="block h-3 w-40 rounded-sm bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" aria-hidden="true" data-loading-placeholder></span>
            {:else if call.checks === 'unavailable'}
                <p class="text-xs text-slate-600 dark:text-slate-300">
                    {$_('dashboard.review_queue.checks_unavailable', {
                        default: 'The range check could not be read, so it is not known whether a species may be misnamed.'
                    })}
                </p>
                {#if onretrychecks}
                    <button type="button" class="btn btn-secondary mt-3 min-h-11 px-3 text-xs" onclick={() => onretrychecks?.()}>
                        {$_('dashboard.field_log.retry', { default: 'Try again' })}
                    </button>
                {/if}
            {:else}
                {#if call.checks === 'stale'}
                    <p class="mb-2 text-xs text-slate-600 dark:text-slate-300" data-review-queue-checks-stale>
                        {$_('dashboard.review_queue.checks_stale', {
                            default: 'The range check could not be read again, so this list may be out of date.'
                        })}
                    </p>
                    {#if onretrychecks}
                        <button type="button" class="btn btn-secondary mb-3 min-h-11 px-3 text-xs" onclick={() => onretrychecks?.()}>
                            {$_('dashboard.field_log.retry', { default: 'Try again' })}
                        </button>
                    {/if}
                {/if}
                <p class="flex items-start gap-2 text-xs font-semibold text-attention-800 dark:text-attention-300">
                    <span class="mt-1 h-2 w-2 shrink-0 rounded-full bg-attention-500" aria-hidden="true"></span>
                    <span>
                        {$_('dashboard.review_queue.checks_summary', {
                            values: { count: checks.names.length, species: checkNames },
                            default: '{count, plural, one {# species may be misnamed: {species}.} other {# species may be misnamed: {species}.}}'
                        })}
                    </span>
                </p>
                <p class="mt-1 text-2xs text-slate-600 dark:text-slate-300">
                    {checks.nearbyRadiusKm
                        ? $_('dashboard.review_queue.checks_body', {
                              values: { count: checks.names.length, distance: displayDistance(checks.nearbyRadiusKm, $_) },
                              default: '{count, plural, one {Only the camera backs it and no birder has reported it within {distance}.} other {Only the camera backs them and no birder has reported them within {distance}.}}'
                          })
                        : $_('dashboard.review_queue.checks_body_plain', {
                              values: { count: checks.names.length },
                              default: '{count, plural, one {Only the camera backs it.} other {Only the camera backs them.}}'
                          })}
                </p>
                <!-- It leaves the page for the Species page, so it says so and points onward. -->
                <button
                    type="button"
                    class="mt-2 inline-flex min-h-11 items-center gap-1.5 rounded-xl px-2 py-2 text-xs font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-ring dark:text-brand-300 dark:hover:bg-brand-950/40"
                    onclick={() => onopenchecks?.()}
                    data-review-queue-open-checks
                >
                    {$_('dashboard.review_queue.checks_open', { default: 'Open the checks on the Species page' })}
                    <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                    </svg>
                </button>
                {#if checks.keptBirds.length > 0}
                    <div class="mt-2">
                        <KeptBirdOffers candidates={checks.keptBirds} {onkept} stacked size="small" />
                    </div>
                {/if}
            {/if}
        </div>
    {/if}
</section>
