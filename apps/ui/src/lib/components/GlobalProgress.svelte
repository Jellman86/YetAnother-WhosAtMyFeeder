<script lang="ts">
    import { onMount } from 'svelte';
    import { slide } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { jobProgressStore, type JobProgressItem } from '../stores/job_progress.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { fetchAnalysisStatus, type AnalysisStatus } from '../api/maintenance';
    import { getNotificationsTabPathForAccess } from '../app/notifications_route';
    import { buildJobsPipelineModel, type QueueTelemetryByKind } from '../jobs/pipeline';
    import { buildGlobalProgressSummary, presentActiveJob, type JobsTranslateFn } from '../jobs/presenter';
    let { onNavigate } = $props<{ onNavigate?: (path: string) => void }>();

    let nowTs = $state(Date.now());
    let showDetails = $state(false);
    let queueByKind = $state<QueueTelemetryByKind>({});
    let analysisStatus = $state<AnalysisStatus | null>(null);
    let analysisStatusSignature = $state('');
    const detailLimit = 4;
    onMount(() => {
        const tick = setInterval(() => {
            nowTs = Date.now();
        }, 1000);
        let queuePoll: ReturnType<typeof setInterval> | null = null;
        let stopped = false;

        const updateQueueTelemetry = async () => {
            if (stopped) return;
            if (!authStore.showSettings) return;
            try {
                const status = await fetchAnalysisStatus();
                const signature = [
                    status.pending ?? 0,
                    status.active ?? 0,
                    status.circuit_open ? 1 : 0,
                    status.pending_capacity ?? '',
                    status.pending_available ?? '',
                    status.max_concurrent_configured ?? '',
                    status.max_concurrent_effective ?? '',
                    status.mqtt_pressure_level ?? '',
                    status.throttled_for_mqtt_pressure ? 1 : 0,
                    status.mqtt_in_flight ?? '',
                    status.mqtt_in_flight_capacity ?? ''
                ].join('|');
                if (signature !== analysisStatusSignature) {
                    analysisStatus = status;
                    analysisStatusSignature = signature;
                }
                queueByKind = {
                    ...queueByKind,
                    reclassify: {
                        queued: Math.max(0, Math.floor(Number(status.pending ?? 0))),
                        running: Math.max(0, Math.floor(Number(status.active ?? 0))),
                        queueDepthKnown: true,
                        updatedAt: Date.now(),
                        maxConcurrentConfigured: Math.max(0, Math.floor(Number(status.max_concurrent_configured ?? 0))),
                        maxConcurrentEffective: Math.max(0, Math.floor(Number(status.max_concurrent_effective ?? 0))),
                        mqttPressureLevel: typeof status.mqtt_pressure_level === 'string' ? status.mqtt_pressure_level : undefined,
                        throttledForMqttPressure: status.throttled_for_mqtt_pressure === true,
                        mqttInFlight: Math.max(0, Math.floor(Number(status.mqtt_in_flight ?? 0))),
                        mqttInFlightCapacity: Math.max(0, Math.floor(Number(status.mqtt_in_flight_capacity ?? 0)))
                    }
                };
            } catch {
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

        if (authStore.showSettings) {
            updateQueueTelemetry();
            queuePoll = setInterval(updateQueueTelemetry, 5000);
        }

        return () => {
            stopped = true;
            clearInterval(tick);
            if (queuePoll) clearInterval(queuePoll);
        };
    });

    let activeJobs = $derived(jobProgressStore.activeJobs);
    let runningJobs = $derived(activeJobs.filter((item) => item.status === 'running'));
    let staleJobs = $derived(activeJobs.filter((item) => item.status === 'stale'));
    let pipeline = $derived(buildJobsPipelineModel(activeJobs, [], queueByKind));
    let rowsByKind = $derived.by(() => new Map(pipeline.kinds.map((row) => [row.kind, row])));
    const t: JobsTranslateFn = (key, values, fallback) => $_(key, { values, default: fallback });
    let visibleJobs = $derived(activeJobs);
    let detailJobs = $derived(visibleJobs.slice(0, detailLimit).map((job) => ({
        job,
        presentation: presentActiveJob(job, rowsByKind.get(job.kind) ?? null, analysisStatus, nowTs, t)
    })));

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

    function kindLabel(kind: string): string {
        if (kind === 'reclassify') return $_('jobs.kind_reclassify', { default: 'Reclassification' });
        if (kind === 'reclassify_batch') return $_('settings.data.batch_analysis_title', { default: 'Batch Analysis' });
        if (kind === 'backfill') return $_('jobs.kind_backfill', { default: 'Detection Backfill' });
        if (kind === 'weather_backfill') return $_('jobs.kind_weather_backfill', { default: 'Weather Backfill' });
        if (kind === 'taxonomy_sync') return $_('jobs.kind_taxonomy_sync', { default: 'Taxonomy Sync' });
        return kind.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
    }

    let aggregate = $derived(buildGlobalProgressSummary(activeJobs, rowsByKind, analysisStatus, nowTs, t, kindLabel));

    function openJobsPage() {
        const jobsTabPath = getNotificationsTabPathForAccess('jobs', authStore.showSettings);
        if (onNavigate) {
            onNavigate(jobsTabPath);
            return;
        }
        window.location.assign(jobsTabPath);
    }
</script>

{#if activeJobs.length > 0}
    <div
        class="w-full bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 overflow-hidden relative shrink-0"
        transition:slide={{ duration: 300 }}
        role="status"
        aria-live="polite"
    >
        <div class="absolute inset-0 bg-emerald-500/5 pointer-events-none"></div>

        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 relative z-10">
            <div class="flex flex-col gap-2">
                <div class="flex items-center justify-between gap-3">
                    <button
                        type="button"
                        class="flex items-center gap-3 min-w-0 flex-1 text-left bg-transparent focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded-lg"
                        onmouseenter={() => showDetails = true}
                        onmouseleave={() => showDetails = false}
                        onclick={() => showDetails = !showDetails}
                        aria-expanded={showDetails}
                        aria-controls="global-progress-details"
                    >
                        <div class="w-6 h-6 rounded-lg bg-emerald-100 dark:bg-emerald-900/30 flex items-center justify-center text-emerald-600 dark:text-emerald-400 flex-shrink-0">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 {runningJobs.length > 0 ? 'animate-spin' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        </div>
                        <div class="min-w-0">
                            <p class="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-tight truncate">
                                {aggregate.headline}
                            </p>
                            <p class="text-[9px] font-bold text-slate-500 dark:text-slate-300 uppercase tracking-wider truncate">
                                {aggregate.subline}
                                {#if staleJobs.length > 0}
                                    · {$_('notifications.global_progress_stale', { values: { count: staleJobs.length }, default: '{count} stale' })}
                                {/if}
                            </p>
                        </div>
                    </button>

                    <button
                        type="button"
                        class="px-3 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-wider bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300 hover:bg-emerald-200 dark:hover:bg-emerald-800/50 transition-colors"
                        onclick={openJobsPage}
                    >
                        {$_('jobs.open', { default: 'Open Jobs' })}
                    </button>
                </div>

                <div class="flex items-center justify-between text-[9px] uppercase tracking-wider font-bold text-slate-500 dark:text-slate-300">
                    <span>{aggregate.progressLabel}</span>
                    <span class="text-right">{$_('notifications.global_progress_last', { values: { age: fmtAge(activeJobs[0].updatedAt) }, default: 'Updated {age} ago' })}</span>
                </div>

                <div class="h-2 w-full bg-emerald-100 dark:bg-emerald-950/60 rounded-full overflow-hidden relative">
                    {#if aggregate.determinate && aggregate.percent !== null}
                        <div
                            class="h-full bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 transition-all duration-500"
                            style="width: {aggregate.percent}%"
                        ></div>
                    {:else}
                        <div class="h-full w-2/5 bg-gradient-to-r from-emerald-500/70 via-teal-500/70 to-sky-500/70 animate-pulse"></div>
                    {/if}
                </div>

                {#if showDetails}
                    <div id="global-progress-details" class="pt-2 border-t border-slate-100 dark:border-slate-800/50 mt-1 grid grid-cols-1 gap-2">
                        {#each detailJobs as item (item.job.id)}
                            {@const job = item.job}
                            {@const presentation = item.presentation}
                            <div class="rounded-xl border border-slate-200/80 dark:border-slate-700/60 px-3 py-2 bg-white/80 dark:bg-slate-900/60">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="text-[10px] font-black uppercase tracking-wide text-slate-800 dark:text-slate-100 truncate">{job.title}</p>
                                    <span class="text-[9px] font-bold uppercase tracking-widest {job.status === 'stale' ? 'text-amber-600 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-300'}">
                                        {job.status}
                                    </span>
                                </div>
                                <p class="text-[10px] font-semibold text-slate-700 dark:text-slate-200 truncate">{presentation.activityLabel}</p>
                                {#if job.message}
                                    <p class="text-[10px] text-slate-500 dark:text-slate-300 truncate">{job.message}</p>
                                {/if}
                                <div class="mt-1 flex items-center justify-between text-[9px] font-semibold text-slate-400 dark:text-slate-400">
                                    <span>{presentation.progressLabel}</span>
                                    <span>{presentation.freshnessLabel}</span>
                                </div>
                                {#if presentation.capacityLabel || presentation.blockerLabel}
                                    <p class="mt-1 text-[9px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-400 truncate">
                                        {presentation.capacityLabel ?? ''}
                                        {#if presentation.capacityLabel && presentation.blockerLabel}
                                            ·
                                        {/if}
                                        {presentation.blockerLabel ?? ''}
                                    </p>
                                {/if}
                            </div>
                        {/each}
                        {#if visibleJobs.length > detailLimit}
                            <button
                                type="button"
                                class="text-left text-[10px] font-black uppercase tracking-wider text-teal-600 dark:text-teal-300 hover:underline"
                                onclick={openJobsPage}
                            >
                                {$_('jobs.more', { values: { count: visibleJobs.length - detailLimit }, default: '+{count} more jobs' })}
                            </button>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}
