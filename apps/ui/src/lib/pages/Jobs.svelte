<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { jobProgressStore, type JobProgressItem } from '../stores/job_progress.svelte';
    import { buildJobsPipelineModel, type QueueTelemetryByKind } from '../jobs/pipeline';
    import { presentActiveJob, type JobsTranslateFn } from '../jobs/presenter';
    import { formatDateTime } from '../utils/datetime';
    import { analysisQueueStatusStore } from '../stores/analysis_queue_status.svelte';
    import { resetVideoCircuit } from '../api/maintenance';
    let { onNavigate, embedded = false } = $props<{ onNavigate?: (path: string) => void; embedded?: boolean }>();

    let nowTs = $state(Date.now());
    onMount(() => {
        const tick = setInterval(() => {
            nowTs = Date.now();
        }, 1000);
        const release = analysisQueueStatusStore.retain();

        return () => {
            release();
            clearInterval(tick);
        };
    });

    let activeJobs = $derived(jobProgressStore.activeJobs);
    let staleJobs = $derived(activeJobs.filter((job) => job.status === 'stale'));
    let historyJobs = $derived(jobProgressStore.historyJobs);
    let queueByKind = $derived(analysisQueueStatusStore.queueByKind as QueueTelemetryByKind);
    let analysisStatus = $derived(analysisQueueStatusStore.analysisStatus);
    let pipeline = $derived(buildJobsPipelineModel(activeJobs, historyJobs, queueByKind));
    let pipelineByKind = $derived.by(() => new Map(pipeline.kinds.map((row) => [row.kind, row])));
    const t: JobsTranslateFn = (key, values, fallback) => $_(key, { values, default: fallback });
    let presentedActiveJobs = $derived(activeJobs.map((job) => ({
        job,
        presentation: presentActiveJob(job, pipelineByKind.get(job.kind) ?? null, analysisStatus, nowTs, t)
    })));
    let circuitOpen = $derived(Boolean(analysisStatus?.circuit_open));
    let circuitOpenUntil = $derived(analysisStatus?.open_until ?? null);
    let circuitFailureCount = $derived(Math.max(0, Math.floor(Number(analysisStatus?.failure_count ?? 0))));
    let queuedReclassifyJobs = $derived(Math.max(0, Math.floor(Number(analysisStatus?.pending ?? queueByKind.reclassify?.queued ?? 0))));
    let resettingCircuit = $state(false);

    async function handleResetCircuit() {
        if (resettingCircuit) return;
        resettingCircuit = true;
        try {
            await resetVideoCircuit();
            await analysisQueueStatusStore.refresh();
        } catch {
            // Swallow — the circuit status will update on the next poll regardless.
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
            window.location.assign(item.route);
        }
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
        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div class="rounded-2xl border border-slate-200/80 dark:border-slate-700/60 bg-slate-50/80 dark:bg-slate-900/60 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.queued', { default: 'Queued' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.queuedKnown.toLocaleString()}</p>
            </div>
            <div class="rounded-2xl border border-slate-200/80 dark:border-slate-700/60 bg-slate-50/80 dark:bg-slate-900/60 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.running', { default: 'Running' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.running.toLocaleString()}</p>
            </div>
            <div class="rounded-2xl border border-slate-200/80 dark:border-slate-700/60 bg-slate-50/80 dark:bg-slate-900/60 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.completed', { default: 'Done' })}</p>
                <p class="mt-1 text-2xl font-black text-slate-900 dark:text-white">{pipeline.lanes.completed.toLocaleString()}</p>
            </div>
            <div class="rounded-2xl border border-slate-200/80 dark:border-slate-700/60 bg-slate-50/80 dark:bg-slate-900/60 p-3">
                <p class="text-[10px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('jobs.failed', { default: 'Failed' })}</p>
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
                        aria-label={$_('jobs.circuit_reset_button', { default: 'Reset Circuit' })}
                        class="px-3 py-1.5 text-xs font-bold rounded-xl bg-amber-500 hover:bg-amber-600 text-white transition-colors disabled:opacity-50 flex items-center gap-1.5"
                    >
                        {#if resettingCircuit}
                            <svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        {/if}
                        {$_('jobs.circuit_reset_button', { default: 'Reset Circuit' })}
                    </button>
                    <p class="mt-1 text-[10px] text-amber-600/80 dark:text-amber-300/70">
                        {$_('jobs.circuit_reset_confirm', { default: 'This will reopen the video classification queue immediately. Queued jobs will retry.' })}
                    </p>
                </div>
            </div>
        {/if}
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
                {#each presentedActiveJobs as item (item.job.id)}
                    {@const job = item.job}
                    {@const presentation = item.presentation}
                    {@const percent = presentation.percent}
                    <div class="rounded-2xl border border-emerald-100/80 dark:border-emerald-900/50 bg-white/80 dark:bg-slate-900/70 px-4 py-3 shadow-sm">
                        <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0">
                                <p class="text-sm font-semibold text-slate-900 dark:text-white truncate">{job.title}</p>
                                <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{presentation.activityLabel}</p>
                            </div>
                            <span class="text-[10px] font-black uppercase tracking-wider {job.status === 'stale' ? 'text-amber-600 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-300'}">
                                {job.status}
                            </span>
                        </div>
                        <div class="mt-3 flex items-center justify-between gap-3 text-xs font-semibold text-slate-600 dark:text-slate-300">
                            <span>{presentation.progressLabel}</span>
                            {#if presentation.determinate && percent !== null}
                                <span>{percent}%</span>
                            {/if}
                        </div>
                        <div class="mt-2 h-2 rounded-full bg-emerald-100 dark:bg-emerald-950/60 overflow-hidden">
                            {#if presentation.determinate && percent !== null}
                                <div class="h-full bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 transition-all duration-500" style={`width: ${percent}%`}></div>
                            {:else}
                                <div class="h-full w-2/5 bg-gradient-to-r from-emerald-500/70 via-teal-500/70 to-sky-500/70 animate-pulse"></div>
                            {/if}
                        </div>
                        {#if presentation.detailLabel}
                            <p class="mt-2 text-[10px] font-semibold text-amber-600 dark:text-amber-300">
                                {presentation.detailLabel}
                            </p>
                        {/if}
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
