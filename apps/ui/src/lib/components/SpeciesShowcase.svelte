<script lang="ts">
    import { tick } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import { swapDisplayOrder, type ShowcaseRow } from '../leaderboard/showcase';
    import { formatDate } from '../utils/datetime';

    /**
     * The leaderboard's showcase: the leading species expanded, the rest as tiles, in the
     * expanded-view manner of a photo library. Click a tile and it grows into the large
     * photograph while the one it replaces shrinks into the slot the tile left; nothing else
     * in the grid moves.
     *
     * Every species is one element for its whole life here. Bringing one forward changes what
     * that element is (a tile or the hero) and where the grid puts it; the movement between the
     * two boxes is measured before and after the change and animated on the element itself, so
     * the picture grows from exactly where it was to exactly where it ends up.
     *
     * Every photograph is honest about where it came from. A species' own tile is this
     * feeder's newest stored crop; where there is none, the species' reference image stands
     * in and is labelled as such, and where there is neither, a plain placeholder.
     */
    interface Props {
        rows: ShowcaseRow[];
        /** What the leader is, e.g. "Most detected this month". */
        eyebrow: string;
        /** What a species brought forward is, e.g. "Rank 5 this month"; the leader keeps `eyebrow`. */
        rankEyebrow: (rank: number) => string;
        countLabel: (count: number) => string;
        /** Species ranked beyond the tiles shown; the last tile points at the full rankings. */
        moreCount?: number;
        onopen: (key: string) => void;
        onmore?: () => void;
    }

    let { rows, eyebrow, rankEyebrow, countLabel, moreCount = 0, onopen, onmore }: Props = $props();

    // The leader is expanded until a click chooses another; a choice that leaves the ranking
    // (a new window or mode) falls back to the leader. Derived, so the first paint is already
    // right and nothing has to swap places on load.
    let chosenKey = $state<string | null>(null);
    const expandedKey = $derived(
        chosenKey !== null && rows.some((row) => row.key === chosenKey) ? chosenKey : (rows[0]?.key ?? null)
    );
    const expanded = $derived(rows.find((row) => row.key === expandedKey) ?? null);

    // Where each species sits in the grid. Rank order until a click trades two places; an
    // order that no longer names exactly these rows is a stale one and rank order returns.
    let displayOrder = $state<string[] | null>(null);
    const orderedRows = $derived.by(() => {
        const byKey = new Map(rows.map((row) => [row.key, row]));
        const usable =
            displayOrder !== null &&
            displayOrder.length === rows.length &&
            displayOrder.every((key) => byKey.has(key));
        const keys = usable && displayOrder !== null ? displayOrder : rows.map((row) => row.key);
        return keys.flatMap((key) => {
            const row = byKey.get(key);
            return row ? [row] : [];
        });
    });

    let reduceMotion = $state(false);
    $effect(() => {
        if (typeof window === 'undefined') return;
        const query = window.matchMedia('(prefers-reduced-motion: reduce)');
        const sync = () => {
            reduceMotion = query.matches || document.documentElement.classList.contains('reduced-motion');
        };
        sync();
        query.addEventListener('change', sync);
        return () => query.removeEventListener('change', sync);
    });
    const MORPH_MS = 560;
    // The tiles rise into place once, on first paint; a species changing places later moves by
    // the morph alone.
    const INTRO_MS = 1200;
    let introDone = $state(false);
    $effect(() => {
        if (introDone || rows.length === 0) return;
        const timer = setTimeout(() => (introDone = true), INTRO_MS);
        return () => clearTimeout(timer);
    });

    let grid = $state<HTMLElement | null>(null);

    function itemFor(key: string): HTMLElement | null {
        return grid?.querySelector<HTMLElement>(`[data-showcase-item="${CSS.escape(key)}"]`) ?? null;
    }

    /**
     * Move an element from the box it had to the box it has now. Width and height animate, so
     * the photograph is re-cropped as it grows rather than stretched; the translate keeps the
     * top-left corner on its path. The grid's tracks are fixed by the container, so a box in
     * flight never resizes a cell.
     */
    function morph(element: HTMLElement, from: DOMRect): void {
        for (const running of element.getAnimations()) running.cancel();
        const to = element.getBoundingClientRect();
        if (from.width === 0 || to.width === 0) return;
        element.classList.add('showcase-moving');
        const animation = element.animate(
            [
                {
                    transform: `translate(${from.left - to.left}px, ${from.top - to.top}px)`,
                    width: `${from.width}px`,
                    height: `${from.height}px`
                },
                { transform: 'none', width: `${to.width}px`, height: `${to.height}px` }
            ],
            { duration: MORPH_MS, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'none' }
        );
        const settle = () => element.classList.remove('showcase-moving');
        animation.addEventListener('finish', settle);
        animation.addEventListener('cancel', settle);
    }

    async function bringForward(key: string): Promise<void> {
        const outgoing = expandedKey;
        if (outgoing === null || key === outgoing) return;
        const before = new Map<string, DOMRect>();
        for (const candidate of [outgoing, key]) {
            const element = itemFor(candidate);
            if (element) before.set(candidate, element.getBoundingClientRect());
        }
        displayOrder = swapDisplayOrder(
            orderedRows.map((row) => row.key),
            outgoing,
            key
        );
        chosenKey = key;
        await tick();
        // The tile's button is gone with the tile; keyboard focus lands on the hero's own button.
        itemFor(key)?.querySelector<HTMLElement>('button')?.focus({ preventScroll: true });
        if (reduceMotion) return;
        for (const [candidate, from] of before) {
            const element = itemFor(candidate);
            if (element) morph(element, from);
        }
    }

    // A photograph that fails to load falls back to the next honest source, never to a hole.
    let failed = $state<Set<string>>(new Set());
    function markFailed(url: string): void {
        failed = new Set([...failed, url]);
    }
    type Picture = { url: string; source: 'feeder' | 'reference' } | null;
    function pictureFor(row: ShowcaseRow): Picture {
        if (row.photo && !failed.has(row.photo)) return { url: withAuthParams(row.photo), source: 'feeder' };
        if (row.reference && !failed.has(row.reference)) return { url: row.reference, source: 'reference' };
        return null;
    }
    function referenceLabel(row: ShowcaseRow): string {
        const source = row.referenceSource?.trim();
        return source
            ? $_('leaderboard.showcase_reference_from', {
                  values: { source },
                  default: 'Reference photo from {source}, not from this feeder'
              })
            : $_('leaderboard.showcase_reference', { default: 'Reference photo, not from this feeder' });
    }
    function confidence(row: ShowcaseRow): string | null {
        if (row.avgConfidence === null) return null;
        return `${Math.round(row.avgConfidence * 100)}%`;
    }
    function rankOf(row: ShowcaseRow): number {
        return rows.findIndex((candidate) => candidate.key === row.key) + 1;
    }
    function trendClass(row: ShowcaseRow, quiet: string): string {
        return (row.delta ?? 0) > 0 ? 'text-accent-300' : (row.delta ?? 0) < 0 ? 'text-rose-300' : quiet;
    }
</script>

{#if rows.length > 0 && expanded}
    <section
        bind:this={grid}
        class="showcase-grid relative grid gap-2 md:gap-2.5"
        class:showcase-intro={!introDone}
        data-leaderboard-showcase
        aria-label={eyebrow}
    >
        {#each orderedRows as row, index (row.key)}
            {@const isHero = row.key === expandedKey}
            {@const picture = pictureFor(row)}
            <div
                class="showcase-item group relative overflow-hidden border bg-slate-900 {isHero
                    ? 'showcase-hero z-20 rounded-2xl border-slate-200/70 bg-slate-950 dark:border-slate-700/50'
                    : 'rounded-xl border-slate-200/70 transition-[transform,box-shadow,border-color] duration-200 ease-out hover:-translate-y-1 hover:border-brand-400/70 hover:shadow-xl active:translate-y-0 active:scale-[0.98] focus-within:border-brand-400/70 motion-reduce:transform-none dark:border-slate-700/50'}"
                style="--showcase-order: {index}"
                data-showcase-item={row.key}
                data-showcase-hero={isHero ? row.key : undefined}
                data-showcase-tile={isHero ? undefined : row.key}
                data-photo-source={picture?.source ?? 'none'}
            >
                {#if picture}
                    <img
                        src={picture.url}
                        alt=""
                        loading={isHero ? 'eager' : 'lazy'}
                        decoding="async"
                        class="absolute inset-0 h-full w-full object-cover {isHero
                            ? 'showcase-drift motion-reduce:animate-none'
                            : 'transition-transform duration-300 ease-out group-hover:scale-[1.05] motion-reduce:transform-none'}"
                        onerror={() => markFailed(row.photo && picture.source === 'feeder' ? row.photo : (row.reference ?? ''))}
                    />
                {:else}
                    <div class="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-slate-800 via-slate-900 to-brand-950 text-slate-600" aria-hidden="true">
                        <svg class="h-1/4 w-1/4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg>
                    </div>
                {/if}

                {#if isHero}
                    <article class="showcase-hero-copy absolute inset-0" aria-label={row.displayName}>
                        <div class="absolute inset-0 bg-gradient-to-t from-slate-950/95 via-slate-950/40 to-slate-950/5" aria-hidden="true"></div>
                        <div class="absolute left-5 top-4 flex flex-wrap items-center gap-2">
                            <span class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/80" data-showcase-eyebrow>{rankOf(row) === 1 ? eyebrow : rankEyebrow(rankOf(row))}</span>
                            {#if picture?.source === 'reference'}
                                <span class="rounded-full border border-white/20 bg-slate-950/60 px-2 py-0.5 text-[10px] font-semibold text-white/85 backdrop-blur-sm" data-showcase-reference-note>
                                    {referenceLabel(row)}
                                </span>
                            {/if}
                        </div>
                        <div class="absolute inset-x-5 bottom-5">
                            <h3 class="font-display text-3xl font-bold leading-none text-white drop-shadow md:text-5xl">{row.displayName}</h3>
                            {#if row.subName}
                                <p class="mt-1 text-sm italic text-white/70">{row.subName}</p>
                            {/if}
                            <dl class="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[13px] text-white/80">
                                <div><dd class="inline text-xl font-bold tabular-nums text-white">{row.count.toLocaleString()}</dd> <dt class="inline">{countLabel(row.count)}</dt></div>
                                {#if row.trend}
                                    <div><dd class="inline font-semibold tabular-nums {trendClass(row, 'text-white/70')}">{row.trend}</dd> <dt class="inline">{$_('leaderboard.showcase_on_previous', { default: 'on the window before' })}</dt></div>
                                {/if}
                                {#if confidence(row)}
                                    <div><dd class="inline font-semibold tabular-nums text-white">{confidence(row)}</dd> <dt class="inline">{$_('leaderboard.avg_confidence', { default: 'Avg confidence' }).toLowerCase()}</dt></div>
                                {/if}
                                {#if row.lastSeen}
                                    <div><dt class="inline">{$_('leaderboard.last_seen', { default: 'Last seen' }).toLowerCase()}</dt> <dd class="inline font-semibold tabular-nums text-white">{formatDate(row.lastSeen)}</dd></div>
                                {/if}
                            </dl>
                            <button
                                type="button"
                                class="btn btn-secondary mt-4 min-h-10 px-4 text-xs"
                                onclick={() => onopen(row.key)}
                            >
                                {$_('leaderboard.view_species', { values: { species: row.displayName }, default: 'View {species}' })}
                            </button>
                        </div>
                    </article>
                {:else}
                    <button
                        type="button"
                        class="absolute inset-0 cursor-pointer text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
                        aria-label={$_('leaderboard.showcase_bring_forward', { values: { species: row.displayName }, default: 'Bring {species} forward' })}
                        onclick={() => bringForward(row.key)}
                    >
                        {#if picture?.source === 'reference'}
                            <span class="absolute right-1.5 top-1.5 rounded-full border border-white/20 bg-slate-950/65 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white/85" title={referenceLabel(row)} data-showcase-reference-badge>
                                {$_('leaderboard.showcase_reference_short', { default: 'Reference' })}
                            </span>
                        {/if}
                        <span class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/90 via-slate-950/50 to-transparent px-2 pb-1.5 pt-6">
                            <span class="block truncate text-[12px] font-semibold text-white">{row.displayName}</span>
                            <span class="block truncate text-[11px] tabular-nums text-white/75">
                                {rankOf(row)} · {row.count.toLocaleString()}
                                {#if row.trend}<span class="ml-1 {trendClass(row, 'text-white/60')}">{row.trend}</span>{/if}
                            </span>
                        </span>
                    </button>
                {/if}
            </div>
        {/each}
        {#if moreCount > 0}
            <button
                type="button"
                class="showcase-item flex items-center justify-center rounded-xl border border-dashed border-slate-300 px-2 text-center text-xs text-slate-500 transition-colors hover:border-brand-400 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:border-slate-600 dark:text-slate-400 dark:hover:text-brand-300"
                style="--showcase-order: {orderedRows.length}"
                onclick={() => onmore?.()}
                data-showcase-more
            >
                {$_('leaderboard.showcase_more', { values: { count: moreCount }, default: '{count} more below' })}
            </button>
        {/if}
    </section>
{/if}

<style>
    /*
     * The grid's tracks come from the container alone: a fixed aspect ratio and equal
     * fractional rows, so a box growing or shrinking between two cells never resizes a cell
     * and nothing but the two boxes moves. Phone: the hero across three columns and two rows,
     * tiles three to a row beneath. Wider: the hero on the left, three columns of tiles beside
     * it, its width tuned so the tiles come out square.
     */
    .showcase-grid {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        grid-auto-rows: minmax(0, 1fr);
        grid-auto-flow: row dense;
        aspect-ratio: 3 / 5;
    }

    .showcase-hero {
        grid-column: 1 / -1;
        grid-row: 1 / span 2;
    }

    @media (min-width: 768px) {
        .showcase-grid {
            grid-template-columns: minmax(0, 4.05fr) repeat(3, minmax(0, 1fr));
            aspect-ratio: 7.05 / 3;
        }

        .showcase-hero {
            grid-column: 1;
            grid-row: 1 / span 3;
        }
    }

    /* A box in flight crosses other tiles; it rides above them and below the hero. */
    .showcase-moving {
        z-index: 10;
    }

    .showcase-hero.showcase-moving {
        z-index: 20;
    }

    /* The hero's words arrive once the box has grown enough to hold them. */
    @keyframes showcase-fade {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    .showcase-hero-copy {
        animation: showcase-fade 0.32s ease-out 0.18s backwards;
    }

    /* The photograph breathes: a slow drift the eye reads as life, not as movement. */
    @keyframes showcase-drift {
        from {
            transform: scale(1.02) translate3d(0, 0, 0);
        }
        to {
            transform: scale(1.08) translate3d(-1%, -1.5%, 0);
        }
    }

    .showcase-drift {
        animation: showcase-drift 22s ease-in-out infinite alternate;
    }

    /* Tiles rise into place on first paint, in rank order. The fill is backwards only: a forwards
       fill would keep `transform: none` applied after the rise and swallow the hover lift. */
    @keyframes showcase-rise {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: none;
        }
    }

    .showcase-intro .showcase-item {
        animation: showcase-rise 0.45s cubic-bezier(0.2, 0.7, 0.2, 1) backwards;
        animation-delay: calc(0.12s + var(--showcase-order, 0) * 0.05s);
    }

    @media (prefers-reduced-motion: reduce) {
        .showcase-drift,
        .showcase-hero-copy,
        .showcase-intro .showcase-item {
            animation: none;
        }
    }

    :global(.reduced-motion) .showcase-drift,
    :global(.reduced-motion) .showcase-hero-copy,
    :global(.reduced-motion) .showcase-intro .showcase-item {
        animation: none;
    }
</style>
