<script lang="ts">
    import type { DailySpeciesSummary } from '../api';
    import { getThumbnailUrl } from '../api';
    import { settingsStore } from '../stores/settings';

    interface Props {
        species: DailySpeciesSummary[];
        onSpeciesClick?: (species: string) => void;
    }

    let { species, onSpeciesClick }: Props = $props();
</script>

<div class="space-y-4">
    <h3 class="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        Today's Top Visitors
    </h3>

    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {#each species as item}
            {@const preferScientific = $settingsStore?.scientific_name_primary ?? false}
            {@const displayName = (preferScientific ? (item.scientific_name || item.species) : (item.common_name || item.species))}
            <button 
                onclick={() => onSpeciesClick?.(item.species)}
                class="bg-white dark:bg-slate-800/50 rounded-xl p-3 border border-slate-200/80 dark:border-slate-700/50 text-left hover:border-teal-500 dark:hover:border-teal-400 transition-all group shadow-sm"
            >
                <div class="relative aspect-square rounded-lg overflow-hidden mb-3 bg-slate-100 dark:bg-slate-700">
                    <img 
                        src={getThumbnailUrl(item.latest_event)} 
                        alt={displayName}
                        class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                    />
                    <div class="absolute top-1.5 right-1.5 bg-teal-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full shadow-sm">
                        {item.count}
                    </div>
                </div>
                <p class="text-xs font-bold text-slate-900 dark:text-white truncate" title={displayName}>
                    {displayName}
                </p>
                <p class="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                    {item.count} visits
                </p>
            </button>
        {/each}

        {#if species.length === 0}
            <div class="col-span-full py-8 text-center bg-slate-50 dark:bg-slate-800/30 rounded-xl border border-dashed border-slate-300 dark:border-slate-700">
                <p class="text-xs text-slate-400">No visitors recorded yet today.</p>
            </div>
        {/if}
    </div>
</div>
