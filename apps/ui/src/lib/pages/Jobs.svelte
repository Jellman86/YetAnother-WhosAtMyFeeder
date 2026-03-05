<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { jobProgressStore, type JobProgressItem } from '../stores/job_progress.svelte';
    import { fetchAnalysisStatus } from '../api/maintenance';
    import { buildJobsPipelineModel, type QueueTelemetryByKind } from '../jobs/pipeline';
    import { formatDateTime } from '../utils/datetime';
    let { onNavigate, embedded = false } = $props<{ onNavigate?: (path: string) => void; embedded?: boolean }>();

    let nowTs = $state(Date.now());
    let queueByKind = $state<QueueTelemetryByKind>({});
    onMount(() => {
        const tick = setInterval(() => {
            nowTs = Date.now();
        }, 1000);
        let queuePoll: ReturnType<typeof setInterval> | null = null;
        let stopped = false;

        const updateQueueTelemetry = async () => {
            if (stopped) return;
            try {
                const status = await fetchAnalysisStatus();
                queueByKind = {
                    ...queueByKind,
                    reclassify: {
                        queued: Math.max(0, Math.floor(Number(status.pending ?? 0))),
                        running: Math.max(0, Math.floor(Number(status.active ?? 0))),
                        queueDepthKnown: true,
                        updatedAt: Date.now()
                    }
                };
            } catch {
                // Keep polling; if we already have good queue data, keep displaying it.
                if (!queueByKind.reclassify) {
                    queueByKind = {
                        ...queueByKind,
                        reclassify: {
                            queued: 0,
                            running: 0,
                            queueDepthKnown: false,
                            updatedAt: Date.now()
                        }
                    };
                }
            }
        };

        updateQueueTelemetry();
        queuePoll = setInterval(updateQueueTelemetry, 5000);

        return () => {
            stopped = true;
            clearInterval(tick);
            if (queuePoll) clearInterval(queuePoll);
        };
    });

    let activeJobs = $derived(jobProgressStore.activeJobs);
    let historyJobs = $derived(jobProgressStore.historyJobs);
    let pipeline = $derived(buildJobsPipelineModel(activeJobs, historyJobs, queueByKind));
    let staleCount = $derived(activeJobs.filter((job) => job.status === 'stale').length);

    function fmtRate(value?: number): string {
        if (!Number.isFinite(value) || !value || value <= 0) return 'n/a';
        return `${Math.round(value).toLocaleString()}/min`;
    }

    function fmtEta(seconds?: number): string {
        if (!Number.isFinite(seconds) || !seconds || seconds <= 0) return 'n/a';
        const total = Math.floor(seconds);
        const h = Math.floor(total / 3600);
        const m = Math.floor((total % 3600) / 60);
        const s = total % 60;
        if (h > 0) return `${h}h ${m}m`;
        if (m > 0) return `${m}m ${s}s`;
        return `${s}s`;
    }

    function fmtAge(updatedAt: number): string {
        const sec = Math.max(0, Math.floor((nowTs - updatedAt) / 1000));
        if (sec < 60) return `${sec}s`;
        const min = Math.floor(sec / 60);
        const remSec = sec % 60;
        if (min < 60) return `${min}m ${remSec}s`;
        const hours = Math.floor(min / 60);
        const remMin = min % 60;
        return `${hours}h ${remMin}m`;
    }

    function pct(item: JobProgressItem): number | null {
        if (item.total <= 0) return null;
        return Math.min(100, Math.max(0, Math.round((item.current / item.total) * 100)));
    }

    function openRoute(item: JobProgressItem) {
        if (typeof item.route === 'string' && item.route.length > 0) {
            if (onNavigate) {
                onNavigate(item.route);
                return;
            }
            window.location.assign(item.route);
        }
    }

    function kindLabel(kind: string): string {
        if (kind === 'reclassify') {
            return $_('jobs.kind_reclassify', { default: 'Reclassification' });
        }
        if (kind === 'backfill') {
            return $_('jobs.kind_backfill', { default: 'Detection Backfill' });
        }
        if (kind === 'weather_backfill') {
            return $_('jobs.kind_weather_backfill', { default: 'Weather Backfill' });
        }
        if (kind === 'taxonomy_sync') {
            return $_('jobs.kind_taxonomy_sync', { default: 'Taxonomy Sync' });
        }
        return kind
            .replace(/_/g, ' ')
            .replace(/\b\w/g, (ch) => ch.toUpperCase());
    }
</script>

<div class="space-y-6">
    {#if !embedded}
        <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
                <h2 class="text-2xl font-black text-slate-900 dark:text-white tracking-tight">{$_('notifications.page_title', { default: 'Notifications & Jobs' })}</h2>
                <p class="text-xs text-slate-500">{$_('notifications.page_subtitle', { default: 'Review notifications and background jobs.' })}</p>
            </div>
            <div class="flex items-center gap-2">
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobProgressStore.clearHistory()}>
                    {$_('jobs.clear_history', { default: 'Clear History' })}
                </button>
                <button type="button" class="btn btn-secondary px-3 py-2 text-xs" onclick={() => jobProgressStore.clearAll()}>
                    {$_('jobs.clear_all', { default: 'Clear All' })}
                </button>
            </div>
        </div>
    {/if}

    <section class="card-base p-6">
        <div class="mb-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.pipeline_title', { default: 'Pipeline' })}</h3>
            <p class="text-xs text-slate-500">{$_('jobs.pipeline_subtitle', { default: 'Queued work flows into active processing, then into completed outcomes.' })}</p>
        </div>

        <div class="flex flex-col md:flex-row items-stretch gap-2 md:gap-3">
            <div class="flex-1 rounded-2xl border border-sky-200/80 dark:border-sky-900/60 bg-sky-50/70 dark:bg-sky-950/30 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-sky-700 dark:text-sky-300">{$_('jobs.queued', { default: 'Queued' })}</p>
                <p class="text-2xl font-black text-sky-700 dark:text-sky-200 mt-1">{pipeline.lanes.queuedKnown.toLocaleString()}</p>
                <p class="text-[10px] text-sky-700/80 dark:text-sky-300/90 mt-1">
                    {#if pipeline.lanes.queuedUnknownKinds > 0}
                        {$_('jobs.queue_unknown_suffix', { values: { count: pipeline.lanes.queuedUnknownKinds }, default: '+ {count} kinds not reported' })}
                    {:else}
                        {$_('jobs.queue_known', { default: 'All shown kinds report queue depth' })}
                    {/if}
                </p>
            </div>

            <div class="hidden md:flex items-center justify-center text-slate-400 dark:text-slate-500 font-black text-lg">→</div>

            <div class="flex-1 rounded-2xl border border-emerald-200/80 dark:border-emerald-900/60 bg-emerald-50/70 dark:bg-emerald-950/30 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-emerald-700 dark:text-emerald-300">{$_('jobs.running', { default: 'Running' })}</p>
                <p class="text-2xl font-black text-emerald-700 dark:text-emerald-200 mt-1">{pipeline.lanes.running.toLocaleString()}</p>
                <p class="text-[10px] text-emerald-700/80 dark:text-emerald-300/90 mt-1">
                    {$_('jobs.stale_hint', { values: { count: staleCount }, default: '{count} stale' })}
                </p>
            </div>

            <div class="hidden md:flex items-center justify-center text-slate-400 dark:text-slate-500 font-black text-lg">→</div>

            <div class="flex-1 rounded-2xl border border-slate-200/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/70 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-slate-600 dark:text-slate-300">{$_('jobs.outcomes', { default: 'Outcomes' })}</p>
                <p class="text-2xl font-black text-slate-700 dark:text-slate-100 mt-1">
                    {(pipeline.lanes.completed + pipeline.lanes.failed).toLocaleString()}
                </p>
                <p class="text-[10px] text-slate-600 dark:text-slate-300 mt-1">
                    {$_('jobs.completed_failed_counts', {
                        values: {
                            completed: pipeline.lanes.completed.toLocaleString(),
                            failed: pipeline.lanes.failed.toLocaleString()
                        },
                        default: '{completed} completed • {failed} failed'
                    })}
                </p>
            </div>
        </div>

        <div class="mt-4 space-y-2">
            {#each pipeline.kinds as row (row.kind)}
                <div class="rounded-xl border border-slate-200/80 dark:border-slate-700/60 bg-white/80 dark:bg-slate-900/60 px-3 py-2">
                    <div class="flex items-center justify-between gap-2">
                        <p class="text-xs font-black text-slate-800 dark:text-slate-100 uppercase tracking-wide">{kindLabel(row.kind)}</p>
                        <p class="text-[10px] font-semibold text-slate-400">
                            {#if row.queueDepthKnown}
                                {$_('jobs.queue_reported', { default: 'Queue reported' })}
                            {:else}
                                {$_('jobs.queue_not_reported', { default: 'Queue not reported' })}
                            {/if}
                        </p>
                    </div>
                    <div class="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-300">
                        <div>
                            {$_('jobs.queued', { default: 'Queued' })}: {row.queued === null ? '—' : row.queued.toLocaleString()}
                        </div>
                        <div>
                            {$_('jobs.running', { default: 'Running' })}: {row.running.toLocaleString()}
                        </div>
                        <div>
                            {$_('jobs.completed', { default: 'Completed' })}: {row.completed.toLocaleString()}
                        </div>
                        <div>
                            {$_('jobs.failed', { default: 'Failed' })}: {row.failed.toLocaleString()}
                        </div>
                    </div>
                </div>
            {/each}
        </div>
    </section>

    <section class="card-base p-6">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-emerald-600/80 dark:text-emerald-300/80">{$_('jobs.active', { default: 'Active' })}</h3>
            <span class="text-[10px] font-semibold text-slate-400">{activeJobs.length}</span>
        </div>
        {#if activeJobs.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.active_empty', { default: 'No active jobs.' })}</p>
        {:else}
            <div class="space-y-3">
                {#each activeJobs as job (job.id)}
                    {@const percent = pct(job)}
                    <div class="rounded-2xl border border-emerald-100/80 dark:border-emerald-900/50 bg-white/80 dark:bg-slate-900/70 px-4 py-3 shadow-sm">
                        <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0">
                                <p class="text-sm font-semibold text-slate-900 dark:text-white truncate">{job.title}</p>
                                <p class="text-xs text-slate-500 dark:text-slate-300 truncate">{job.message || ''}</p>
                            </div>
                            <span class="text-[10px] font-black uppercase tracking-wider {job.status === 'stale' ? 'text-amber-600 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-300'}">
                                {job.status}
                            </span>
                        </div>
                        <div class="mt-2 flex flex-wrap items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                            <span>
                                {job.current.toLocaleString()}
                                {#if job.total > 0}
                                    / {job.total.toLocaleString()}
                                {/if}
                                {#if percent !== null}
                                    · {percent}%
                                {/if}
                            </span>
                            <span>{fmtRate(job.ratePerMinute)} · ETA {fmtEta(job.etaSeconds)}</span>
                            <span>{$_('jobs.updated', { values: { age: fmtAge(job.updatedAt) }, default: 'Updated {age} ago' })}</span>
                        </div>
                        <div class="mt-2 h-2 rounded-full bg-emerald-100 dark:bg-emerald-950/60 overflow-hidden">
                            {#if percent !== null}
                                <div class="h-full bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 transition-all duration-500" style={`width: ${percent}%`}></div>
                            {:else}
                                <div class="h-full w-2/5 bg-gradient-to-r from-emerald-500/70 via-teal-500/70 to-sky-500/70 animate-pulse"></div>
                            {/if}
                        </div>
                        {#if job.route}
                            <button type="button" class="mt-2 text-[10px] font-black uppercase tracking-wider text-teal-600 dark:text-teal-300 hover:underline" onclick={() => openRoute(job)}>
                                {$_('notifications.open_action')}
                            </button>
                        {/if}
                    </div>
                {/each}
            </div>
        {/if}
    </section>

    <section class="card-base p-6">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('jobs.recent', { default: 'Recent' })}</h3>
            <span class="text-[10px] font-semibold text-slate-400">{historyJobs.length}</span>
        </div>
        {#if historyJobs.length === 0}
            <p class="text-xs text-slate-500">{$_('jobs.recent_empty', { default: 'No completed jobs yet.' })}</p>
        {:else}
            <div class="divide-y divide-slate-100 dark:divide-slate-800/60">
                {#each historyJobs as job (job.id)}
                    <button
                        type="button"
                        class="w-full text-left py-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition px-2 rounded-xl"
                        onclick={() => openRoute(job)}
                    >
                        <div class="flex items-start justify-between gap-3">
                            <div class="min-w-0 flex-1">
                                <p class="text-sm font-semibold text-slate-900 dark:text-white truncate">{job.title}</p>
                                <p class="text-xs text-slate-500 dark:text-slate-400 truncate">{job.message || ''}</p>
                                <p class="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mt-1">
                                    {job.status} · {formatDateTime(job.finishedAt ?? job.updatedAt)}
                                </p>
                            </div>
                            <span class="text-[10px] font-black uppercase tracking-wider {job.status === 'failed' ? 'text-rose-600 dark:text-rose-300' : 'text-emerald-600 dark:text-emerald-300'}">
                                {job.status}
                            </span>
                        </div>
                    </button>
                {/each}
            </div>
        {/if}
    </section>
</div>
