<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { fetchSpeciesLineage, type Taxon } from '../api/taxonomy';
    import { currentNamingStyle } from '../taxonomy/naming-style';
    import { byRank, taxonNames } from '../taxonomy/nomenclature';
    import { logger } from '../utils/logger';
    import { TaxonFactsStore } from '../utils/taxon-facts.svelte';
    import { isHoverPointer, isKeyboardFocus, TaxonPeek } from '../utils/taxon-peek.svelte';
    import FamilyTreeDialog from './FamilyTreeDialog.svelte';
    import TaxonCard from './TaxonCard.svelte';
    import TaxonNameText from './TaxonNameText.svelte';

    /**
     * Where this bird or animal belongs, in a line from its class down to it, with one line of
     * context and the way into the full family tree. Quiet when the catalogue does not know it:
     * nothing is shown rather than a gap that looks like an error.
     */
    interface Props {
        scientificName: string;
        /** A Garden animal: the catalogue holds only the model's animals, so no count is worldwide. */
        subject?: 'bird' | 'animal';
        /** Chrome around the lineage, such as a rule above it, drawn only when there is a lineage. */
        class?: string;
    }

    let { scientificName, subject = 'bird', class: className = '' }: Props = $props();

    let lineage = $state.raw<Taxon[] | null>(null);
    let loading = $state(true);
    let open = $state(false);
    const peek = new TaxonPeek();
    // What this install recorded, shared by the ladder's card and the tree it opens. Asked for when
    // a card first opens, so a record that is only read costs nothing more.
    const facts = new TaxonFactsStore();

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
    const steps = $derived(
        (lineage ?? []).filter((taxon) => taxon.principal && SHOWN.includes(taxon.rank)).sort(byRank)
    );
    const family = $derived(steps.find((taxon) => taxon.rank === 'family') ?? null);
    const style = $derived(currentNamingStyle());

    function lookCloser(): void {
        facts.request(steps.map((taxon) => taxon.taxon_id));
    }
</script>

{#if loading}
    <div class={className} aria-hidden="true">
        <div class="h-16 animate-pulse rounded-xl bg-slate-100 motion-reduce:animate-none dark:bg-slate-800"></div>
    </div>
{:else if steps.length > 1}
    <section class="space-y-3 {className}" aria-labelledby="taxonomy-lineage-heading" data-taxonomy-lineage>
        <h4 id="taxonomy-lineage-heading" class="eyebrow">
            {$_('taxonomy.small_heading', { default: 'Family tree' })}
        </h4>
        <!-- An indented ladder drawn as a cladogram: each rank one step in from the rank above,
             joined by a right-angled branch, ranks in their own column on the left. Rows touch, so
             each branch runs from the centre of the row above to the centre of its own. -->
        <ol aria-label={$_('taxonomy.lineage_label', { default: 'Classification, from class to species' })} data-taxonomy-ladder>
            {#each steps as taxon, index (taxon.taxon_id)}
                {@const last = index === steps.length - 1}
                {@const names = taxonNames(taxon, style)}
                <li class="relative flex min-h-11 items-stretch gap-3" aria-current={last ? 'true' : undefined} data-taxon-rank={taxon.rank}>
                    <span class="taxon-rank w-20 shrink-0 self-center text-right">
                        {$_(`taxonomy.rank.${taxon.rank}`, { default: taxon.rank })}
                    </span>
                    <span class="relative flex min-w-0 flex-1 items-center" style:padding-left="{index}rem">
                        {#if index > 0}
                            <span
                                class="pointer-events-none absolute -top-1/2 bottom-1/2 w-4 border-b border-l border-slate-400 dark:border-slate-500"
                                style:left="{index - 0.5}rem"
                                aria-hidden="true"
                            ></span>
                        {/if}
                        <span class="relative flex w-4 shrink-0 items-center justify-center" aria-hidden="true">
                            {#if last}
                                <span class="block h-2.5 w-2.5 rounded-full bg-slate-900 ring-2 ring-slate-900 ring-offset-2 ring-offset-surface dark:bg-white dark:ring-white" data-taxonomy-marker="current"></span>
                            {:else}
                                <span class="block h-2 w-2 rounded-full bg-slate-500 dark:bg-slate-400" data-taxonomy-marker="path"></span>
                            {/if}
                        </span>
                        <button
                            type="button"
                            class="ml-2 flex min-h-11 min-w-0 flex-col justify-center rounded-lg px-2 text-left hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
                            aria-expanded={peek.isOpen(taxon.taxon_id)}
                            onpointerenter={(event) => {
                                if (!isHoverPointer(event)) return;
                                lookCloser();
                                peek.hover(taxon, last, event.currentTarget);
                            }}
                            onpointerleave={() => peek.leave()}
                            onfocus={(event) => {
                                if (!isKeyboardFocus(event.currentTarget)) return;
                                lookCloser();
                                peek.focus(taxon, last, event.currentTarget);
                            }}
                            onblur={() => peek.leave()}
                            onclick={(event) => {
                                lookCloser();
                                peek.toggle(taxon, last, event.currentTarget);
                            }}
                            data-taxon-peek-trigger
                        >
                            <TaxonNameText
                                name={names.primary}
                                class="truncate text-sm leading-5 {last ? 'font-bold text-slate-900 dark:text-white' : 'font-medium text-slate-700 dark:text-slate-200'}"
                            />
                            {#if names.secondary}
                                <TaxonNameText name={names.secondary} class="truncate text-2xs leading-4 text-slate-500 dark:text-slate-400" />
                            {/if}
                        </button>
                    </span>
                </li>
            {/each}
        </ol>
        {#if subject === 'bird' && family && family.species_count}
            <p class="text-xs tabular-nums text-slate-500 dark:text-slate-400" data-taxonomy-lineage-context>
                {$_('taxonomy.context', {
                    values: { group: taxonNames(family, style).primary.text, total: family.species_count, seen: family.seen_species ?? 0 },
                    default: '{group}: {total, plural, one {# species} other {# species}} worldwide, {seen} seen at this feeder.'
                })}
            </p>
        {/if}
        <button type="button" class="btn btn-secondary min-h-11 px-4" onclick={() => {
                peek.close();
                open = true;
            }} data-taxonomy-open-tree>
            {$_('taxonomy.open', { default: 'Open the family tree' })}
        </button>
    </section>
{/if}

<TaxonCard {peek} {facts} {subject} />

{#if open && lineage}
    <FamilyTreeDialog {lineage} {facts} {subject} onclose={() => (open = false)} />
{/if}
