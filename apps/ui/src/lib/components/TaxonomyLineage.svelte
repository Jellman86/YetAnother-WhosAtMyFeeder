<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { fetchSpeciesLineage, type Taxon } from '../api/taxonomy';
    import { taxonLabel } from '../taxonomy/tree-model';
    import { logger } from '../utils/logger';
    import { isHoverPointer, isKeyboardFocus, TaxonPeek } from '../utils/taxon-peek.svelte';
    import FamilyTreeDialog from './FamilyTreeDialog.svelte';
    import TaxonCard from './TaxonCard.svelte';

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
    const peek = new TaxonPeek();

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
        <h4 id="taxonomy-lineage-heading" class="eyebrow">
            {$_('taxonomy.small_heading', { default: 'Family tree' })}
        </h4>
        <!-- A stepped ladder: each rank sits one step further in than the rank above it, joined by
             an elbow, so the eye walks down from class to species. Ranks stay in their own column,
             and a step is small enough that five of them fit a phone. -->
        <ol class="space-y-0.5" aria-label={$_('taxonomy.lineage_label', { default: 'Classification, from class to species' })} data-taxonomy-ladder>
            {#each steps as taxon, index (taxon.taxon_id)}
                {@const last = index === steps.length - 1}
                <li class="flex min-h-9 items-stretch gap-2" aria-current={last ? 'true' : undefined}>
                    <span class="w-16 shrink-0 self-center text-right text-3xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        {$_(`taxonomy.rank.${taxon.rank}`, { default: taxon.rank })}
                    </span>
                    <span class="relative flex min-w-0 flex-1 items-center" style="padding-left: {index * 1.125}rem">
                        {#if index > 0}
                            <!-- The elbow from the rank above: down from its node, then across to this one. -->
                            <span
                                class="pointer-events-none absolute -top-1/2 bottom-1/2 w-[1.125rem] rounded-bl-lg border-b-2 border-l-2 border-amber-300/80 dark:border-amber-400/50"
                                style="left: calc({index - 1} * 1.125rem + 0.4375rem)"
                                aria-hidden="true"
                            ></span>
                        {/if}
                        <span class="relative flex w-4 shrink-0 items-center justify-center" aria-hidden="true">
                            <span class="block rounded-full {last ? 'h-3.5 w-3.5 bg-amber-400 ring-2 ring-amber-200 dark:ring-amber-900' : 'h-2.5 w-2.5 bg-amber-400'}"></span>
                        </span>
                        <button
                            type="button"
                            class="ml-1.5 flex min-w-0 items-baseline gap-2 rounded-md px-1.5 py-1 text-left hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                            aria-expanded={peek.isOpen(taxon.taxon_id)}
                            onpointerenter={(event) => isHoverPointer(event) && peek.hover(taxon, last, event.currentTarget)}
                            onpointerleave={() => peek.leave()}
                            onfocus={(event) => isKeyboardFocus(event.currentTarget) && peek.focus(taxon, last, event.currentTarget)}
                            onblur={() => peek.leave()}
                            onclick={(event) => peek.toggle(taxon, last, event.currentTarget)}
                            data-taxon-peek-trigger
                        >
                            <span class="truncate text-sm {last ? 'font-bold text-slate-900 dark:text-white' : 'font-semibold text-slate-700 dark:text-slate-200'}">{taxonLabel(taxon)}</span>
                            {#if taxon.name && taxon.rank !== 'species'}
                                <span class="hidden truncate text-xs italic text-slate-500 dark:text-slate-400 sm:inline">{taxon.scientific_name}</span>
                            {/if}
                        </button>
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
        <button type="button" class="btn btn-secondary px-3 py-1.5 text-xs" onclick={() => {
                peek.close();
                open = true;
            }} data-taxonomy-open-tree>
            {$_('taxonomy.open', { default: 'Open the family tree' })}
        </button>
    </section>
{/if}

<TaxonCard {peek} />

{#if open && lineage}
    <FamilyTreeDialog {lineage} onclose={() => (open = false)} />
{/if}
