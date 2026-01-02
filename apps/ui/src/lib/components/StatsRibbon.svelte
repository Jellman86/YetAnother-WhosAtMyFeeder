<script lang="ts">
    interface Props {
        todayCount: number;
        uniqueSpecies: number;
        mostSeenSpecies: string | null;
        mostSeenCount: number;
        audioConfirmations: number;
    }

    let { todayCount, uniqueSpecies, mostSeenSpecies, mostSeenCount, audioConfirmations }: Props = $props();
</script>

<div class="stats-ribbon">
    <!-- Animated gradient line at top -->
    <div class="gradient-line"></div>

    <!-- Gradient mesh overlay -->
    <div class="absolute inset-0 bg-gradient-mesh opacity-60 pointer-events-none"></div>

    <!-- Stats grid -->
    <div class="relative grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
        <!-- Today's Count -->
        <div class="flex items-center gap-3 p-3 rounded-xl bg-white/50 dark:bg-slate-700/30 backdrop-blur-sm border border-white/60 dark:border-slate-600/30">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-teal-500 to-emerald-500 text-white shadow-lg shadow-teal-500/25">
                <svg class="w-6 h-6 animate-float" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
            </div>
            <div class="min-w-0">
                <div class="stat-number animate-count-up">{todayCount}</div>
                <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Today</div>
            </div>
        </div>

        <!-- Unique Species -->
        <div class="flex items-center gap-3 p-3 rounded-xl bg-white/50 dark:bg-slate-700/30 backdrop-blur-sm border border-white/60 dark:border-slate-600/30">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500 to-green-500 text-white shadow-lg shadow-emerald-500/25">
                <svg class="w-6 h-6 animate-float" style="animation-delay: 0.5s" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                </svg>
            </div>
            <div class="min-w-0">
                <div class="stat-number animate-count-up" style="animation-delay: 0.1s">{uniqueSpecies}</div>
                <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Species</div>
            </div>
        </div>

        <!-- Most Seen -->
        <div class="flex items-center gap-3 p-3 rounded-xl bg-white/50 dark:bg-slate-700/30 backdrop-blur-sm border border-white/60 dark:border-slate-600/30">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-lg shadow-amber-500/25">
                <svg class="w-6 h-6 animate-float" style="animation-delay: 1s" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                </svg>
            </div>
            <div class="min-w-0 flex-1">
                {#if mostSeenSpecies}
                    <div class="text-lg font-bold text-slate-900 dark:text-white truncate animate-count-up" style="animation-delay: 0.2s" title={mostSeenSpecies}>
                        {mostSeenSpecies}
                    </div>
                    <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">
                        Top Visitor ({mostSeenCount}x)
                    </div>
                {:else}
                    <div class="text-lg font-bold text-slate-400 dark:text-slate-500">—</div>
                    <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Top Visitor</div>
                {/if}
            </div>
        </div>

        <!-- Audio Confirmations -->
        <div class="flex items-center gap-3 p-3 rounded-xl bg-white/50 dark:bg-slate-700/30 backdrop-blur-sm border border-white/60 dark:border-slate-600/30">
            <div class="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-500 text-white shadow-lg shadow-blue-500/25 relative">
                <svg class="w-6 h-6 animate-float" style="animation-delay: 1.5s" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
                {#if audioConfirmations > 0}
                    <span class="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full animate-pulse"></span>
                {/if}
            </div>
            <div class="min-w-0">
                <div class="stat-number animate-count-up" style="animation-delay: 0.3s">{audioConfirmations}</div>
                <div class="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wide">Audio</div>
            </div>
        </div>
    </div>
</div>
