<script lang="ts">
    import { onMount } from 'svelte';
    import { slide } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { jobProgressStore, type JobProgressItem } from '../stores/job_progress.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { getNotificationsTabPathForAccess } from '../app/notifications_route';
    let { onNavigate } = $props<{ onNavigate?: (path: string) => void }>();

    let nowTs = $state(Date.now());
    let showDetails = $state(false);
    const detailLimit = 4;
    onMount(() => {
        const tick = setInterval(() => {
            nowTs = Date.now();
        }, 1000);
        return () => {
            clearInterval(tick);
        };
    });

    let activeJobs = $derived(jobProgressStore.activeJobs);
    let runningJobs = $derived(activeJobs.filter((item) => item.status === 'running'));
    let staleJobs = $derived(activeJobs.filter((item) => item.status === 'stale'));
    let detailJobs = $derived(runningJobs.slice(0, detailLimit));

    function pct(item: JobProgressItem): number | null {
        if (item.total <= 0) return null;
        return Math.min(100, Math.max(0, Math.round((item.current / item.total) * 100)));
    }

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

    let aggregate = $derived.by(() => {
        if (runningJobs.length === 0) {
            return { percent: null as number | null, current: 0, total: 0, rate: 0, etaSeconds: null as number | null };
        }
        let current = 0;
        let total = 0;
        let rate = 0;
        for (const item of runningJobs) {
            if (item.total > 0) {
                total += item.total;
                current += Math.min(item.total, Math.max(0, item.current));
            }
            if (Number.isFinite(item.ratePerMinute) && (item.ratePerMinute ?? 0) > 0) {
                rate += item.ratePerMinute ?? 0;
            }
        }
        const percent = total > 0 ? Math.min(100, Math.max(0, Math.round((current / total) * 100))) : null;
        const etaSeconds = total > 0 && rate > 0 && current < total
            ? Math.ceil(((total - current) / rate) * 60)
            : null;
        return { percent, current, total, rate, etaSeconds };
    });

    let summaryLabel = $derived.by(() => {
        if (runningJobs.length === 1) return runningJobs[0].title;
        return $_('notifications.global_progress_tasks', { values: { count: runningJobs.length } });
    });

    function openJobsPage() {
        const jobsTabPath = getNotificationsTabPathForAccess('jobs', authStore.showSettings);
        if (onNavigate) {
            onNavigate(jobsTabPath);
            return;
        }
        window.location.assign(jobsTabPath);
    }
</script>

{#if runningJobs.length > 0}
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
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                        </div>
                        <div class="min-w-0">
                            <p class="text-[10px] font-black text-slate-900 dark:text-white uppercase tracking-tight truncate">
                                {summaryLabel}
                            </p>
                            <p class="text-[9px] font-bold text-slate-500 dark:text-slate-300 uppercase tracking-wider truncate">
                                {$_('notifications.global_progress_last', { values: { age: fmtAge(runningJobs[0].updatedAt) }, default: 'Updated {age} ago' })}
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
                    <span>
                        {#if aggregate.total > 0}
                            {aggregate.current.toLocaleString()} / {aggregate.total.toLocaleString()}
                        {:else}
                            {$_('jobs.unknown_total', { default: 'Scanning...' })}
                        {/if}
                    </span>
                    <span class="text-right">
                        {#if aggregate.percent !== null}
                            {aggregate.percent}% · {$_('jobs.rate_label', { values: { rate: fmtRate(aggregate.rate) }, default: '{rate}' })} · ETA {fmtEta(aggregate.etaSeconds ?? undefined)}
                        {:else}
                            {$_('jobs.rate_label', { values: { rate: fmtRate(aggregate.rate) }, default: '{rate}' })}
                        {/if}
                    </span>
                </div>

                <div class="h-2 w-full bg-emerald-100 dark:bg-emerald-950/60 rounded-full overflow-hidden relative">
                    {#if aggregate.percent !== null}
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
                        {#each detailJobs as job (job.id)}
                            {@const jobPercent = pct(job)}
                            <div class="rounded-xl border border-slate-200/80 dark:border-slate-700/60 px-3 py-2 bg-white/80 dark:bg-slate-900/60">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="text-[10px] font-black uppercase tracking-wide text-slate-800 dark:text-slate-100 truncate">{job.title}</p>
                                    <span class="text-[9px] font-bold uppercase tracking-widest {job.status === 'stale' ? 'text-amber-600 dark:text-amber-300' : 'text-emerald-600 dark:text-emerald-300'}">
                                        {job.status}
                                    </span>
                                </div>
                                <p class="text-[10px] text-slate-500 dark:text-slate-300 truncate">{job.message || ''}</p>
                                <div class="mt-1 flex items-center justify-between text-[9px] font-semibold text-slate-400 dark:text-slate-400">
                                    <span>
                                        {job.current.toLocaleString()}
                                        {#if job.total > 0}
                                            / {job.total.toLocaleString()}
                                        {/if}
                                        {#if jobPercent !== null}
                                            · {jobPercent}%
                                        {/if}
                                    </span>
                                    <span>{fmtRate(job.ratePerMinute)} · ETA {fmtEta(job.etaSeconds)}</span>
                                </div>
                            </div>
                        {/each}
                        {#if runningJobs.length > detailLimit}
                            <button
                                type="button"
                                class="text-left text-[10px] font-black uppercase tracking-wider text-teal-600 dark:text-teal-300 hover:underline"
                                onclick={openJobsPage}
                            >
                                {$_('jobs.more', { values: { count: runningJobs.length - detailLimit }, default: '+{count} more jobs' })}
                            </button>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>
    </div>
{/if}
