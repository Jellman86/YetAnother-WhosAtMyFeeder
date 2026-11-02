<script lang="ts">
    import { untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { currentNamingStyle } from '../taxonomy/naming-style';
    import { taxonNames } from '../taxonomy/nomenclature';
    import { speciesPicture, type ReferencePicture } from '../utils/taxon-pictures';
    import type { TaxonPeek } from '../utils/taxon-peek.svelte';
    import { portal } from '../utils/portal';
    import TaxonNameText from './TaxonNameText.svelte';

    /**
     * The card a taxon's name opens: what it is, how big the group is, what was seen of it here,
     * and for a species a reference photograph to compare a capture against. Portalled and placed
     * in viewport coordinates, so no scrolling container clips it.
     */
    interface Props {
        peek: TaxonPeek;
        /** A Garden animal: what was seen here counts bird visits, so the card does not claim it. */
        subject?: 'bird' | 'animal';
    }

    let { peek, subject = 'bird' }: Props = $props();

    const GAP = 8;
    const MARGIN = 8;

    const anchor = $derived(peek.anchor);
    const taxon = $derived(anchor?.taxon ?? null);
    const isSpecies = $derived(taxon?.rank === 'species');
    const names = $derived(taxon ? taxonNames(taxon, currentNamingStyle()) : null);

    // Bumped as the page scrolls or resizes, so the card is placed against where its name is now.
    let frame = $state(0);
    let cardHeight = $state(0);
    // Measured rather than assumed: the card is sized in rem, so the reader's text size sets its width.
    let cardWidth = $state(0);

    const position = $derived.by(() => {
        void frame;
        if (!anchor) return null;
        const rect = anchor.element.getBoundingClientRect();
        const estimated = cardHeight || (isSpecies ? 300 : 140);
        const above = rect.bottom + GAP + estimated > window.innerHeight && rect.top - GAP - estimated > 0;
        const centre = (rect.left + rect.right) / 2;
        const width = cardWidth || 240;
        const left = Math.min(Math.max(centre - width / 2, MARGIN), window.innerWidth - width - MARGIN);
        return { left, top: above ? rect.top - GAP - estimated : rect.bottom + GAP };
    });

    $effect(() => {
        if (!anchor) return;
        const element = anchor.element;
        let pending: number | null = null;
        const follow = () => {
            if (pending !== null) return;
            pending = requestAnimationFrame(() => {
                pending = null;
                const rect = element.getBoundingClientRect();
                // A name scrolled out of sight closes its card: a card pointing at nothing helps no one.
                if (!element.isConnected || rect.bottom < 0 || rect.top > window.innerHeight) peek.close();
                else frame += 1;
            });
        };
        // A tap elsewhere closes a pinned card; another name is a trigger and handles itself.
        const outside = (event: PointerEvent) => {
            const target = event.target;
            if (!(target instanceof Element)) return;
            if (target.closest('[data-taxon-card], [data-taxon-peek-trigger]')) return;
            peek.close();
        };
        // Escape closes the card before anything behind it: the record or the tree stays open.
        const escape = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            peek.close();
        };
        window.addEventListener('scroll', follow, true);
        window.addEventListener('resize', follow);
        window.addEventListener('keydown', escape, true);
        document.addEventListener('pointerdown', outside, true);
        return () => {
            if (pending !== null) cancelAnimationFrame(pending);
            window.removeEventListener('scroll', follow, true);
            window.removeEventListener('resize', follow);
            window.removeEventListener('keydown', escape, true);
            document.removeEventListener('pointerdown', outside, true);
        };
    });

    let picture = $state<{ name: string; reference: ReferencePicture | null; state: 'loading' | 'ready' | 'none' | 'failed' } | null>(null);

    // Keyed by the name, not the taxon object: hovering, focusing or pinning the same species
    // places a fresh proxied taxon, and re-running the lookup for it once stranded the card loading.
    const pictureName = $derived(isSpecies ? (taxon?.scientific_name ?? null) : null);

    $effect(() => {
        const name = pictureName;
        if (!name) return;
        // Read untracked: the picture this effect sets must not re-run it.
        if (untrack(() => picture?.name) === name) return;
        picture = { name, reference: null, state: 'loading' };
        // A result for a name the card has moved away from is dropped by the name check.
        void speciesPicture(name).then((reference) => {
            if (picture?.name === name) picture = { name, reference, state: reference ? 'ready' : 'none' };
        });
    });

    function seenLine(): string | null {
        if (!taxon || subject === 'animal') return null;
        if (taxon.rank === 'species') {
            return (taxon.seen_count ?? 0) > 0
                ? $_('taxonomy.captures_here', { values: { count: taxon.seen_count }, default: '{count, plural, one {# capture here} other {# captures here}}' })
                : $_('taxonomy.not_seen_here', { default: 'Not seen at this feeder yet' });
        }
        return $_('taxonomy.group_counts', {
            values: { total: taxon.species_count ?? 0, seen: taxon.seen_species ?? 0 },
            default: '{total, plural, one {# species} other {# species}} worldwide, {seen} seen here'
        });
    }
</script>

{#if anchor && taxon && names && position}
    <div
        use:portal
        class="pointer-events-auto fixed z-[90] w-60 overflow-hidden rounded-xl border border-line bg-surface text-left shadow-lg"
        style:left="{position.left}px"
        style:top="{position.top}px"
        role="group"
        aria-label={names.primary.text}
        bind:clientHeight={cardHeight}
        bind:clientWidth={cardWidth}
        onpointerenter={() => peek.stay()}
        onpointerleave={() => peek.leave()}
        data-taxon-card
    >
        {#if isSpecies}
            <div class="relative h-36 w-full bg-surface-raised">
                {#if picture?.state === 'ready' && picture.reference}
                    <img
                        src={picture.reference.url}
                        alt={$_('detection.species_reference_alt', { values: { species: names.primary.text }, default: 'Reference photograph of {species}' })}
                        class="h-full w-full object-cover"
                        onerror={() => {
                            if (picture) picture = { ...picture, state: 'failed' };
                        }}
                        data-taxon-card-picture
                    />
                    <span class="absolute bottom-1.5 left-1.5 max-w-full truncate rounded-md bg-slate-950/70 px-1.5 py-0.5 text-3xs font-medium text-white" data-taxon-card-attribution>
                        {picture.reference.source
                            ? $_('taxonomy.photo_source', { values: { source: picture.reference.source }, default: 'Reference photo: {source}' })
                            : $_('taxonomy.reference_photo', { default: 'Reference photo' })}
                    </span>
                {:else if picture?.state === 'loading'}
                    <div class="h-full w-full animate-pulse motion-reduce:animate-none" aria-hidden="true"></div>
                {:else}
                    <div class="flex h-full w-full flex-col items-center justify-center gap-1 text-slate-500 dark:text-slate-400" data-taxon-card-no-picture>
                        <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 18 9 13l3 3 2-2 6 6M15 8h.01M5 4h14a1 1 0 0 1 1 1v14H4V5a1 1 0 0 1 1-1Z" stroke-linecap="round" stroke-linejoin="round" /></svg>
                        <span class="text-2xs">{$_('taxonomy.no_reference_photo', { default: 'No reference photo' })}</span>
                    </div>
                {/if}
            </div>
        {/if}
        <div class="space-y-1 p-3">
            <p class="taxon-rank" data-taxon-card-rank>
                {$_(`taxonomy.rank.${taxon.rank}`, { default: taxon.rank })}{#if anchor.current}<span class="font-normal normal-case tracking-normal">{` · ${subject === 'animal'
                    ? $_('taxonomy.legend_this_animal', { default: 'This animal' })
                    : $_('taxonomy.legend_this_bird', { default: 'This bird' })}`}</span>{/if}
            </p>
            <p class="text-sm font-semibold leading-snug text-slate-900 dark:text-white"><TaxonNameText name={names.primary} /></p>
            {#if names.secondary}<p class="text-xs text-slate-600 dark:text-slate-300"><TaxonNameText name={names.secondary} /></p>{/if}
            {#if seenLine()}
                <p class="pt-1 text-xs tabular-nums {(taxon.seen_species ?? 0) > 0 ? 'font-semibold text-emerald-700 dark:text-emerald-300' : 'text-slate-500 dark:text-slate-400'}" data-taxon-card-seen>{seenLine()}</p>
            {/if}
        </div>
    </div>
{/if}
