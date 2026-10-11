<script lang="ts">
    import { untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { taxonLabel } from '../taxonomy/tree-model';
    import { speciesPicture } from '../utils/taxon-pictures';
    import type { TaxonPeek } from '../utils/taxon-peek.svelte';
    import { portal } from '../utils/portal';

    /**
     * The card a taxon's name opens: what it is, how big the group is, what was seen of it here,
     * and for a species a reference photograph to compare a capture against. Portalled and placed
     * in viewport coordinates, so no scrolling container clips it.
     */
    interface Props {
        peek: TaxonPeek;
    }

    let { peek }: Props = $props();

    const WIDTH = 240;
    const GAP = 8;
    const MARGIN = 8;

    const anchor = $derived(peek.anchor);
    const taxon = $derived(anchor?.taxon ?? null);
    const isSpecies = $derived(taxon?.rank === 'species');

    // Bumped as the page scrolls or resizes, so the card is placed against where its name is now.
    let frame = $state(0);
    let cardHeight = $state(0);

    const position = $derived.by(() => {
        void frame;
        if (!anchor) return null;
        const rect = anchor.element.getBoundingClientRect();
        const estimated = cardHeight || (isSpecies ? 300 : 140);
        const above = rect.bottom + GAP + estimated > window.innerHeight && rect.top - GAP - estimated > 0;
        const centre = (rect.left + rect.right) / 2;
        const left = Math.min(Math.max(centre - WIDTH / 2, MARGIN), window.innerWidth - WIDTH - MARGIN);
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

    let picture = $state<{ name: string; url: string | null; state: 'loading' | 'ready' | 'none' | 'failed' } | null>(null);

    $effect(() => {
        if (!taxon || taxon.rank !== 'species') return;
        const name = taxon.scientific_name;
        // Read untracked: the picture this effect sets must not re-run it and cancel its own lookup.
        if (untrack(() => picture?.name) === name) return;
        picture = { name, url: null, state: 'loading' };
        let live = true;
        void speciesPicture(name).then((url) => {
            if (live && picture?.name === name) picture = { name, url, state: url ? 'ready' : 'none' };
        });
        return () => {
            live = false;
        };
    });

    function seenLine(): string | null {
        if (!taxon) return null;
        if (taxon.rank === 'species') {
            return (taxon.seen_count ?? 0) > 0
                ? $_('taxonomy.captures_here', { values: { count: taxon.seen_count }, default: '{count} captures here' })
                : $_('taxonomy.not_seen_here', { default: 'Not seen at this feeder yet' });
        }
        return $_('taxonomy.group_summary', {
            values: { total: taxon.species_count ?? 0, seen: taxon.seen_species ?? 0 },
            default: '{total} species worldwide, {seen} seen here'
        });
    }
</script>

{#if anchor && taxon && position}
    <div
        use:portal
        class="pointer-events-auto fixed z-[90] w-60 overflow-hidden rounded-2xl border border-slate-200 bg-white text-left shadow-xl dark:border-slate-700 dark:bg-slate-900"
        style:left="{position.left}px"
        style:top="{position.top}px"
        role="group"
        aria-label={taxonLabel(taxon)}
        bind:clientHeight={cardHeight}
        onpointerenter={() => peek.stay()}
        onpointerleave={() => peek.leave()}
        data-taxon-card
    >
        {#if isSpecies}
            <div class="relative h-36 w-full bg-slate-100 dark:bg-slate-800">
                {#if picture?.state === 'ready' && picture.url}
                    <img
                        src={picture.url}
                        alt={$_('detection.species_reference_alt', { values: { species: taxonLabel(taxon) }, default: 'Reference photograph of {species}' })}
                        class="h-full w-full object-cover"
                        onerror={() => {
                            if (picture) picture = { ...picture, state: 'failed' };
                        }}
                        data-taxon-card-picture
                    />
                    <span class="absolute bottom-1.5 left-1.5 rounded-full bg-slate-950/60 px-2 py-0.5 text-3xs font-semibold text-white">
                        {$_('taxonomy.reference_photo', { default: 'Reference photo' })}
                    </span>
                {:else if picture?.state === 'loading'}
                    <div class="h-full w-full animate-pulse" aria-hidden="true"></div>
                {:else}
                    <div class="flex h-full w-full flex-col items-center justify-center gap-1 text-slate-400" data-taxon-card-no-picture>
                        <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 18 9 13l3 3 2-2 6 6M15 8h.01M5 4h14a1 1 0 0 1 1 1v14H4V5a1 1 0 0 1 1-1Z" stroke-linecap="round" stroke-linejoin="round" /></svg>
                        <span class="text-2xs">{$_('taxonomy.no_reference_photo', { default: 'No reference photo' })}</span>
                    </div>
                {/if}
            </div>
        {/if}
        <div class="space-y-1 p-3">
            <p class="text-3xs font-semibold uppercase tracking-[0.12em] text-slate-400">{$_(`taxonomy.rank.${taxon.rank}`, { default: taxon.rank })}</p>
            <p class="text-sm font-bold leading-snug {anchor.current ? 'text-amber-600 dark:text-amber-300' : 'text-slate-900 dark:text-white'}">{taxonLabel(taxon)}</p>
            {#if taxon.name}<p class="text-xs italic text-slate-500 dark:text-slate-400">{taxon.scientific_name}</p>{/if}
            {#if seenLine()}
                <p class="pt-1 text-xs {(taxon.seen_species ?? 0) > 0 ? 'font-semibold text-emerald-700 dark:text-emerald-300' : 'text-slate-500 dark:text-slate-400'}" data-taxon-card-seen>{seenLine()}</p>
            {/if}
        </div>
    </div>
{/if}
