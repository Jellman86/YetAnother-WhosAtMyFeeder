<script lang="ts">
    import type { DailySpeciesSummary } from '../api';
    import { getThumbnailUrl } from '../api';
    import { settingsStore } from '../stores/settings';

    import { getBirdNames } from '../naming';

    interface Props {
        species: DailySpeciesSummary[];
        onSpeciesClick?: (species: string) => void;
    }

    let { species, onSpeciesClick }: Props = $props();

    // Ultra-reactive derivation
    let processedSpecies = $derived.by(() => {
        if (!species) return [];
        const showCommon = $settingsStore?.display_common_names ?? true;
        const preferSci = $settingsStore?.scientific_name_primary ?? false;
        
        return species.map(item => {
            const naming = getBirdNames(item, showCommon, preferSci);
            return {
                ...item,
                displayName: naming.primary,
                subName: naming.secondary
            };
        });
    });
</script>

<div class="space-y-4">
    <h3 class="text-sm font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        Today's Top Visitors
    </h3>

    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
        {#each processedSpecies as item}
            <button 
                onclick={() => onSpeciesClick?.(item.species)}
                class="bg-white dark:bg-slate-800/50 rounded-xl p-3 border border-slate-200/80 dark:border-slate-700/50 text-left hover:border-teal-500 dark:hover:border-teal-400 transition-all group shadow-sm flex flex-col h-full"
            >
                <div class="relative aspect-square rounded-lg overflow-hidden mb-3 bg-slate-100 dark:bg-slate-700">
                    <img 
                        src={getThumbnailUrl(item.latest_event)} 
                        alt={item.displayName}
                        class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                    />
                    <div class="absolute top-1.5 right-1.5 bg-teal-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full shadow-sm">
                        {item.count}
                    </div>
                </div>
                <div class="flex-1 min-w-0">
                    <p class="text-xs font-bold text-slate-900 dark:text-white truncate" title={item.displayName}>
                        {item.displayName}
                    </p>
                    {#if item.subName}
                        <p class="text-[10px] italic text-slate-500 dark:text-slate-400 truncate opacity-80 mt-0.5" title={item.subName}>
                            {item.subName}
                        </p>
                    {/if}
                </div>
                <p class="text-[10px] text-slate-400 dark:text-slate-500 mt-2 pt-2 border-t border-slate-100 dark:border-slate-700/50">
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