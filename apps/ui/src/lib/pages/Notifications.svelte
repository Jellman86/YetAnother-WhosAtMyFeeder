<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { notificationCenter, type NotificationItem } from '../stores/notification_center.svelte';
    import { jobProgressStore } from '../stores/job_progress.svelte';
    import {
        type NotificationFilter,
        countByFilter,
        filterNotifications,
        groupNotifications,
        isOwnerOnlyFilter,
        progressOf,
        toneOf
    } from '../utils/notification-timeline';
    import { formatDateTime, formatTime } from '../utils/datetime';
    import { getThumbnailUrl } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { toAppPath } from '../app/url-base';

    let { onNavigate } = $props<{ onNavigate?: (path: string) => void; currentRoute?: string }>();

    const FILTERS: NotificationFilter[] = ['all', 'birds', 'updates', 'jobs', 'errors'];

    let items = $derived(notificationCenter.items);
    let isOwner = $derived(authStore.showSettings);
    let activeJobs = $derived(jobProgressStore.activeJobs);
    let counts = $derived(countByFilter(items));
    let unread = $derived(items.filter((item) => !item.read).length);

    let filter = $state<NotificationFilter>('all');
    // A guest can reach an owner filter by leaving one selected as access changes underneath them.
    let effectiveFilter = $derived(!isOwner && isOwnerOnlyFilter(filter) ? 'all' : filter);
    let visibleFilters = $derived(FILTERS.filter((name) => isOwner || !isOwnerOnlyFilter(name)));
    let groups = $derived(groupNotifications(filterNotifications(items, effectiveFilter)));

    function navigate(path: string) {
        if (onNavigate) {
            onNavigate(path);
            return;
        }
        window.location.assign(toAppPath(path));
    }

    function openItem(item: NotificationItem) {
        notificationCenter.markRead(item.id);
        const route = item.meta?.route;
        if (typeof route === 'string' && route.length > 0) navigate(route);
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
        if (item.type === 'detection') return 'bird';
        if (item.type === 'update') return 'update';
        if (item.type === 'system') return 'bell';
        return tone === 'done' ? 'check' : 'clock';
    }

    function isOwnerOnlyItem(item: NotificationItem): boolean {
        return item.type === 'process' || item.type === 'system';
    }

    const TONE_DOT: Record<string, string> = {
        attention: 'bg-accent-500 border-accent-500',
        running: 'bg-brand-500 border-brand-500',
        done: 'bg-emerald-500 border-emerald-500',
        info: 'bg-slate-300 border-slate-300 dark:bg-slate-600 dark:border-slate-600'
    };
    const TONE_ICON: Record<string, string> = {
        attention: 'text-accent-700 bg-accent-50 border-accent-200 dark:text-accent-300 dark:bg-accent-950/40 dark:border-accent-900',
        running: 'text-brand-700 bg-brand-50 border-brand-200 dark:text-brand-300 dark:bg-brand-950/40 dark:border-brand-900',
        done: 'text-emerald-700 bg-emerald-50 border-emerald-200 dark:text-emerald-300 dark:bg-emerald-950/40 dark:border-emerald-900',
        info: 'text-slate-500 bg-slate-50 border-slate-200 dark:text-slate-400 dark:bg-slate-800/60 dark:border-slate-700'
    };
</script>

<!-- Matches the About page: a list of short text rows should not run the full 7xl shell. -->
<div class="mx-auto max-w-5xl space-y-5" data-notifications-timeline>
    <!-- One window, stated once, with the same metrics the dashboard day bar uses. -->
    <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h2 class="font-display text-xl font-bold text-slate-900 dark:text-white">
                {$_('notifications.window_label', { default: 'Today' })}
            </h2>
            <p class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
                <span><b class="font-semibold tabular-nums text-slate-900 dark:text-white">{items.length}</b>
                    {$_('notifications.count_events', { default: 'events' })}</span>
                {#if unread > 0}
                    <span><b class="font-semibold tabular-nums text-slate-900 dark:text-white">{unread}</b>
                        {$_('notifications.count_unread', { default: 'unread' })}</span>
                {/if}
            </p>
        </div>
        <div class="flex flex-wrap gap-2">
            {#if isOwner}
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => navigate('/notifications/jobs')}>
                    {$_('notifications.job_manager', { default: 'Job manager' })}
                    {#if activeJobs.length > 0}
                        <span class="ml-1.5 tabular-nums">{activeJobs.length}</span>
                    {/if}
                </button>
            {/if}
            <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => notificationCenter.markAllRead()}>
                {$_('notifications.center_mark_all')}
            </button>
            <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => notificationCenter.clear()}>
                {$_('notifications.center_clear')}
            </button>
        </div>
    </div>

    <!-- Chips rather than tabs: a failed job belongs in the same list as everything else. -->
    <div class="flex flex-wrap gap-2" role="group" aria-label={$_('notifications.filter_all', { default: 'Everything' })}>
        {#each visibleFilters as name (name)}
            <button
                type="button"
                class="focus-ring inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors {effectiveFilter === name
                    ? 'border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/50 dark:text-brand-300'
                    : 'border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300'}"
                aria-pressed={effectiveFilter === name}
                onclick={() => (filter = name)}
            >
                {$_(`notifications.filter_${name}`)}
                <span class="tabular-nums text-[10px] text-slate-400 dark:text-slate-500">{counts[name]}</span>
                {#if isOwnerOnlyFilter(name)}
                    <svg class="h-2.5 w-2.5 text-slate-400 dark:text-slate-500" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <rect x="3.5" y="7" width="9" height="6" rx="1.5" />
                        <path d="M5.8 7V5.2a2.2 2.2 0 014.4 0V7" />
                    </svg>
                {/if}
            </button>
        {/each}
    </div>

    {#if groups.length === 0}
        <div class="card-base px-6 py-10 text-center">
            {#if items.length > 0}
                <p class="text-sm text-slate-500 dark:text-slate-400">
                    {$_('notifications.empty_filtered', { default: 'Nothing matches this filter.' })}
                </p>
            {:else}
                <h3 class="font-display text-lg font-bold text-slate-900 dark:text-white">
                    {$_('notifications.empty_title', { default: 'Nothing has happened yet' })}
                </h3>
                <p class="mx-auto mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">
                    {$_('notifications.empty_body', {
                        default: 'Visits appear here as the classifier names them, newest first.'
                    })}
                </p>
                <button type="button" class="btn btn-secondary mt-4 px-3 py-2 text-xs" onclick={() => navigate('/')}>
                    {$_('notifications.empty_action', { default: 'Open the field log' })}
                </button>
            {/if}
        </div>
    {:else}
        <div class="card-base p-4 sm:p-5">
            {#each groups as group (group.key)}
                <h3 class="mb-1 mt-5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400 first:mt-0 dark:text-slate-500">
                    {$_(`notifications.group_${group.key}`)}
                </h3>
                <ol class="ml-1">
                    {#each group.items as item, index (item.id)}
                        {@const tone = toneOf(item)}
                        {@const progress = progressOf(item)}
                        {@const capture = captureEventId(item)}
                        {@const kind = iconKind(item, tone)}
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
                            <div class="flex items-start gap-3 py-3">
                                {#if capture}
                                    <!-- The capture is the evidence, same as the field log. Fixed box
                                         and a placeholder underneath, so a missing image cannot shift
                                         the row or imply a state. -->
                                    <span class="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-md border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
                                        <img
                                            src={getThumbnailUrl(capture)}
                                            alt=""
                                            loading="lazy"
                                            decoding="async"
                                            width="32"
                                            height="32"
                                            class="h-8 w-8 object-cover"
                                            onerror={(event) => event.currentTarget.classList.add('hidden')}
                                        />
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
                                                <path d="M8 3v6.6M5.3 7.2 8 9.9l2.7-2.7M3.4 12.4h9.2" stroke-linecap="round" stroke-linejoin="round" />
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
                                <div class="min-w-0 flex-1">
                                    <p class="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                                        {item.title}
                                        {#if !item.read}
                                            <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true"></span>
                                        {/if}
                                    </p>
                                    {#if item.message}
                                        <p class="mt-0.5 text-xs text-slate-600 dark:text-slate-300">{item.message}</p>
                                    {/if}
                                    {#if progress}
                                        <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                                            <!-- Brand, not the amber gradient this used to run: a job in flight needs nobody. -->
                                            <div class="h-full rounded-full bg-brand-500 transition-[width] duration-500" style={`width: ${progress.percent}%`}></div>
                                        </div>
                                        <p class="mt-1 flex justify-between font-mono text-[10px] text-slate-400 dark:text-slate-500">
                                            <span>{progress.current.toLocaleString()} / {progress.total.toLocaleString()}</span>
                                            <span>{progress.percent}%</span>
                                        </p>
                                    {/if}
                                    <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-slate-400 dark:text-slate-500">
                                        <!-- The group heading already carries the day, so repeating
                                             the full date on every row is noise. -->
                                        <span>{group.key === 'older' || group.key === 'yesterday'
                                            ? formatDateTime(item.timestamp)
                                            : formatTime(item.timestamp)}</span>
                                        {#if isOwnerOnlyItem(item)}
                                            <span class="inline-flex items-center gap-1 rounded border border-slate-200 px-1.5 py-px uppercase tracking-wider dark:border-slate-700">
                                                <svg class="h-2 w-2" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                                    <rect x="3.5" y="7" width="9" height="6" rx="1.5" />
                                                    <path d="M5.8 7V5.2a2.2 2.2 0 014.4 0V7" />
                                                </svg>
                                                {$_('notifications.owner_only', { default: 'owner' })}
                                            </span>
                                        {/if}
                                    </p>
                                    {#if canOpen(item)}
                                        <!-- Was a paragraph that looked like an action and could not be reached. -->
                                        <button
                                            type="button"
                                            class="btn btn-secondary focus-ring mt-2 px-2.5 py-1 text-xs"
                                            onclick={() => openItem(item)}
                                        >
                                            {item.meta?.open_label ?? $_('notifications.open_action')}
                                        </button>
                                    {/if}
                                </div>
                            </div>
                        </li>
                    {/each}
                </ol>
            {/each}
        </div>
    {/if}
</div>
