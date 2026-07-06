<script lang="ts">
    import { onMount } from 'svelte';
    import {
        fetchAudioHistory,
        fetchAudioSummary,
        type AudioHistoryDetection,
        type AudioHistoryResponse,
        type AudioSummaryResponse
    } from '../api';
    import { formatDate, formatDateTime, formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    const PAGE_SIZE = 100;

    let days = $state(30);
    let speciesFilter = $state('');
    let sourceFilter = $state('');
    let minConfidence = $state(0);
    let history = $state<AudioHistoryResponse | null>(null);
    let summary = $state<AudioSummaryResponse | null>(null);
    let loading = $state(true);
    let error = $state<string | null>(null);
    let offset = $state(0);

    let detections = $derived<AudioHistoryDetection[]>(history?.items ?? []);
    let maxHourlyCount = $derived(Math.max(...(summary?.hourly_counts ?? []).map((item) => item.count), 1));
    let canPrevious = $derived(offset > 0);
    let canNext = $derived(Boolean(history && offset + history.limit < history.total));

    function requestParams(includePaging = true) {
        return {
            days,
            species: speciesFilter.trim() || undefined,
            source: sourceFilter.trim() || undefined,
            min_confidence: minConfidence,
            limit: includePaging ? PAGE_SIZE : undefined,
            offset: includePaging ? offset : undefined
        };
    }

    async function loadAudioHistory() {
        loading = true;
        error = null;
        try {
            const [nextHistory, nextSummary] = await Promise.all([
                fetchAudioHistory(requestParams(true)),
                fetchAudioSummary(requestParams(false))
            ]);
            history = nextHistory;
            summary = nextSummary;
        } catch (e) {
            error = getErrorMessage(e) || 'Unable to load BirdNET history.';
            history = null;
            summary = null;
            if (isTransientRequestError(e)) {
                logger.warn('BirdNET history fetch failed (transient)', { message: error });
            } else {
                logger.error('Failed to load BirdNET history', e);
            }
        } finally {
            loading = false;
        }
    }

    function applyFilters() {
        offset = 0;
        void loadAudioHistory();
    }

    function clearFilters() {
        days = 30;
        speciesFilter = '';
        sourceFilter = '';
        minConfidence = 0;
        offset = 0;
        void loadAudioHistory();
    }

    function previousPage() {
        if (!canPrevious) return;
        offset = Math.max(0, offset - PAGE_SIZE);
        void loadAudioHistory();
    }

    function nextPage() {
        if (!canNext) return;
        offset += PAGE_SIZE;
        void loadAudioHistory();
    }

    function confidencePercent(value: number | null | undefined): string {
        return `${Math.round((value ?? 0) * 100)}%`;
    }

    function hourLabel(hour: number): string {
        return `${String(hour).padStart(2, '0')}:00`;
    }

    onMount(() => {
        void loadAudioHistory();
    });
</script>

<div class="space-y-6">
    <section class="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Heard</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{summary?.total ?? 0}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">BirdNET detections in view</p>
        </div>
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Species</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{summary?.species_count ?? 0}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Audio-derived species</p>
        </div>
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Sources</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{summary?.source_count ?? 0}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">BirdNET microphones or streams</p>
        </div>
        <div class="card-base rounded-2xl p-4">
            <p class="text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">Confidence</p>
            <p class="mt-2 text-3xl font-black text-slate-900 dark:text-white">{confidencePercent(minConfidence)}</p>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">Minimum filter</p>
        </div>
    </section>

    <section class="card-base rounded-2xl p-4">
        <div class="grid grid-cols-1 gap-3 md:grid-cols-5">
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">Window</span>
                <select bind:value={days} class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-900 dark:text-white">
                    <option value={1}>24 hours</option>
                    <option value={7}>7 days</option>
                    <option value={30}>30 days</option>
                    <option value={90}>90 days</option>
                    <option value={365}>1 year</option>
                </select>
            </label>
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">Species</span>
                <input bind:value={speciesFilter} class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-white" placeholder="Dunnock" />
            </label>
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">Source</span>
                <input bind:value={sourceFilter} class="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 dark:text-white" placeholder="BirdCam" />
            </label>
            <label class="space-y-1">
                <span class="text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">Min confidence</span>
                <input bind:value={minConfidence} type="range" min="0" max="1" step="0.05" class="h-10 w-full accent-teal-600" />
            </label>
            <div class="flex items-end gap-2">
                <button type="button" class="btn-primary flex-1 justify-center" onclick={applyFilters}>Apply</button>
                <button type="button" class="btn-secondary flex-1 justify-center" onclick={clearFilters}>Clear</button>
            </div>
        </div>
    </section>

    {#if error}
        <div class="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-200">
            {error}
        </div>
    {/if}

    <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section class="card-base rounded-2xl p-4">
            <div class="mb-4 flex items-center justify-between gap-3">
                <div>
                    <h2 class="text-lg font-black text-slate-900 dark:text-white">Detection History</h2>
                    <p class="text-xs text-slate-500 dark:text-slate-400">Persisted BirdNET-Go detections, separate from visual visits.</p>
                </div>
                <button type="button" class="btn-secondary" onclick={() => void loadAudioHistory()} disabled={loading}>Refresh</button>
            </div>

            {#if loading}
                <div class="space-y-2">
                    {#each Array.from({ length: 8 }) as _}
                        <div class="h-14 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800"></div>
                    {/each}
                </div>
            {:else if detections.length === 0}
                <div class="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    No BirdNET detections match these filters.
                </div>
            {:else}
                <div class="overflow-x-auto">
                    <table class="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
                        <thead>
                            <tr class="text-left text-xs font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                <th class="py-2 pr-4">Time</th>
                                <th class="py-2 pr-4">Species</th>
                                <th class="py-2 pr-4">Source</th>
                                <th class="py-2 pr-4 text-right">Confidence</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                            {#each detections as detection}
                                <tr class="text-slate-700 dark:text-slate-200">
                                    <td class="whitespace-nowrap py-3 pr-4">
                                        <div class="font-bold">{formatDate(detection.timestamp)}</div>
                                        <div class="text-xs text-slate-500 dark:text-slate-400">{formatTime(detection.timestamp, { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</div>
                                    </td>
                                    <td class="py-3 pr-4 font-black">{detection.species}</td>
                                    <td class="py-3 pr-4">{detection.source_name || detection.sensor_id || 'Unknown source'}</td>
                                    <td class="whitespace-nowrap py-3 pr-4 text-right font-black">{confidencePercent(detection.confidence)}</td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
                <div class="mt-4 flex items-center justify-between gap-3 border-t border-slate-200 pt-4 text-xs font-semibold text-slate-500 dark:border-slate-800 dark:text-slate-400">
                    <span>Showing {offset + 1}-{Math.min(offset + (history?.items.length ?? 0), history?.total ?? 0)} of {history?.total ?? 0}</span>
                    <div class="flex gap-2">
                        <button type="button" class="btn-secondary" onclick={previousPage} disabled={!canPrevious}>Previous</button>
                        <button type="button" class="btn-secondary" onclick={nextPage} disabled={!canNext}>Next</button>
                    </div>
                </div>
            {/if}
        </section>

        <aside class="space-y-6">
            <section class="card-base rounded-2xl p-4">
                <h2 class="text-base font-black text-slate-900 dark:text-white">Top Heard Species</h2>
                <div class="mt-4 space-y-3">
                    {#each (summary?.top_species ?? []).slice(0, 8) as item}
                        <div>
                            <div class="flex items-center justify-between gap-3 text-sm">
                                <span class="font-black text-slate-800 dark:text-slate-100">{item.species}</span>
                                <span class="font-black text-teal-700 dark:text-teal-300">{item.count}</span>
                            </div>
                            <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                Last heard {item.last_heard ? formatDateTime(item.last_heard) : 'unknown'} · avg {confidencePercent(item.avg_confidence)}
                            </div>
                        </div>
                    {:else}
                        <p class="text-sm text-slate-500 dark:text-slate-400">No species yet.</p>
                    {/each}
                </div>
            </section>

            <section class="card-base rounded-2xl p-4">
                <h2 class="text-base font-black text-slate-900 dark:text-white">Hourly Activity</h2>
                <div class="mt-4 space-y-2">
                    {#each (summary?.hourly_counts ?? []) as item}
                        <div class="grid grid-cols-[3.5rem_minmax(0,1fr)_2.5rem] items-center gap-2 text-xs">
                            <span class="font-bold text-slate-500 dark:text-slate-400">{hourLabel(item.hour)}</span>
                            <div class="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                                <div class="h-full rounded-full bg-teal-500" style={`width: ${Math.max(4, (item.count / maxHourlyCount) * 100)}%`}></div>
                            </div>
                            <span class="text-right font-black text-slate-700 dark:text-slate-200">{item.count}</span>
                        </div>
                    {:else}
                        <p class="text-sm text-slate-500 dark:text-slate-400">No hourly activity yet.</p>
                    {/each}
                </div>
            </section>

            <section class="card-base rounded-2xl p-4">
                <h2 class="text-base font-black text-slate-900 dark:text-white">Sources</h2>
                <div class="mt-4 space-y-3">
                    {#each (summary?.sources ?? []).slice(0, 8) as item}
                        <div class="flex items-start justify-between gap-3">
                            <div>
                                <p class="text-sm font-black text-slate-800 dark:text-slate-100">{item.source_name}</p>
                                <p class="text-xs text-slate-500 dark:text-slate-400">Last heard {formatDateTime(item.last_heard)}</p>
                            </div>
                            <span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-black text-slate-700 dark:bg-slate-800 dark:text-slate-200">{item.count}</span>
                        </div>
                    {:else}
                        <p class="text-sm text-slate-500 dark:text-slate-400">No sources yet.</p>
                    {/each}
                </div>
            </section>
        </aside>
    </div>
</div>
