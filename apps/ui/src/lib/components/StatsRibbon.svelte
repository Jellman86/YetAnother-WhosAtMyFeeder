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

    let {
        todayCount,
        uniqueSpecies,
        mostSeenSpecies,
        mostSeenCount,
        audioConfirmations,
        topVisitorImageUrl
    }: Props = $props();
</script>

<section
    data-dashboard-overview
    class="overflow-hidden rounded-3xl border border-slate-200/80 bg-white/80 shadow-sm ring-1 ring-slate-900/5 dark:border-slate-700/70 dark:bg-slate-900/55 dark:ring-white/5"
>
    <header class="flex flex-col gap-3 bg-gradient-to-r from-teal-50/90 via-emerald-50/50 to-white/40 px-5 py-4 dark:from-teal-950/40 dark:via-emerald-950/20 dark:to-slate-900/20 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div class="flex items-center gap-3">
            <span class="flex h-10 w-10 items-center justify-center rounded-2xl border border-teal-200/80 bg-white/80 text-teal-700 shadow-sm dark:border-teal-800/70 dark:bg-slate-900/70 dark:text-teal-300" aria-hidden="true">
                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M5 16c2.5-1.5 3.5-4 3.5-7.5 2.2 2.7 5.2 3.8 9 3.2-1.2 3.8-4.2 6.3-8.1 6.3H7l-2 2v-4z" />
                    <path stroke-linecap="round" d="M16.5 8.5 20 7l-2.2 3" />
                </svg>
            </span>
            <div>
                <h1 class="font-display text-2xl font-bold tracking-tight text-slate-950 dark:text-white">{$_('dashboard.title')}</h1>
                <p class="text-sm text-slate-500 dark:text-slate-400">{$_('page_subtitle.dashboard')}</p>
            </div>
        </div>
        <span class="inline-flex w-fit items-center gap-2 rounded-full border border-teal-200/80 bg-white/70 px-3 py-1.5 text-xs font-semibold text-teal-800 dark:border-teal-800/70 dark:bg-slate-900/60 dark:text-teal-200">
            <span class="h-2 w-2 rounded-full bg-teal-500" aria-hidden="true"></span>
            {$_('dashboard.histogram.last_24h')}
        </span>
    </header>

    <dl class="grid grid-cols-2 border-t border-slate-200/80 dark:border-slate-700/70 md:grid-cols-4 md:divide-x md:divide-slate-200/80 dark:md:divide-slate-700/70">
        <div class="min-w-0 border-b border-r border-slate-200/80 p-4 dark:border-slate-700/70 md:border-b-0 md:border-r-0 sm:p-5">
            <dt class="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                <svg class="h-4 w-4 text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M8 7V3m8 4V3M5 10h14M5 21h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z" /></svg>
                {$_('common.detections')}
            </dt>
            <dd class="mt-2 font-display text-3xl font-bold tabular-nums text-slate-950 dark:text-white">{todayCount.toLocaleString()}</dd>
        </div>

        <div class="min-w-0 border-b border-slate-200/80 p-4 dark:border-slate-700/70 md:border-b-0 sm:p-5">
            <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">
                {$_('dashboard.stats.species')}
            </dt>
            <dd class="mt-2 font-display text-3xl font-bold tabular-nums text-slate-950 dark:text-white">{uniqueSpecies.toLocaleString()}</dd>
        </div>

        <div class="min-w-0 border-r border-slate-200/80 p-4 dark:border-slate-700/70 md:border-r-0 sm:p-5">
            <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('dashboard.stats.top_visitor')}</dt>
            <dd class="mt-2 flex min-w-0 items-center gap-3">
                <span
                    data-dashboard-top-visitor-portrait
                    class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-white bg-slate-100 text-slate-400 shadow-sm ring-1 ring-teal-200 dark:border-slate-800 dark:bg-slate-800 dark:ring-teal-800 sm:h-11 sm:w-11"
                >
                    {#if topVisitorImageUrl}
                        <img src={topVisitorImageUrl} alt="" class="h-full w-full object-cover" />
                    {:else}
                        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 16c2.5-1.5 3.5-4 3.5-7.5 2.2 2.7 5.2 3.8 9 3.2-1.2 3.8-4.2 6.3-8.1 6.3H7l-2 2v-4z" /></svg>
                    {/if}
                </span>
                <span class="min-w-0">
                    <span class="block font-display text-base font-bold leading-tight text-slate-950 dark:text-white sm:text-lg" title={mostSeenSpecies ?? undefined}>{mostSeenSpecies || '—'}</span>
                    {#if mostSeenSpecies}
                        <span class="block text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.top_visitors_count', { values: { count: mostSeenCount } })}</span>
                    {/if}
                </span>
            </dd>
        </div>

        <div class="min-w-0 p-4 sm:p-5">
            <dt class="flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                <svg class="h-4 w-4 text-sky-600 dark:text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 0 1-14 0m7 7v3m-4 0h8M9 5a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0V5Z" /></svg>
                {$_('dashboard.stats.audio')}
            </dt>
            <dd class="mt-2 flex items-baseline gap-2">
                <span class="font-display text-3xl font-bold tabular-nums text-slate-950 dark:text-white">{audioConfirmations.toLocaleString()}</span>
                {#if audioConfirmations > 0}<span class="text-xs font-semibold text-emerald-700 dark:text-emerald-300">{$_('dashboard.hero.audio_confirmed')}</span>{/if}
            </dd>
        </div>
    </dl>
</section>
