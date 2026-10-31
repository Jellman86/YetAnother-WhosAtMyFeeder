<script lang="ts">
    import { getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { reviewReasonMessage, type ReviewQueue } from '../utils/review-queue';
    import MediaImage from './MediaImage.svelte';
    import { formatDate, formatTime } from '../utils/datetime';
    import { _ } from 'svelte-i18n';

    interface Props {
        queue: ReviewQueue;
        /** Until the history is read, an empty queue is unknown, not "nothing waiting". */
        status?: 'loading' | 'ready' | 'unavailable';
        onreview?: (detection: Detection) => void;
        onreviewall?: () => void;
        onretry?: () => void;
    }

    let { queue, status = 'ready', onreview, onreviewall, onretry }: Props = $props();

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
    class="rounded-2xl border p-5 {queue.total > 0
        ? 'border-attention-300 bg-attention-50/70 dark:border-attention-800/70 dark:bg-attention-950/25'
        : 'border-line-soft bg-surface'}"
    data-dashboard-review-queue
    aria-labelledby="review-queue-title"
>
    <header class="flex items-center gap-2">
        <svg
            class="h-4 w-4 {queue.total > 0
                ? 'text-attention-700 dark:text-attention-300'
                : 'text-slate-400 dark:text-slate-500'}"
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
        {#if queue.total > 0}
            <span
                class="ml-auto rounded-full bg-attention-500 px-2 py-0.5 text-xs font-bold text-attention-950"
                data-review-queue-count
            >
                {queue.total}
            </span>
        {/if}
    </header>

    {#if status === 'loading' && queue.total === 0}
        <p role="status" class="sr-only">
            {$_('dashboard.review_queue.loading', { default: 'Checking for visits that need you…' })}
        </p>
        <div class="mt-3 space-y-2" aria-hidden="true">
            {#each ['w-28', 'w-20'] as width (width)}
                <div class="flex items-center gap-2.5 px-1.5">
                    <span class="h-8 w-8 shrink-0 rounded-lg bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                    <span class="h-3 rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60 {width}" data-loading-placeholder></span>
                </div>
            {/each}
        </div>
    {:else if status === 'unavailable' && queue.total === 0}
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
    {:else if queue.total === 0}
        <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
            {$_('dashboard.review_queue.empty', {
                default: 'Every visit today has a species. Nothing waiting on you.'
            })}
        </p>
    {:else}
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
                            <span class="block truncate text-2xs text-slate-500 dark:text-slate-400">
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
            <p class="mt-2 text-2xs text-slate-500 dark:text-slate-400">
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
</section>
