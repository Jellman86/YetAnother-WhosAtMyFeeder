<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { MaintenanceStats, BackfillResult, WeatherBackfillResult, CacheStats, TaxonomySyncStatus } from '../../api';

    // Props
    let {
        maintenanceStats,
        retentionDays = $bindable(0),
        cacheRetentionDays = $bindable(0),
        cleaningUp,
        cacheEnabled = $bindable(true),
        cacheSnapshots = $bindable(true),
        cacheClips = $bindable(true),
        cacheStats,
        cleaningCache,
        speciesInfoSource = $bindable('auto'),
        taxonomyStatus,
        syncingTaxonomy,
        backfillDateRange = $bindable<'day' | 'week' | 'month' | 'custom'>('week'),
        backfillStartDate = $bindable(''),
        backfillEndDate = $bindable(''),
        backfilling,
        backfillResult,
        backfillTotal = $bindable(0),
        weatherBackfilling,
        weatherBackfillResult,
        weatherBackfillTotal = $bindable(0),
        resettingDatabase,
        analyzingUnknowns,
        analysisStatus,
        analysisTotal,
        handleCleanup,
        handleCacheCleanup,
        handleStartTaxonomySync,
        handleBackfill,
        handleWeatherBackfill,
        handleAnalyzeUnknowns,
        handleResetDatabase
    }: {
        maintenanceStats: MaintenanceStats | null;
        retentionDays: number;
        cacheRetentionDays: number;
        cleaningUp: boolean;
        cacheEnabled: boolean;
        cacheSnapshots: boolean;
        cacheClips: boolean;
        cacheStats: CacheStats | null;
        cleaningCache: boolean;
        speciesInfoSource: string;
        taxonomyStatus: TaxonomySyncStatus | null;
        syncingTaxonomy: boolean;
        backfillDateRange: 'day' | 'week' | 'month' | 'custom';
        backfillStartDate: string;
        backfillEndDate: string;
        backfilling: boolean;
        backfillResult: BackfillResult | null;
        backfillTotal: number;
        weatherBackfilling: boolean;
        weatherBackfillResult: WeatherBackfillResult | null;
        weatherBackfillTotal: number;
        resettingDatabase: boolean;
        analyzingUnknowns: boolean;
        analysisStatus: { pending: number; active: number; circuit_open: boolean } | null;
        analysisTotal: number;
        handleCleanup: () => Promise<void>;
        handleCacheCleanup: () => Promise<void>;
        handleStartTaxonomySync: () => Promise<void>;
        handleBackfill: () => Promise<void>;
        handleWeatherBackfill: () => Promise<void>;
        handleAnalyzeUnknowns: () => Promise<void>;
        handleResetDatabase: () => Promise<void>;
    } = $props();
</script>

<div class="space-y-6">
    <!-- Maintenance Stats -->
    {#if maintenanceStats}
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            {#each [
                { label: 'Total Records', val: maintenanceStats.total_detections.toLocaleString(), color: 'text-teal-500' },
                { label: 'Oldest Seen', val: maintenanceStats.oldest_detection ? new Date(maintenanceStats.oldest_detection).toLocaleDateString() : 'N/A', color: 'text-blue-500' },
                { label: 'Retention', val: retentionDays === 0 ? '∞' : `${retentionDays} Days`, color: 'text-indigo-500' },
                { label: 'Pending GC', val: maintenanceStats.detections_to_cleanup.toLocaleString(), color: maintenanceStats.detections_to_cleanup > 0 ? 'text-amber-500' : 'text-slate-400' }
            ] as stat}
                <div class="card-base rounded-3xl p-6 text-center">
                    <p class="text-2xl font-black {stat.color} tracking-tight">{stat.val}</p>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{stat.label}</p>
                </div>
            {/each}
        </div>
    {/if}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
        <!-- Retention & Cleanup -->
        <section class="card-base rounded-3xl p-8">
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight mb-6">Retention Policy</h3>
            <div class="space-y-6">
                <div>
                    <label for="retention-days" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">History Duration</label>
                    <select
                        id="retention-days"
                        bind:value={retentionDays}
                        aria-label="Retention policy duration"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"
                    >
                        <option value={0}>Keep Everything (∞)</option>
                        <option value={7}>1 Week</option>
                        <option value={14}>2 Weeks</option>
                        <option value={30}>1 Month</option>
                        <option value={90}>3 Months</option>
                        <option value={365}>1 Year</option>
                    </select>
                </div>
                <div class="pt-4 border-t border-slate-100 dark:border-slate-700/50 flex flex-col gap-3">
                    <button
                        onclick={handleCleanup}
                        disabled={cleaningUp || retentionDays === 0 || (maintenanceStats?.detections_to_cleanup ?? 0) === 0}
                        aria-label="Purge old records"
                        class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-amber-500 hover:bg-amber-600 text-white transition-all shadow-lg shadow-amber-500/20 disabled:opacity-50"
                    >
                        {cleaningUp ? 'Cleaning...' : 'Purge Old Records'}
                    </button>
                    <p class="text-[10px] text-center text-slate-400 font-bold italic">Automatic cleanup runs daily at 3 AM</p>
                </div>
            </div>
        </section>

        <!-- Media Cache -->
        <section class="card-base rounded-3xl p-8">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Media Cache</h3>
                <button
                    role="switch"
                    aria-checked={cacheEnabled}
                    aria-label="Toggle media cache"
                    onclick={() => cacheEnabled = !cacheEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            cacheEnabled = !cacheEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {cacheEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">Media Cache</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {cacheEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            {#if cacheEnabled}
                <div class="space-y-6 animate-in fade-in slide-in-from-top-2">
                    <div class="grid grid-cols-2 gap-3">
                        <button
                            onclick={() => cacheSnapshots = !cacheSnapshots}
                            aria-label="Toggle snapshot caching"
                            class="p-4 rounded-2xl border-2 transition-all text-center {cacheSnapshots ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                        >
                            <p class="text-xs font-black uppercase tracking-widest">Snapshots</p>
                        </button>
                        <button
                            onclick={() => cacheClips = !cacheClips}
                            aria-label="Toggle video clip caching"
                            class="p-4 rounded-2xl border-2 transition-all text-center {cacheClips ? 'border-teal-500 bg-teal-500/5 text-teal-600' : 'border-slate-100 dark:border-slate-700/50 text-slate-400'}"
                        >
                            <p class="text-xs font-black uppercase tracking-widest">Video Clips</p>
                        </button>
                    </div>
                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                        <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">Cache Size</span>
                        <span class="text-sm font-black text-slate-900 dark:text-white">{cacheStats?.total_size_mb ?? 0} MB</span>
                    </div>
                    <button
                        onclick={handleCacheCleanup}
                        disabled={cleaningCache}
                        aria-label="Clear cached files"
                        class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-900 dark:bg-slate-700 text-white hover:bg-slate-800 transition-all disabled:opacity-50"
                    >
                        {cleaningCache ? 'Cleaning...' : 'Clear Cached Files'}
                    </button>
                </div>
            {/if}
        </section>
    </div>

    <!-- Species Info Source -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Species Info Source</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">Choose where summaries and images come from</p>
            </div>
        </div>
        <div class="space-y-3">
            <label for="species-info-source" class="block text-[10px] font-black uppercase tracking-widest text-slate-500">Source Preference</label>
            <select
                id="species-info-source"
                bind:value={speciesInfoSource}
                aria-label="Species info source"
                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
            >
                <option value="auto">Auto (iNaturalist with Wikipedia fallback)</option>
                <option value="inat">iNaturalist Only</option>
                <option value="wikipedia">Wikipedia Only</option>
            </select>
        </div>
    </section>

    <!-- Taxonomy Sync -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Taxonomy Repair</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">Connect scientific and common names</p>
            </div>
            {#if taxonomyStatus?.is_running}
                <div class="flex items-center gap-2 px-3 py-1 rounded-full bg-teal-500/10 text-teal-600 animate-pulse">
                    <div class="w-1.5 h-1.5 rounded-full bg-teal-500"></div>
                    <span class="text-[10px] font-black uppercase tracking-widest">Syncing</span>
                </div>
            {/if}
        </div>

        {#if taxonomyStatus}
            {#if taxonomyStatus.is_running}
                <div class="mb-6 space-y-3">
                    <div class="flex justify-between text-[10px] font-black uppercase tracking-widest">
                        <span class="text-slate-400">{taxonomyStatus.current_item || 'Repairing Database'}</span>
                        <span class="text-teal-500">{taxonomyStatus.processed} / {taxonomyStatus.total}</span>
                    </div>
                    <div class="w-full h-3 bg-slate-100 dark:bg-slate-900 rounded-full overflow-hidden border border-slate-200 dark:border-slate-700" role="progressbar" aria-valuenow={taxonomyStatus.processed} aria-valuemin="0" aria-valuemax={taxonomyStatus.total}>
                        <div class="h-full bg-gradient-to-r from-teal-500 to-emerald-400 transition-all duration-1000 ease-out" style="width: {(taxonomyStatus.processed / (taxonomyStatus.total || 1)) * 100}%"></div>
                    </div>
                </div>
            {:else if taxonomyStatus.current_item}
                <div class="mb-6 p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-700/50 flex items-center gap-3">
                    {#if taxonomyStatus.error}
                        <div class="w-2 h-2 rounded-full bg-red-500"></div>
                        <p class="text-xs font-bold text-red-500">{taxonomyStatus.error}</p>
                    {:else}
                        <div class="w-2 h-2 rounded-full bg-emerald-500"></div>
                        <p class="text-xs font-bold text-slate-600 dark:text-slate-300">{taxonomyStatus.current_item}</p>
                    {/if}
                </div>
            {/if}
        {/if}

        <button
            onclick={handleStartTaxonomySync}
            disabled={taxonomyStatus?.is_running || syncingTaxonomy}
            aria-label="Run full taxonomy repair"
            class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
        >
            {#if syncingTaxonomy || taxonomyStatus?.is_running}
                <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
            {/if}
            Run Full Taxonomy Repair
        </button>
    </section>

    <!-- Missed Detections (Backfill) -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Missed Detections</h3>
        </div>
        <p class="text-xs font-bold text-slate-500 leading-relaxed uppercase tracking-wider mb-6">Query Frigate history to fetch and classify past events.</p>

        <div class="space-y-6">
            <div>
                <label for="backfill-range" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Time Window</label>
                <select
                    id="backfill-range"
                    bind:value={backfillDateRange}
                    aria-label="Backfill time window"
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                >
                    <option value="day">Last 24 Hours</option>
                    <option value="week">Last Week</option>
                    <option value="month">Last Month</option>
                    <option value="custom">Custom Range</option>
                </select>
            </div>

            {#if backfillDateRange === 'custom'}
                <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                    <div>
                        <label for="backfill-start" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Start</label>
                        <input
                            id="backfill-start"
                            type="date"
                            bind:value={backfillStartDate}
                            aria-label="Backfill start date"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                    </div>
                    <div>
                        <label for="backfill-end" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">End</label>
                        <input
                            id="backfill-end"
                            type="date"
                            bind:value={backfillEndDate}
                            aria-label="Backfill end date"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                    </div>
                </div>
            {/if}

            {#if backfillResult}
                {#if backfillTotal > 0}
                    {@const backfillProgress = Math.min(100, Math.round((backfillResult.processed / backfillTotal) * 100))}
                    <div class="mb-3">
                        <div class="flex items-center justify-between text-[10px] font-bold text-slate-500 mb-2">
                            <span>{backfillResult.processed.toLocaleString()} / {backfillTotal.toLocaleString()}</span>
                            <span>{backfillProgress}%</span>
                        </div>
                        <div class="h-2 rounded-full bg-slate-200/80 dark:bg-slate-800/80 overflow-hidden">
                            <div class="h-full bg-teal-500 transition-all" style={`width: ${backfillProgress}%`}></div>
                        </div>
                    </div>
                {/if}
                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 grid grid-cols-4 gap-2 text-center">
                    <div><p class="text-sm font-black text-slate-900 dark:text-white">{backfillResult.processed}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Total</p></div>
                    <div><p class="text-sm font-black text-emerald-500">{backfillResult.new_detections}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">New</p></div>
                    <div><p class="text-sm font-black text-slate-400">{backfillResult.skipped}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Skip</p></div>
                    <div><p class="text-sm font-black text-red-500">{backfillResult.errors}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Err</p></div>
                </div>
                {#if backfillResult.skipped_reasons && Object.keys(backfillResult.skipped_reasons).length > 0}
                    <div class="mt-2 p-3 rounded-xl bg-slate-50/50 dark:bg-slate-900/30 border border-slate-100 dark:border-slate-700/30">
                        <p class="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-2">Skipped Breakdown</p>
                        <div class="grid grid-cols-1 gap-2">
                            {#each Object.entries(backfillResult.skipped_reasons) as [reason, count]}
                                <div class="flex justify-between items-center text-xs">
                                    <span class="text-slate-500">
                                        {#if reason === 'low_confidence'}
                                            Below Minimum Confidence Floor
                                        {:else if reason === 'below_threshold'}
                                            Below Confidence Threshold
                                        {:else if reason === 'blocked_label'}
                                            Filtered (Blocked Label)
                                        {:else if reason === 'already_exists'}
                                            Already in Database
                                        {:else if reason === 'fetch_snapshot_failed'}
                                            Frigate Snapshot Missing
                                        {:else}
                                            {reason.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                        {/if}
                                    </span>
                                    <span class="font-bold text-slate-700 dark:text-slate-300">{count}</span>
                                </div>
                            {/each}
                        </div>
                    </div>
                {/if}
            {/if}

            <button
                onclick={handleBackfill}
                disabled={backfilling}
                aria-label="Scan Frigate history"
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-teal-500 hover:bg-teal-600 text-white transition-all shadow-lg shadow-teal-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if backfilling}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {backfilling ? 'Analyzing Frigate...' : 'Scan History'}
            </button>

            <div class="pt-2 border-t border-slate-100 dark:border-slate-800">
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">Weather Backfill</p>
                {#if weatherBackfillResult}
                    {#if weatherBackfillTotal > 0}
                        {@const weatherProgress = Math.min(100, Math.round((weatherBackfillResult.processed / weatherBackfillTotal) * 100))}
                        <div class="mb-3">
                            <div class="flex items-center justify-between text-[10px] font-bold text-slate-500 mb-2">
                                <span>{weatherBackfillResult.processed.toLocaleString()} / {weatherBackfillTotal.toLocaleString()}</span>
                                <span>{weatherProgress}%</span>
                            </div>
                            <div class="h-2 rounded-full bg-slate-200/80 dark:bg-slate-800/80 overflow-hidden">
                                <div class="h-full bg-slate-700 transition-all" style={`width: ${weatherProgress}%`}></div>
                            </div>
                        </div>
                    {/if}
                    <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 grid grid-cols-4 gap-2 text-center mb-3">
                        <div><p class="text-sm font-black text-slate-900 dark:text-white">{weatherBackfillResult.processed}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Total</p></div>
                        <div><p class="text-sm font-black text-emerald-500">{weatherBackfillResult.updated}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Upd</p></div>
                        <div><p class="text-sm font-black text-slate-400">{weatherBackfillResult.skipped}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Skip</p></div>
                        <div><p class="text-sm font-black text-red-500">{weatherBackfillResult.errors}</p><p class="text-[8px] font-black uppercase text-slate-500 tracking-tighter">Err</p></div>
                    </div>
                {/if}
                <button
                    onclick={handleWeatherBackfill}
                    disabled={weatherBackfilling}
                    aria-label="Backfill weather fields"
                    class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-slate-800 hover:bg-slate-900 text-white transition-all shadow-lg shadow-slate-500/10 flex items-center justify-center gap-3 disabled:opacity-50"
                >
                    {#if weatherBackfilling}
                        <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    {/if}
                    {weatherBackfilling ? 'Filling Weather...' : 'Fill Weather Fields'}
                </button>
            </div>
        </div>
    </section>

    <!-- Batch Analysis -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Batch Analysis</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">Refine existing detections</p>
            </div>
        </div>

        <div class="space-y-4">
            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
                Run video analysis on all detections labeled as "Unknown Bird". This will queue background tasks to download clips and re-classify them.
            </p>
            <button
                onclick={handleAnalyzeUnknowns}
                disabled={analyzingUnknowns}
                aria-label="Analyze unknown birds"
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if analyzingUnknowns}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {analyzingUnknowns ? 'Queueing...' : 'Analyze All Unknowns'}
            </button>

            {#if analysisStatus && (analysisStatus.pending > 0 || analysisStatus.active > 0)}
                {@const remaining = analysisStatus.pending + analysisStatus.active}
                {@const processed = analysisTotal > 0 ? Math.max(0, analysisTotal - remaining) : 0}
                {@const progress = analysisTotal > 0 ? (processed / analysisTotal) * 100 : 0}
                
                <div class="mt-4 p-4 rounded-2xl bg-indigo-50/50 dark:bg-indigo-900/20 border border-indigo-100 dark:border-indigo-700/30 space-y-3 animate-in fade-in slide-in-from-top-2">
                    <div class="flex justify-between text-xs font-bold uppercase tracking-widest">
                        <span class="text-indigo-600 dark:text-indigo-400">Processing...</span>
                        <span class="text-slate-500">{processed} / {analysisTotal}</span>
                    </div>
                    <div class="w-full h-2 bg-white dark:bg-slate-800 rounded-full overflow-hidden border border-indigo-100 dark:border-indigo-700/50">
                        <div class="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500 ease-out" style="width: {progress}%"></div>
                    </div>
                    <div class="flex justify-between text-[10px] font-bold text-slate-400">
                        <span>Pending: {analysisStatus.pending}</span>
                        <span>Active: {analysisStatus.active}</span>
                    </div>
                    {#if analysisStatus.circuit_open}
                        <div class="text-[10px] font-bold text-amber-500 flex items-center gap-1 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                            Circuit Breaker Open (Paused due to failures)
                        </div>
                    {/if}
                </div>
            {/if}
        </div>
    </section>

    <!-- Danger Zone -->
    <section class="card-base rounded-3xl p-8 border-2 border-red-500/20 bg-red-500/5">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-red-500/10 flex items-center justify-center text-red-600 dark:text-red-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.danger.title')}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-red-500 mt-1">{$_('settings.danger.subtitle')}</p>
            </div>
        </div>

        <div class="space-y-4">
            <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">
                {$_('settings.danger.reset_desc')}
            </p>
            <button
                type="button"
                onclick={handleResetDatabase}
                disabled={resettingDatabase}
                aria-label={$_('settings.danger.reset_button')}
                class="w-full px-4 py-4 text-xs font-black uppercase tracking-widest rounded-2xl bg-red-500 hover:bg-red-600 text-white transition-all shadow-lg shadow-red-500/20 flex items-center justify-center gap-3 disabled:opacity-50"
            >
                {#if resettingDatabase}
                    <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                {/if}
                {resettingDatabase ? $_('settings.danger.resetting') : $_('settings.danger.reset_button')}
            </button>
            {#if resettingDatabase}
                <div class="h-2 rounded-full bg-red-100 dark:bg-red-900/30 overflow-hidden">
                    <div class="h-full bg-gradient-to-r from-red-500 via-rose-500 to-orange-400 animate-pulse"></div>
                </div>
            {/if}
        </div>
    </section>
</div>
