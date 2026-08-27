<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { jobProgressStore, type JobProgressItem } from '../stores/job_progress.svelte';
    import { buildJobsPipelineModel, type QueueTelemetryByKind } from '../jobs/pipeline';
    import { presentActiveJob, presentJobKindIcon, presentWorkLane, type JobsTranslateFn } from '../jobs/presenter';
    import { formatDateTime } from '../utils/datetime';
    import { analysisQueueStatusStore } from '../stores/analysis_queue_status.svelte';
    import { backfillStatusStore } from '../stores/backfill_status.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { resetVideoCircuit } from '../api/maintenance';
    import { toAppPath } from '../app/url-base';
    import { serverJobsStore, stableJobIdentity } from '../stores/server_jobs.svelte';
    import Pagination from '../components/Pagination.svelte';
    import { paginateItems } from '../utils/pagination';
    let { onNavigate, embedded = false } = $props<{ onNavigate?: (path: string) => void; embedded?: boolean }>();

    let nowTs = $state(Date.now());
    onMount(() => {
        const tick = setInterval(() => {
            nowTs = Date.now();
        }, 1000);
        const releaseBackfill = backfillStatusStore.retain();
        const releaseServerJobs = serverJobsStore.retain();

        return () => {
            releaseBackfill();
            releaseServerJobs();
            clearInterval(tick);
        };
    });

    $effect(() => {
        return pageRefreshAction.register(async () => {
            await Promise.all([
                analysisQueueStatusStore.refresh(),
                backfillStatusStore.refresh(),
                serverJobsStore.refresh()
            ]);
        });
    });

    let activeJobs = $derived(serverJobsStore.mergeActive(jobProgressStore.activeJobs));
    let presentedActiveJobs = $derived.by(() => {
        return [...activeJobs].sort((left, right) => {
            const startedDiff = (right.startedAt ?? 0) - (left.startedAt ?? 0);
            if (startedDiff !== 0) return startedDiff;
            return right.id.localeCompare(left.id);
        });
    });
    let staleJobs = $derived(activeJobs.filter((job) => job.status === 'stale'));
    let historyJobs = $derived(serverJobsStore.mergeHistory(jobProgressStore.historyJobs));
    let recentJobs = $derived.by(() => {
        return [...historyJobs].sort((left, right) => {
            const recentDiff = jobRecentSortTimestamp(right) - jobRecentSortTimestamp(left);
            if (recentDiff !== 0) return recentDiff;
            return right.id.localeCompare(left.id);
        });
    });
    let requestedRecentPage = $state(1);
    let recentPageSize = $state(20);
    let recentJobsPage = $derived(paginateItems(recentJobs, requestedRecentPage, recentPageSize));
    let queueByKind = $derived({
        ...analysisQueueStatusStore.queueByKind,
        ...serverJobsStore.queueByKind
    } as QueueTelemetryByKind);
    let analysisStatus = $derived(analysisQueueStatusStore.analysisStatus);
    let pipeline = $derived(buildJobsPipelineModel(activeJobs, historyJobs, queueByKind));
    let pipelineByKind = $derived.by(() => new Map(pipeline.kinds.map((row) => [row.kind, row])));
    const t: JobsTranslateFn = (key, values, fallback) => $_(key, { values, default: fallback });
    let presentedWorkLanes = $derived(
        pipeline.kinds
            .filter((row) => row.running > 0 || row.stale > 0 || (row.queued ?? 0) > 0)
            .map((row) => ({
                row,
                presentation: presentWorkLane(row, analysisStatus, nowTs, t, kindLabel)
            }))
    );
    let circuitOpen = $derived(Boolean(analysisStatus?.circuit_open));
    let circuitOpenUntil = $derived(analysisStatus?.open_until ?? null);
    let circuitFailureCount = $derived(Math.max(0, Math.floor(Number(analysisStatus?.failure_count ?? 0))));
    let queuedReclassifyJobs = $derived(Math.max(0, Math.floor(Number(analysisStatus?.pending ?? queueByKind.reclassify?.queued ?? 0))));
    let resettingCircuit = $state(false);
    let circuitResetError = $state<string | null>(null);

    async function handleResetCircuit() {
        if (resettingCircuit) return;
        resettingCircuit = true;
        circuitResetError = null;
        try {
            await resetVideoCircuit();
            await analysisQueueStatusStore.refresh();
        } catch {
            circuitResetError = $_('jobs.circuit_reset_failed', {
                default: 'The queue could not be resumed. Try again.'
            });
        } finally {
            resettingCircuit = false;
        }
    }

    function openRoute(item: JobProgressItem) {
        if (typeof item.route === 'string' && item.route.length > 0) {
            if (onNavigate) {
                onNavigate(item.route);
                return;
            }
            window.location.assign(toAppPath(item.route));
        }
    }

    function isBackfillKind(kind: string) {
        return kind === 'backfill' || kind === 'weather_backfill';
    }

    function statusLabel(status: JobProgressItem['status']): string {
        if (status === 'queued') return $_('jobs.queued', { default: 'Queued' });
        if (status === 'running') return $_('jobs.status_running', { default: 'Running' });
        if (status === 'stale') return $_('jobs.status_stale', { default: 'Needs attention' });
        if (status === 'failed') return $_('jobs.status_failed', { default: 'Failed' });
        return $_('jobs.status_completed', { default: 'Completed' });
    }

    function kindLabel(kind: string): string {
        if (kind === 'reclassify') return $_('jobs.kind_reclassify', { default: 'Reclassification' });
        if (kind === 'reclassify_batch') return $_('settings.data.batch_analysis_title', { default: 'Batch Analysis' });
        if (kind === 'backfill') return $_('jobs.kind_backfill', { default: 'Detection Backfill' });
        if (kind === 'weather_backfill') return $_('jobs.kind_weather_backfill', { default: 'Weather Backfill' });
        if (kind === 'taxonomy_sync') return $_('jobs.kind_taxonomy_sync', { default: 'Taxonomy Sync' });
        if (kind === 'auto_video') return $_('jobs.kind_auto_video', { default: 'Automatic video analysis' });
        if (kind === 'video_analysis') return $_('jobs.kind_video_analysis', { default: 'Video analysis' });
        if (kind === 'high_quality_snapshot') return $_('jobs.kind_high_quality_snapshot', { default: 'Best-quality snapshots' });
        if (kind === 'full_visit') return $_('jobs.kind_full_visit', { default: 'Full visit clips' });
        return kind.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
    }

    function jobRecentSortTimestamp(job: JobProgressItem): number {
        return Math.max(job.finishedAt ?? 0, job.updatedAt ?? 0, job.startedAt ?? 0);
    }

    function changeRecentPage(page: number) {
        requestedRecentPage = page;
    }

    function changeRecentPageSize(size: number) {
        recentPageSize = size;
        requestedRecentPage = 1;
    }

</script>

<div class="space-y-6">
    {#if !embedded}
        <div>
            <div>
                <h2 class="text-2xl font-black text-slate-900 dark:text-white tracking-tight">{$_('notifications.page_title', { default: 'Notifications & Jobs' })}</h2>
                <p class="text-xs text-slate-500">{$_('notifications.page_subtitle', { default: 'Review notifications and background jobs.' })}</p>
            </div>
        </div>
    {/if}

    {#if serverJobsStore.error}
        <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100" role="status">
            {$_('jobs.server_status_unavailable', { default: 'Live job status is temporarily unavailable. Existing progress is shown and YA-WAMF will retry automatically.' })}
        </div>
    {/if}

    <div class="card-base overflow-hidden divide-y divide-slate-200/80 dark:divide-slate-800/80">
    <section class="px-4 py-5 sm:px-6">
        <div class="grid grid-cols-2 md:grid-cols-4">
            <div class="border-b border-r border-slate-200/80 px-4 py-3 dark:border-slate-800/80 md:border-b-0">
                <p class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.queued', { default: 'Queued' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.queuedKnown.toLocaleString()}</p>
            </div>
            <div class="border-b border-slate-200/80 px-4 py-3 dark:border-slate-800/80 md:border-b-0 md:border-r">
                <p class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.running', { default: 'Running' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.running.toLocaleString()}</p>
            </div>
            <div class="border-r border-slate-200/80 px-4 py-3 dark:border-slate-800/80">
                <p class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.completed', { default: 'Done' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.completed.toLocaleString()}</p>
            </div>
            <div class="px-4 py-3">
                <p class="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.failed', { default: 'Failed' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.failed.toLocaleString()}</p>
            </div>
        </div>

        {#if circuitOpen}
            <div class="mt-4 rounded-2xl border border-amber-200/80 dark:border-amber-800/60 bg-amber-50/80 dark:bg-amber-950/30 px-4 py-3">
                <p class="text-sm font-semibold text-amber-900 dark:text-amber-100">
                    {$_('jobs.circuit_open_message', { default: 'Reclassification queue paused by circuit breaker.' })}
                </p>
                <p class="mt-1 text-xs text-amber-700/90 dark:text-amber-200/90">
                    {$_('jobs.circuit_open_detail', {
                        values: {
                            queued: queuedReclassifyJobs.toLocaleString(),
                            failures: circuitFailureCount.toLocaleString()
                        },
                        default: '{queued} queued items are waiting. Recent failures: {failures}.'
                    })}
                    {#if circuitOpenUntil}
                        · {$_('jobs.circuit_open_until', { default: 'Until' })}: {formatDateTime(circuitOpenUntil)}
                    {/if}
                </p>
                <div class="mt-3">
                    <button
                        type="button"
                        onclick={handleResetCircuit}
                        disabled={resettingCircuit}
                        aria-label={$_('jobs.circuit_reset_button', { default: 'Try again' })}
                        class="btn btn-secondary min-h-11 px-4 text-sm"
                    >
                        {#if resettingCircuit}
                            <svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        {/if}
                        {$_('jobs.circuit_reset_button', { default: 'Try again' })}
                    </button>
                    <p class="mt-1 text-[10px] text-amber-600/80 dark:text-amber-300/70">
                        {$_('jobs.circuit_reset_confirm', { default: 'This will reopen the video classification queue immediately. Queued jobs will retry.' })}
                    </p>
                    {#if circuitResetError}
                        <p class="mt-2 text-xs font-semibold text-rose-700 dark:text-rose-300" role="alert">{circuitResetError}</p>
                    {/if}
                </div>
            </div>
        {/if}
    </section>

    <section class="px-4 py-5 sm:px-6">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-accent-600/80 dark:text-accent-300/80">{$_('jobs.work_lanes', { default: 'Work Lanes' })}</h3>
            <span class="text-[10px] font-semibold text-slate-400">{presentedWorkLanes.length}</span>
        </div>
        {#if presentedWorkLanes.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.work_lanes_empty', { default: 'No queued or running work.' })}</p>
        {:else}
            <div class="divide-y divide-slate-100 dark:divide-slate-800/60">
                {#each presentedWorkLanes as item (item.row.kind)}
                    {@const presentation = item.presentation}
                    <div class="py-3 first:pt-0 last:pb-0">
                        <div class="flex flex-wrap items-start justify-between gap-3">
                            <div class="min-w-0">
                                <div class="flex flex-wrap items-center gap-2">
                                    <p class="text-sm font-black text-slate-900 dark:text-white">{presentation.title}</p>
                                    <span class="rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-wider {item.row.running > 0 ? 'bg-accent-100 text-accent-700 dark:bg-accent-950/70 dark:text-accent-300' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}">
                                        {presentation.stateLabel}
                                    </span>
                                </div>
                                <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold text-slate-700 dark:text-slate-200">
                                    <span>{presentation.runningLabel}</span>
                                    <span>{presentation.queuedLabel}</span>
                                    {#if presentation.capacityLabel}
                                        <span>{presentation.capacityLabel}</span>
                                    {/if}
                                </div>
                                {#if presentation.batchLabel || presentation.candidateLabel || presentation.blockerLabel}
                                    <p class="mt-2 text-[10px] font-semibold {presentation.blockerLabel ? 'text-amber-600 dark:text-amber-300' : 'text-slate-500 dark:text-slate-400'}">
                                        {presentation.blockerLabel ?? presentation.batchLabel}
                                        {#if presentation.candidateLabel && !presentation.blockerLabel}
                                            · {presentation.candidateLabel}
                                        {/if}
                                    </p>
                                {/if}
                            </div>
                            {#if presentation.freshnessLabel}
                                <p class="text-[10px] font-semibold text-slate-400">{presentation.freshnessLabel}</p>
                            {/if}
                        </div>
                    </div>
                {/each}
            </div>
        {/if}
    </section>

    <section class="px-4 py-5 sm:px-6">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-accent-600/80 dark:text-accent-300/80">{$_('jobs.active', { default: 'Active Work' })}</h3>
            <span class="text-[10px] font-semibold text-slate-400">{activeJobs.length}</span>
        </div>
        {#if activeJobs.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.active_empty', { default: 'No active jobs.' })}</p>
        {:else}
            <div class="divide-y divide-slate-200/80 dark:divide-slate-800/80">
                {#each presentedActiveJobs as job (stableJobIdentity(job))}
                    {@const presentation = presentActiveJob(job, pipelineByKind.get(job.kind) ?? null, analysisStatus, nowTs, t)}
                    {@const jobKindIcon = presentJobKindIcon(job.kind)}
                    <div class="py-4 first:pt-0 last:pb-0">
                        <div class="flex items-start justify-between gap-2">
                            <div class="inline-flex items-center gap-2 min-w-0">
                                <span class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-100/80 text-accent-700 dark:bg-accent-950/70 dark:text-accent-300">
                                    {#if jobKindIcon.key === 'reclassify'}
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                            <path d="M3 4.5h10M3 8h10M3 11.5h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                        </svg>
                                    {:else if jobKindIcon.key === 'backfill'}
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                            <path d="M8 2.5v8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                            <path d="M5.5 8 8 10.5 10.5 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path>
                                            <path d="M3 13h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                        </svg>
                                    {:else if jobKindIcon.key === 'weather'}
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                            <path d="M5.5 11.5h5.25a2.25 2.25 0 1 0-.38-4.47 3.25 3.25 0 0 0-6.18.97A2 2 0 0 0 5.5 11.5Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"></path>
                                        </svg>
                                    {:else if jobKindIcon.key === 'download'}
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                            <path d="M8 2.5v7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                            <path d="M5.5 7.5 8 10l2.5-2.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path>
                                            <path d="M3 13h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                        </svg>
                                    {:else}
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                            <rect x="3" y="3" width="10" height="10" rx="2" stroke="currentColor" stroke-width="1.5"></rect>
                                        </svg>
                                    {/if}
                                </span>
                                <p class="text-[10px] font-black uppercase tracking-widest text-slate-400 dark:text-slate-500">
                                    {#if isBackfillKind(job.kind)}
                                        {$_('jobs.coordinator_job', { default: 'Coordinator Job' })}
                                    {:else}
                                        {$_('jobs.active_job', { default: 'Active Job' })}
                                    {/if}
                                </p>
                            </div>
                            <span class="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-wider {job.status === 'stale' ? 'text-amber-600 dark:text-amber-300' : job.status === 'queued' ? 'text-slate-500 dark:text-slate-300' : 'text-accent-600 dark:text-accent-300'}">
                                <span class={`h-2 w-2 rounded-full ${job.status === 'stale' ? 'bg-amber-500 dark:bg-amber-300' : job.status === 'queued' ? 'bg-slate-400 dark:bg-slate-500' : 'bg-accent-500 dark:bg-accent-300'}`}></span>
                                {statusLabel(job.status)}
                            </span>
                        </div>
                        <div class="mt-3">
                            <div class="min-w-0">
                                <p class="text-sm font-semibold text-slate-900 dark:text-white truncate">{job.title}</p>
                                <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{presentation.activityLabel}</p>
                            </div>
                            <div class="mt-3 flex items-center justify-between gap-3 text-xs font-semibold text-slate-600 dark:text-slate-300">
                                <span>{presentation.progressLabel}</span>
                                {#if presentation.determinate && presentation.percent !== null}
                                    <span>{presentation.percent}%</span>
                                {/if}
                            </div>
                            <div
                                class="mt-2 h-2 rounded-full bg-accent-100 dark:bg-accent-950/60 overflow-hidden"
                                role="progressbar"
                                aria-label={presentation.progressLabel}
                                aria-valuemin={0}
                                aria-valuemax={presentation.determinate ? 100 : undefined}
                                aria-valuenow={presentation.determinate && presentation.percent !== null ? presentation.percent : undefined}
                            >
                                {#if presentation.determinate && presentation.percent !== null}
                                    <div class="h-full w-full origin-left bg-gradient-to-r from-accent-500 via-brand-500 to-sky-500 transition-transform duration-200 ease-out motion-reduce:transition-none" style={`transform: scaleX(${presentation.percent / 100})`}></div>
                                {:else}
                                    <div class="h-full w-2/5 bg-gradient-to-r from-accent-500/70 via-brand-500/70 to-sky-500/70 motion-safe:animate-pulse"></div>
                                {/if}
                            </div>
                            {#if isBackfillKind(job.kind)}
                                <p class="mt-2 text-[10px] font-semibold text-accent-700/80 dark:text-accent-300/80">
                                    {$_('jobs.coordinator_detail', { default: 'One coordinator job manages classifier worker capacity for this backfill.' })}
                                </p>
                            {/if}
                            {#if presentation.detailLabel}
                                <p class="mt-2 text-[10px] font-semibold text-amber-600 dark:text-amber-300">
                                    {presentation.detailLabel}
                                </p>
                            {/if}
                            {#if job.route}
                                <button type="button" class="btn btn-ghost mt-2 min-h-11 px-3 text-xs" onclick={() => openRoute(job)}>
                                    <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                        <path d="M6 4H12V10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"></path>
                                        <path d="M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"></path>
                                    </svg>
                                    {$_('notifications.open_action')}
                                </button>
                            {/if}
                        </div>
                    </div>
                {/each}
            </div>
        {/if}
    </section>

    <section class="px-4 py-5 sm:px-6">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.recent', { default: 'Recent' })}</h3>
            <span class="text-[10px] font-semibold text-slate-400">{recentJobs.length}</span>
        </div>
        {#if recentJobs.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.recent_empty', { default: 'No completed jobs yet.' })}</p>
        {:else}
            <div class="divide-y divide-slate-100 dark:divide-slate-800/60">
                {#each recentJobsPage.items as job (job.id)}
                    {@const jobKindIcon = presentJobKindIcon(job.kind)}
                    <button
                        type="button"
                        class="w-full min-h-11 text-left py-3 transition px-2 rounded-xl enabled:hover:bg-slate-50 dark:enabled:hover:bg-slate-800/40 disabled:cursor-default"
                        onclick={() => openRoute(job)}
                        disabled={!job.route}
                    >
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0 flex-1">
                                <div class="flex items-start gap-2">
                                    <span
                                        class="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                                        title={jobKindIcon.label}
                                        aria-label={jobKindIcon.label}
                                    >
                                        {#if jobKindIcon.key === 'reclassify'}
                                            <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                                <path d="M3 4.5h10M3 8h10M3 11.5h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                            </svg>
                                        {:else if jobKindIcon.key === 'backfill'}
                                            <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                                <path d="M8 2.5v8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                                <path d="M5.5 8 8 10.5 10.5 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path>
                                                <path d="M3 13h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                            </svg>
                                        {:else if jobKindIcon.key === 'weather'}
                                            <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                                <path d="M5.5 11.5h5.25a2.25 2.25 0 1 0-.38-4.47 3.25 3.25 0 0 0-6.18.97A2 2 0 0 0 5.5 11.5Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"></path>
                                            </svg>
                                        {:else if jobKindIcon.key === 'download'}
                                            <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                                <path d="M8 2.5v7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                                <path d="M5.5 7.5 8 10l2.5-2.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"></path>
                                                <path d="M3 13h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"></path>
                                            </svg>
                                        {:else}
                                            <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                                                <rect x="3" y="3" width="10" height="10" rx="2" stroke="currentColor" stroke-width="1.5"></rect>
                                            </svg>
                                        {/if}
                                    </span>
                                    <div class="min-w-0 flex-1">
                                        <p class="text-sm font-semibold text-slate-900 dark:text-white truncate">{job.title}</p>
                                        <p class="text-xs text-slate-500 dark:text-slate-400 truncate">{job.message || ''}</p>
                                        <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mt-1">
                                            {statusLabel(job.status)} · {formatDateTime(job.finishedAt ?? job.updatedAt)}
                                        </p>
                                    </div>
                                </div>
                            </div>
                            <span class="text-[10px] font-black uppercase tracking-wider {job.status === 'failed' ? 'text-rose-600 dark:text-rose-300' : 'text-accent-600 dark:text-accent-300'}">
                                {statusLabel(job.status)}
                            </span>
                        </div>
                    </button>
                {/each}
            </div>
            <div data-jobs-history-pagination>
                <Pagination
                    currentPage={recentJobsPage.page}
                    totalPages={recentJobsPage.totalPages}
                    totalItems={recentJobsPage.totalItems}
                    itemsPerPage={recentJobsPage.pageSize}
                    onPageChange={changeRecentPage}
                    onPageSizeChange={changeRecentPageSize}
                    pageSizeOptions={[10, 20, 50]}
                />
            </div>
        {/if}
    </section>
    </div>
</div>
