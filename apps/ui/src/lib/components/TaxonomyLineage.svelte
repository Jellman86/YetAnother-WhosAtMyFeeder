<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { fetchSpeciesLineage, type Taxon } from '../api/taxonomy';
    import { taxonLabel } from '../taxonomy/tree-model';
    import { logger } from '../utils/logger';
    import FamilyTreeDialog from './FamilyTreeDialog.svelte';

    /**
     * Where this bird belongs, in a line from its class down to it, with one line of context and
     * the way into the full family tree. Quiet when the catalogue does not know the bird: nothing
     * is shown rather than a gap that looks like an error.
     */
    interface Props {
        scientificName: string;
    }

    let { scientificName }: Props = $props();

    let lineage = $state.raw<Taxon[] | null>(null);
    let loading = $state(true);
    let open = $state(false);

    $effect(() => {
        const name = scientificName.trim();
        lineage = null;
        loading = Boolean(name);
        if (!name) return;
        const controller = new AbortController();
        fetchSpeciesLineage(name, controller.signal)
            .then((response) => {
                if (!controller.signal.aborted) lineage = response.lineage;
            })
            .catch((error) => {
                if (controller.signal.aborted) return;
                lineage = null;
                logger.debug('Lineage unavailable', { scientificName: name, error });
            })
            .finally(() => {
                if (!controller.signal.aborted) loading = false;
            });
        return () => controller.abort();
    });

    // The ranks a reader needs, from the class down: kingdom and phylum belong in the full view.
    const SHOWN = ['class', 'order', 'family', 'genus', 'species'];
    const steps = $derived((lineage ?? []).filter((taxon) => taxon.principal && SHOWN.includes(taxon.rank)));
    const family = $derived(steps.find((taxon) => taxon.rank === 'family') ?? null);
</script>

{#if loading}
    <div class="h-16 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" aria-hidden="true"></div>
{:else if steps.length > 1}
    <section class="space-y-2" aria-labelledby="taxonomy-lineage-heading" data-taxonomy-lineage>
        <h4 id="taxonomy-lineage-heading" class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            {$_('taxonomy.small_heading', { default: 'Family tree' })}
        </h4>
        <!-- A ladder, one rank per row, so a long family name never wraps the line into ragged rows. -->
        <ol aria-label={$_('taxonomy.lineage_label', { default: 'Classification, from class to species' })}>
            {#each steps as taxon, index (taxon.taxon_id)}
                {@const first = index === 0}
                {@const last = index === steps.length - 1}
                <li class="flex items-stretch gap-3" aria-current={last ? 'true' : undefined}>
                    <span class="w-16 shrink-0 self-center text-right text-[10px] uppercase tracking-wide text-slate-400">
                        {$_(`taxonomy.rank.${taxon.rank}`, { default: taxon.rank })}
                    </span>
                    <span class="relative flex w-4 shrink-0 items-center justify-center" aria-hidden="true">
                        <span class="absolute left-1/2 w-0.5 -translate-x-1/2 bg-amber-300/70 {first ? 'top-1/2' : 'top-0'} {last ? 'bottom-1/2' : 'bottom-0'}"></span>
                        <span class="relative block rounded-full {last ? 'h-3.5 w-3.5 bg-amber-400 ring-2 ring-amber-200 dark:ring-amber-900' : 'h-2.5 w-2.5 bg-amber-400'}"></span>
                    </span>
                    <span class="flex min-w-0 flex-1 items-baseline gap-2 py-1">
                        <span class="truncate text-sm {last ? 'font-bold text-slate-900 dark:text-white' : 'font-semibold text-slate-700 dark:text-slate-200'}">{taxonLabel(taxon)}</span>
                        {#if taxon.name && taxon.rank !== 'species'}
                            <span class="hidden truncate text-xs italic text-slate-500 dark:text-slate-400 sm:inline">{taxon.scientific_name}</span>
                        {/if}
                    </span>
                </li>
            {/each}
        </ol>
        {#if family && family.species_count}
            <p class="text-xs text-slate-500 dark:text-slate-400" data-taxonomy-lineage-context>
                {$_('taxonomy.context', {
                    values: { group: taxonLabel(family), total: family.species_count, seen: family.seen_species ?? 0 },
                    default: '{group}: {total} species worldwide, {seen} seen at this feeder.'
                })}
            </p>
        {/if}
        <button type="button" class="btn btn-secondary px-3 py-1.5 text-xs" onclick={() => (open = true)} data-taxonomy-open-tree>
            {$_('taxonomy.open', { default: 'Open the family tree' })}
        </button>
    </section>
{/if}

{#if open && lineage}
    <FamilyTreeDialog {lineage} onclose={() => (open = false)} />
{/if}
