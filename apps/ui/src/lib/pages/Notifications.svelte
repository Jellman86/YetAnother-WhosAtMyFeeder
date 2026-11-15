<script lang="ts">
    import { untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { notificationCenter, type NotificationItem } from '../stores/notification_center.svelte';
    import { jobProgressStore } from '../stores/job_progress.svelte';
    import { serverJobsStore } from '../stores/server_jobs.svelte';
    import {
        type NotificationFilter,
        buildTimelineItems,
        countByFilter,
        filterNotifications,
        groupNotifications,
        isOwnerOnlyFilter,
        isStoppedJob,
        showsProgress,
        progressOf,
        toneOf
    } from '../utils/notification-timeline';
    import { formatDateTime, formatTime } from '../utils/datetime';
    import { getThumbnailUrl } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { toAppPath } from '../app/url-base';
    import Pagination from '../components/Pagination.svelte';
    import { paginateItems } from '../utils/pagination';
    import JobCircuitBanner from '../components/JobCircuitBanner.svelte';

    let { onNavigate }: { onNavigate?: (path: string) => void } = $props();

    const FILTERS: NotificationFilter[] = ['all', 'birds', 'updates', 'jobs', 'errors'];

    let notificationItems = $derived(notificationCenter.items);
    let isOwner = $derived(authStore.showSettings);
    let activeJobs = $derived(serverJobsStore.mergeActive(jobProgressStore.activeJobs));
    let historyJobs = $derived(serverJobsStore.mergeHistory(jobProgressStore.historyJobs));
    // Never retain or expose an earlier owner's server snapshot after access changes.
    let timelineJobs = $derived(isOwner ? [...activeJobs, ...historyJobs] : []);
    let items = $derived(buildTimelineItems(notificationItems, timelineJobs));
    // An owner's history is not whole until the first jobs reading is in. Drawing the part this
    // device already holds and then pushing job rows into it moved everything under them.
    let historyPending = $derived(isOwner && serverJobsStore.snapshot === null && serverJobsStore.error === null);
    let counts = $derived(countByFilter(items));
    let unread = $derived(items.filter((item) => !item.read).length);

    let filter = $state<NotificationFilter>('all');
    let requestedPage = $state(1);
    let pageSize = $state(20);
    // A guest can reach an owner filter by leaving one selected as access changes underneath them.
    let effectiveFilter = $derived(!isOwner && isOwnerOnlyFilter(filter) ? 'all' : filter);
    let visibleFilters = $derived(FILTERS.filter((name) => isOwner || !isOwnerOnlyFilter(name)));
    let filteredItems = $derived(filterNotifications(items, effectiveFilter));
    let timelinePage = $derived(paginateItems(filteredItems, requestedPage, pageSize));
    let groups = $derived(groupNotifications(timelinePage.items));

    $effect(() => {
        if (!isOwner) return;
        // retain() starts a refresh that reads and updates reactive store state. Keep those reads
        // outside this effect's dependency graph so a response cannot restart its own polling loop.
        return untrack(() => serverJobsStore.retain());
    });

    // Clearing is saved at once, so the toast offers the history back for a few seconds.
    function clearWithUndo(): void {
        const cleared = notificationCenter.clear();
        if (cleared.length === 0) return;
        toastStore.undoable(
            $_('notifications.cleared', {
                values: { count: cleared.length },
                default: '{count, plural, one {Cleared # notification.} other {Cleared # notifications.}}'
            }),
            $_('common.undo', { default: 'Undo' }),
            () => notificationCenter.restore(cleared)
        );
    }

    function navigate(path: string) {
        if (onNavigate) {
            onNavigate(path);
            return;
        }
        window.location.assign(toAppPath(path));
    }

    function selectFilter(nextFilter: NotificationFilter) {
        filter = nextFilter;
        requestedPage = 1;
    }

    function changePage(page: number) {
        requestedPage = page;
    }

    function changePageSize(size: number) {
        pageSize = size;
        requestedPage = 1;
    }

    function openItem(item: NotificationItem) {
        notificationCenter.markRead(item.id);
        const route = item.meta?.route;
        if (typeof route === 'string' && route.length > 0) navigate(route);
    }

    /** What a stopped job says for itself: how far it got and when it went quiet. */
    function stoppedMessage(item: NotificationItem, progress: { current: number; total: number } | null): string {
        const time = formatDateTime(item.timestamp);
        if (progress) {
            return $_('notifications.job_stopped', {
                values: { current: progress.current.toLocaleString(), total: progress.total.toLocaleString(), time }
            });
        }
        return $_('notifications.job_stopped_no_count', { values: { time } });
    }

    function canOpen(item: NotificationItem): boolean {
        return typeof item.meta?.route === 'string' && item.meta.route.length > 0;
    }

    /** A detection carries its own evidence; everything else gets an icon for its kind. */
    function captureEventId(item: NotificationItem): string | null {
        if (item.type !== 'detection') return null;
        const id = item.meta?.event_id;
        return typeof id === 'string' && id.length > 0 ? id : null;
    }

    type IconKind = 'warn' | 'check' | 'clock' | 'update' | 'bird' | 'bell';

    function iconKind(item: NotificationItem, tone: string): IconKind {
        if (tone === 'attention') return 'warn';
        if (tone === 'done') return 'check';
        if (tone === 'running') return 'clock';
        if (item.type === 'detection') return 'bird';
        if (item.type === 'update') return 'update';
        if (item.type === 'system') return 'bell';
        return 'clock';
    }

    function isOwnerOnlyItem(item: NotificationItem): boolean {
        return item.type === 'process' || item.type === 'system' || Boolean(item.meta?.status);
    }

    const TONE_DOT: Record<string, string> = {
        attention: 'bg-attention-500 border-attention-500',
        running: 'bg-brand-500 border-brand-500',
        done: 'bg-success-500 border-success-500',
        info: 'bg-slate-300 border-slate-300 dark:bg-slate-600 dark:border-slate-600'
    };
    const TONE_ICON: Record<string, string> = {
        attention: 'text-attention-800 bg-attention-50 border-attention-200 dark:text-attention-300 dark:bg-attention-950/40 dark:border-attention-900',
        running: 'text-brand-700 bg-brand-50 border-brand-200 dark:text-brand-300 dark:bg-brand-950/40 dark:border-brand-900',
        done: 'text-success-700 bg-success-50 border-success-200 dark:text-success-300 dark:bg-success-950/40 dark:border-success-900',
        info: 'text-slate-600 bg-slate-50 border-slate-200 dark:text-slate-400 dark:bg-slate-800/60 dark:border-slate-700'
    };
</script>

{#snippet rowBody(item: NotificationItem, groupKey: string, tone: ReturnType<typeof toneOf>, opens: boolean)}
    {@const progress = progressOf(item)}
    {@const capture = captureEventId(item)}
    {@const kind = iconKind(item, tone)}
    {#if capture}
        {@const thumbnailUrl = getThumbnailUrl(capture, detectionsStore.settledMediaVersion(capture))}
        <!-- The capture is the evidence, same as the field log. Fixed box
             and a placeholder underneath, so a missing image cannot shift
             the row or imply a state. Keyed, so a photograph saved by a
             later run is drawn even where the earlier one failed. -->
        <span class="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-md border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
            {#key thumbnailUrl}
                <img
                    src={thumbnailUrl}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width="32"
                    height="32"
                    class="h-8 w-8 object-cover"
                    onerror={(event) => event.currentTarget.classList.add('hidden')}
                />
            {/key}
        </span>
    {:else}
        <span class="grid h-8 w-8 shrink-0 place-items-center rounded-md border {TONE_ICON[tone]}">
            {#if kind === 'warn'}
                <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path d="M8 4.5v4.2M8 11.3v.2" stroke-linecap="round" />
                    <path d="M6.9 2.6 1.9 12a1.2 1.2 0 0 0 1.1 1.8h10a1.2 1.2 0 0 0 1.1-1.8l-5-9.4a1.2 1.2 0 0 0-2.2 0z" />
                </svg>
            {:else if kind === 'check'}
                <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true">
                    <path d="m3.5 8.5 3 3 6-6.5" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
            {:else if kind === 'clock'}
                <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <circle cx="8" cy="8" r="5.4" />
                    <path d="M8 5.4V8l1.8 1.2" stroke-linecap="round" />
                </svg>
            {:else if kind === 'update'}
                <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <!-- Two arrows turning: something is being retried or renewed. -->
                    <path d="M12.6 6.4A4.9 4.9 0 0 0 3.7 5.6M3.4 9.6a4.9 4.9 0 0 0 8.9.8M12.8 3.4v3h-3M3.2 12.6v-3h3" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
            {:else if kind === 'bird'}
                <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                    <path d="M10.4 4.1a1.9 1.9 0 1 1 2.2 2.9v1.4c0 2.6-2.1 4.7-4.7 4.7H3.1l2.6-2.2A4.4 4.4 0 0 1 10.4 4.1z" stroke-linejoin="round" />
                    <path d="M12.6 4.6h1.6" stroke-linecap="round" />
                </svg>
            {:else}
                <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                    <path d="M4 6.8a4 4 0 1 1 8 0c0 3 1 3.9 1 3.9H3s1-.9 1-3.9z" stroke-linejoin="round" />
                    <path d="M6.6 12.6a1.6 1.6 0 0 0 2.8 0" stroke-linecap="round" />
                </svg>
            {/if}
        </span>
    {/if}
    <span class="block min-w-0 flex-1">
        <!-- The time sits on the title line, at the right edge, so a row is as tall as its words. -->
        <span class="flex items-baseline gap-2">
            <span class="flex min-w-0 flex-1 items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                <!-- Its own box, so a long word can break instead of pushing the unread dot off the row. -->
                <span class="min-w-0 wrap-anywhere">{item.title}</span>
                {#if !item.read}
                    <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true"></span>
                    <span class="sr-only">{$_('notifications.count_unread', { default: 'unread' })}</span>
                {/if}
            </span>
            <!-- The group heading already carries the day, so only older rows repeat the date. -->
            <span class="shrink-0 text-3xs tabular-nums text-slate-600 dark:text-slate-400">
                {groupKey === 'older' || groupKey === 'yesterday' ? formatDateTime(item.timestamp) : formatTime(item.timestamp)}
            </span>
        </span>
        {#if isStoppedJob(item)}
            <span class="mt-0.5 block text-xs text-slate-600 dark:text-slate-300">{stoppedMessage(item, progress)}</span>
        {:else if item.message}
            <span class="mt-0.5 block text-xs text-slate-600 dark:text-slate-300">{item.message}</span>
        {/if}
        {#if progress && showsProgress(item)}
            <span class="mt-2 block h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <!-- Brand, not amber: a job in flight needs nobody. -->
                <span class="block h-full w-full origin-left rounded-full {isStoppedJob(item) ? 'bg-slate-400 dark:bg-slate-500' : 'bg-brand-500 transition-transform duration-200 ease-out motion-reduce:transition-none'}" style={`transform: scaleX(${progress.percent / 100})`}></span>
            </span>
            <span class="mt-1 flex justify-between text-3xs tabular-nums text-slate-600 dark:text-slate-400">
                <span>{progress.current.toLocaleString()} / {progress.total.toLocaleString()}</span>
                <span>{isStoppedJob(item) ? $_('notifications.job_stopped_label') : `${progress.percent}%`}</span>
            </span>
        {/if}
        {#if opens}
            <span class="sr-only">{item.meta?.open_label ?? $_('notifications.open_action')}</span>
        {/if}
    </span>
    {#if opens}
        <!-- The row is the link; the chevron says so without a button of its own. -->
        <svg class="mt-1 h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true" data-notification-chevron>
            <path d="m6 3.5 4.5 4.5L6 12.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
    {/if}
{/snippet}

<div class="space-y-5" data-notifications-timeline>
    <JobCircuitBanner />
    <!-- One window, stated once, with the same metrics the dashboard day bar uses. -->
    <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h2 class="font-display text-xl font-bold text-slate-900 dark:text-white">
                {$_('notifications.page_history', { default: 'History' })}
            </h2>
            <p class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
                <span><b class="font-semibold tabular-nums text-slate-900 dark:text-white">{items.length}</b>
                    {$_('notifications.count_events', { values: { count: items.length }, default: '{count, plural, one {event} other {events}}' })}</span>
                {#if unread > 0}
                    <span><b class="font-semibold tabular-nums text-slate-900 dark:text-white">{unread}</b>
                        {$_('notifications.count_unread_unit', { values: { count: unread }, default: '{count, plural, one {unread} other {unread}}' })}</span>
                {/if}
            </p>
        </div>
        <div class="flex flex-wrap gap-2">
            {#if isOwner}
                <!-- Three actions, three weights: a link elsewhere, the everyday action, and the one that empties the list. -->
                <a
                    href={toAppPath('/system-health')}
                    class="focus-ring inline-flex min-h-11 items-center rounded-sm px-1 text-xs font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200"
                    onclick={(event) => { if (onNavigate) { event.preventDefault(); onNavigate('/system-health'); } }}
                >
                    {$_('settings.data.open_diagnostics', { default: 'Open Health' })}
                </a>
            {/if}
            <button type="button" class="btn btn-secondary min-h-11 px-3 py-2 text-xs" onclick={() => notificationCenter.markAllRead()}>
                {$_('notifications.center_mark_all')}
            </button>
            <!-- Undoable from the toast that follows, so it needs no confirmation and no red. -->
            <button type="button" class="btn btn-ghost min-h-11 px-3 py-2 text-xs" onclick={clearWithUndo}>
                {$_('notifications.clear_notifications', { default: 'Clear notifications' })}
            </button>
        </div>
    </div>

    {#if isOwner && items.some(isOwnerOnlyItem)}
        <!-- Said once for the page, in words: marking it on every row was most of the rows. -->
        <p class="text-xs text-slate-600 dark:text-slate-400" data-notifications-owner-note>
            {$_('notifications.owner_only_note', { default: 'Background jobs, health and system events are shown only to you, not to visitors.' })}
        </p>
    {/if}

    <!-- Chips rather than tabs: a failed job belongs in the same list as everything else. -->
    <div class="flex flex-wrap gap-2" role="group" aria-label={$_('notifications.filter_group', { default: 'Filter notifications' })}>
        {#each visibleFilters as name (name)}
            <button
                type="button"
                class="focus-ring inline-flex min-h-11 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors {effectiveFilter === name
                    ? 'border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/50 dark:text-brand-300'
                    : 'border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300'}"
                aria-pressed={effectiveFilter === name}
                onclick={() => selectFilter(name)}
            >
                {$_(`notifications.filter_${name}`)}
                <span class="tabular-nums text-3xs text-slate-600 dark:text-slate-400">{counts[name]}</span>
            </button>
        {/each}
    </div>

    {#if historyPending}
        <div class="space-y-3" role="status" aria-label={$_('common.loading', { default: 'Loading…' })} data-notifications-loading>
            {#each [1, 2, 3, 4, 5, 6, 7, 8] as row (row)}
                <div class="h-20 rounded-xl bg-slate-100 motion-safe:animate-pulse dark:bg-slate-800" aria-hidden="true"></div>
            {/each}
        </div>
    {:else if groups.length === 0}
        <div class="card-base px-6 py-10 text-center">
            {#if items.length > 0}
                <p class="text-sm text-slate-600 dark:text-slate-400">
                    {$_('notifications.empty_filtered', { default: 'Nothing matches this filter.' })}
                </p>
            {:else}
                <h3 class="font-display text-lg font-bold text-slate-900 dark:text-white">
                    {$_('notifications.empty_title', { default: 'Nothing has happened yet' })}
                </h3>
                <p class="mx-auto mt-1 max-w-sm text-sm text-slate-600 dark:text-slate-400">
                    {$_('notifications.empty_body', {
                        default:
                            'Visits appear here as the classifier names them, and background work as it runs. Newest first.'
                    })}
                </p>
                <button type="button" class="btn btn-secondary mt-4 min-h-11 px-3 py-2 text-xs" onclick={() => navigate('/')}>
                    {$_('notifications.empty_action', { default: 'Open the field log' })}
                </button>
            {/if}
        </div>
    {:else}
        <div class="card-base p-4 sm:p-5">
            {#each groups as group (group.key)}
                <h3 class="mb-1 mt-5 text-3xs font-bold text-slate-600 first:mt-0 dark:text-slate-400">
                    {$_(`notifications.group_${group.key}`)}
                </h3>
                <ol class="ml-1">
                    {#each group.items as item, index (item.id)}
                        {@const tone = toneOf(item)}
                        <li class="grid grid-cols-[0.75rem_minmax(0,1fr)] gap-3">
                            <!-- The rail and its marker are centred in the same column rather than
                                 offset against a border by hand, so the dot cannot drift off the line.
                                 State reads from position and shape as well as colour, so it survives
                                 greyscale. -->
                            <span class="relative flex justify-center" aria-hidden="true">
                                {#if group.items.length > 1}
                                    <!-- The rail starts and stops at the outer dots rather than
                                         dangling past them. A lone entry needs no rail at all. -->
                                    <span
                                        class="absolute left-1/2 w-px -translate-x-1/2 bg-slate-200 dark:bg-slate-700 {index ===
                                        0
                                            ? 'top-7 bottom-0'
                                            : index === group.items.length - 1
                                              ? 'top-0 h-7'
                                              : 'inset-y-0'}"
                                    ></span>
                                {/if}
                                <span class="relative mt-3 grid h-8 place-items-center">
                                    <span class="h-2.5 w-2.5 rounded-full border-2 {TONE_DOT[tone]}"></span>
                                </span>
                            </span>
                            <div class="flex min-w-0 items-start gap-1 py-1">
                                {#if canOpen(item)}
                                    <button
                                        type="button"
                                        class="focus-ring flex min-h-11 min-w-0 flex-1 items-start gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-slate-100 dark:hover:bg-slate-800/70"
                                        onclick={() => openItem(item)}
                                        data-notification-row="link"
                                    >
                                        {@render rowBody(item, group.key, tone, true)}
                                    </button>
                                {:else}
                                    <div class="flex min-h-11 min-w-0 flex-1 items-start gap-3 px-2 py-2" data-notification-row="plain">
                                        {@render rowBody(item, group.key, tone, false)}
                                    </div>
                                {/if}
                                {#if isStoppedJob(item)}
                                    <!-- A stopped job is a record; the owner decides when it has been seen. -->
                                    <button type="button" class="btn btn-ghost focus-ring min-h-11 shrink-0 px-2 text-xs" onclick={() => notificationCenter.remove(item.id)}>
                                        {$_('notifications.dismiss_action')}
                                    </button>
                                {/if}
                            </div>
                        </li>
                    {/each}
                </ol>
            {/each}
        </div>
        <div data-notifications-pagination>
            <Pagination
                currentPage={timelinePage.page}
                totalPages={timelinePage.totalPages}
                totalItems={timelinePage.totalItems}
                itemsPerPage={timelinePage.pageSize}
                onPageChange={changePage}
                onPageSizeChange={changePageSize}
                pageSizeOptions={[10, 20, 50]}
            />
        </div>
    {/if}
</div>
