<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        todayCount: number;
        uniqueSpecies: number;
        mostSeenSpecies: string | null;
        mostSeenCount: number;
        audioConfirmations: number;
        topVisitorImageUrl?: string | null;
    }

    let { todayCount, uniqueSpecies, mostSeenSpecies, mostSeenCount, audioConfirmations, topVisitorImageUrl }: Props = $props();
</script>

<div class="stats-ribbon">
    <div class="flex items-center gap-3 mb-3">
        <h3 class="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {$_('dashboard.title')}
        </h3>
        <span class="text-[10px] font-semibold text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">
            {$_('dashboard.histogram.last_24h')}
        </span>
    </div>
    <!-- Stats grid -->
    <div class="relative grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
        <!-- Today's Count -->
        <div class="card-base flex items-center gap-3 p-3">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-teal-500 text-white shadow-md">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
            <div class="min-w-0">
                <div class="stat-number">{todayCount}</div>
                <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{$_('common.detections')}</div>
            </div>
        </div>

        <!-- Unique Species -->
        <div class="card-base flex items-center gap-3 p-3">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-emerald-500 text-white shadow-md">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
            </div>
            <div class="min-w-0">
                <div class="stat-number">{uniqueSpecies}</div>
                <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{$_('dashboard.stats.species')}</div>
            </div>
        </div>

        <!-- Most Seen -->
        <div class="card-base flex items-center gap-3 p-3">
            {#if topVisitorImageUrl}
                <div class="flex items-center justify-center w-12 h-12 rounded-xl overflow-hidden bg-slate-100 dark:bg-slate-700 shadow-md ring-2 ring-amber-400/40">
                    <img src={topVisitorImageUrl} alt={mostSeenSpecies || $_('dashboard.stats.top_visitor')} class="w-full h-full object-cover" />
                </div>
            {:else}
                <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-amber-500 text-white shadow-md">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                    </svg>
                </div>
            {/if}
            <div class="min-w-0 flex-1">
                {#if mostSeenSpecies}
                    <div class="text-lg font-bold text-slate-900 dark:text-white truncate" title={mostSeenSpecies}>
                        {mostSeenSpecies}
                    </div>
                    <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        {$_('dashboard.stats.top_visitor')}
                    </div>
                {:else}
                    <div class="text-lg font-bold text-slate-400 dark:text-slate-500">—</div>
                    <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{$_('dashboard.stats.top_visitor')}</div>
                {/if}
            </div>
        </div>

        <!-- Audio Confirmations -->
        <div class="card-base flex items-center gap-3 p-3">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-blue-500 text-white shadow-md relative">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
                {#if audioConfirmations > 0}
                    <span class="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full animate-pulse"></span>
                {/if}
            </div>
            <div class="min-w-0">
                <div class="stat-number">{audioConfirmations}</div>
                <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">{$_('dashboard.stats.audio')}</div>
            </div>
        </div>
    </div>
</div>
