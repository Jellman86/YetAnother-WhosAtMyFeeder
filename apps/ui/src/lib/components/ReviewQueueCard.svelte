<script lang="ts">
    import { getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import type { ReviewQueue } from '../utils/review-queue';
    import { formatDate, formatTime } from '../utils/datetime';
    import { _ } from 'svelte-i18n';

    interface Props {
        queue: ReviewQueue;
        onreview?: (detection: Detection) => void;
        onreviewall?: () => void;
    }

    let { queue, onreview, onreviewall }: Props = $props();

    // The queue reaches back further than today, so a bare time would be ambiguous.
    function when(detection: Detection): string {
        const at = new Date(detection.detection_time);
        if (Number.isNaN(at.getTime())) return '';
        const isToday = at.toDateString() === new Date().toDateString();
        return isToday
            ? formatTime(detection.detection_time)
            : `${formatDate(detection.detection_time)} ${formatTime(detection.detection_time)}`;
    }
</script>

<section
    class="rounded-2xl border p-4 {queue.total > 0
        ? 'border-accent-300 bg-accent-50/70 dark:border-accent-800/70 dark:bg-accent-950/25'
        : 'border-slate-200 bg-white/70 dark:border-slate-700/60 dark:bg-slate-900/40'}"
    data-dashboard-review-queue
    aria-labelledby="review-queue-title"
>
    <header class="flex items-center gap-2">
        <svg
            class="h-4 w-4 {queue.total > 0
                ? 'text-accent-700 dark:text-accent-300'
                : 'text-slate-400 dark:text-slate-500'}"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            aria-hidden="true"
        >
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 21V4h9l-1 3h6l-2 4 2 4h-9l-1-3H5" />
        </svg>
        <h3 id="review-queue-title" class="font-display text-sm font-bold text-slate-950 dark:text-white">
            {$_('dashboard.review_queue.title', { default: 'Needs your call' })}
        </h3>
        {#if queue.total > 0}
            <span
                class="ml-auto rounded-full bg-accent-500 px-2 py-0.5 text-xs font-bold text-accent-950"
                data-review-queue-count
            >
                {queue.total}
            </span>
        {/if}
    </header>

    {#if queue.total === 0}
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
                        <img
                            src={getThumbnailUrl(detection.frigate_event)}
                            alt=""
                            loading="lazy"
                            decoding="async"
                            width="32"
                            height="32"
                            class="h-8 w-8 shrink-0 rounded-lg object-cover"
                        />
                        <span class="min-w-0 flex-1">
                            <span class="block truncate text-xs font-semibold text-slate-800 dark:text-slate-100">
                                {detection.display_name}
                            </span>
                            <span class="block truncate text-[11px] text-slate-500 dark:text-slate-400">
                                {when(detection)} · {detection.camera_name}
                            </span>
                        </span>
                        <span class="shrink-0 text-[11px] font-bold tabular-nums text-accent-700 dark:text-accent-300">
                            {Math.round((detection.score ?? 0) * 100)}%
                        </span>
                    </button>
                </li>
            {/each}
        </ul>

        {#if queue.remaining > 0}
            <p class="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                {$_('dashboard.review_queue.remaining', {
                    values: { count: queue.remaining },
                    default: '{count} more waiting'
                })}
            </p>
        {/if}

        <button class="btn btn-primary mt-3 w-full px-3 py-2 text-xs" onclick={() => onreviewall?.()}>
            {$_('dashboard.review_queue.work_through', { default: 'Work through the queue' })}
        </button>
    {/if}
</section>
