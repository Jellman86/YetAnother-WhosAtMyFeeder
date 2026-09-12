<script lang="ts">
    import { crossfade } from 'svelte/transition';
    import { flip } from 'svelte/animate';
    import { cubicOut } from 'svelte/easing';
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import type { ShowcaseRow } from '../leaderboard/showcase';
    import { formatDate } from '../utils/datetime';

    /**
     * The leaderboard's showcase: the leading species expanded, the rest as tiles, in the
     * expanded-view manner of a photo library. Click a tile and it grows into the large
     * photograph while the one it replaces folds back into the grid; the two swap places
     * rather than cutting.
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
    const tiles = $derived(rows.filter((row) => row.key !== expandedKey));

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
    const [send, receive] = crossfade({
        duration: () => (reduceMotion ? 0 : MORPH_MS),
        easing: cubicOut,
        fallback(node) {
            const style = getComputedStyle(node);
            const transform = style.transform === 'none' ? '' : style.transform;
            return {
                duration: reduceMotion ? 0 : 320,
                easing: cubicOut,
                css: (t) => `opacity: ${t}; transform: ${transform} scale(${0.96 + 0.04 * t});`
            };
        }
    });

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
</script>

{#if rows.length > 0}
    <section
        class="grid gap-3 md:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]"
        data-leaderboard-showcase
        aria-label={eyebrow}
    >
        {#if expanded}
            {@const picture = pictureFor(expanded)}
            {#key expanded.key}
                <article
                    class="showcase-hero relative min-h-[300px] overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-950 md:min-h-[420px] dark:border-slate-700/50"
                    in:receive={{ key: expanded.key }}
                    out:send={{ key: expanded.key }}
                    data-showcase-hero={expanded.key}
                    data-photo-source={picture?.source ?? 'none'}
                >
                    {#if picture}
                        <img
                            src={picture.url}
                            alt=""
                            decoding="async"
                            class="showcase-drift absolute inset-0 h-full w-full object-cover motion-reduce:animate-none"
                            onerror={() => markFailed(expanded.photo && picture.source === 'feeder' ? expanded.photo : (expanded.reference ?? ''))}
                        />
                    {:else}
                        <div class="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-slate-800 via-slate-900 to-brand-950 text-slate-600" aria-hidden="true">
                            <svg class="h-20 w-20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg>
                        </div>
                    {/if}
                    <div class="absolute inset-0 bg-gradient-to-t from-slate-950/95 via-slate-950/40 to-slate-950/5" aria-hidden="true"></div>
                    <div class="absolute left-5 top-4 flex flex-wrap items-center gap-2">
                        <span class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/80" data-showcase-eyebrow>{rankOf(expanded) === 1 ? eyebrow : rankEyebrow(rankOf(expanded))}</span>
                        {#if picture?.source === 'reference'}
                            <span class="rounded-full border border-white/20 bg-slate-950/60 px-2 py-0.5 text-[10px] font-semibold text-white/85 backdrop-blur-sm" data-showcase-reference-note>
                                {referenceLabel(expanded)}
                            </span>
                        {/if}
                    </div>
                    <div class="absolute inset-x-5 bottom-5">
                        <h3 class="font-display text-3xl font-bold leading-none text-white drop-shadow md:text-5xl">{expanded.displayName}</h3>
                        {#if expanded.subName}
                            <p class="mt-1 text-sm italic text-white/70">{expanded.subName}</p>
                        {/if}
                        <dl class="mt-3 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[13px] text-white/80">
                            <div><dd class="inline text-xl font-bold tabular-nums text-white">{expanded.count.toLocaleString()}</dd> <dt class="inline">{countLabel(expanded.count)}</dt></div>
                            {#if expanded.trend}
                                <div><dd class="inline font-semibold tabular-nums {(expanded.delta ?? 0) > 0 ? 'text-accent-300' : (expanded.delta ?? 0) < 0 ? 'text-rose-300' : 'text-white/70'}">{expanded.trend}</dd> <dt class="inline">{$_('leaderboard.showcase_on_previous', { default: 'on the window before' })}</dt></div>
                            {/if}
                            {#if confidence(expanded)}
                                <div><dd class="inline font-semibold tabular-nums text-white">{confidence(expanded)}</dd> <dt class="inline">{$_('leaderboard.avg_confidence', { default: 'Avg confidence' }).toLowerCase()}</dt></div>
                            {/if}
                            {#if expanded.lastSeen}
                                <div><dt class="inline">{$_('leaderboard.last_seen', { default: 'Last seen' }).toLowerCase()}</dt> <dd class="inline font-semibold tabular-nums text-white">{formatDate(expanded.lastSeen)}</dd></div>
                            {/if}
                        </dl>
                        <button
                            type="button"
                            class="btn btn-secondary mt-4 min-h-10 px-4 text-xs"
                            onclick={() => onopen(expanded.key)}
                        >
                            {$_('leaderboard.view_species', { values: { species: expanded.displayName }, default: 'View {species}' })}
                        </button>
                    </div>
                </article>
            {/key}
        {/if}

        <div class="flex gap-2 overflow-x-auto pb-1 md:grid md:grid-cols-3 md:gap-2.5 md:overflow-visible md:pb-0" data-showcase-tiles>
            {#each tiles as tile, index (tile.key)}
                {@const picture = pictureFor(tile)}
                <button
                    type="button"
                    class="showcase-tile group relative h-[96px] w-[96px] shrink-0 cursor-pointer overflow-hidden rounded-xl border border-slate-200/70 bg-slate-900 text-left transition-[transform,box-shadow,border-color] duration-200 ease-out hover:-translate-y-1 hover:border-brand-400/70 hover:shadow-xl active:translate-y-0 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 motion-reduce:transform-none md:aspect-square md:h-auto md:w-auto dark:border-slate-700/50"
                    style="--showcase-order: {index}"
                    in:receive={{ key: tile.key }}
                    out:send={{ key: tile.key }}
                    animate:flip={{ duration: reduceMotion ? 0 : MORPH_MS, easing: cubicOut }}
                    aria-pressed="false"
                    aria-label={$_('leaderboard.showcase_bring_forward', { values: { species: tile.displayName }, default: 'Bring {species} forward' })}
                    data-showcase-tile={tile.key}
                    data-photo-source={picture?.source ?? 'none'}
                    onclick={() => (chosenKey = tile.key)}
                >
                    {#if picture}
                        <img
                            src={picture.url}
                            alt=""
                            loading="lazy"
                            decoding="async"
                            class="absolute inset-0 h-full w-full object-cover transition-transform duration-300 ease-out group-hover:scale-[1.05] motion-reduce:transform-none"
                            onerror={() => markFailed(tile.photo && picture.source === 'feeder' ? tile.photo : (tile.reference ?? ''))}
                        />
                    {:else}
                        <span class="absolute inset-0 flex items-center justify-center text-slate-600" aria-hidden="true">
                            <svg class="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg>
                        </span>
                    {/if}
                    {#if picture?.source === 'reference'}
                        <span class="absolute right-1.5 top-1.5 rounded-full border border-white/20 bg-slate-950/65 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white/85" title={referenceLabel(tile)} data-showcase-reference-badge>
                            {$_('leaderboard.showcase_reference_short', { default: 'Reference' })}
                        </span>
                    {/if}
                    <span class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/90 via-slate-950/50 to-transparent px-2 pb-1.5 pt-6">
                        <span class="block truncate text-[12px] font-semibold text-white">{tile.displayName}</span>
                        <span class="block text-[11px] tabular-nums text-white/75">{rankOf(tile)} · {tile.count.toLocaleString()}{#if tile.trend} <span class={(tile.delta ?? 0) > 0 ? 'text-accent-300' : (tile.delta ?? 0) < 0 ? 'text-rose-300' : 'text-white/60'}>{tile.trend}</span>{/if}</span>
                    </span>
                </button>
            {/each}
            {#if moreCount > 0}
                <button
                    type="button"
                    class="showcase-tile flex h-[96px] w-[96px] shrink-0 items-center justify-center rounded-xl border border-dashed border-slate-300 px-2 text-center text-xs text-slate-500 transition-colors hover:border-brand-400 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 md:aspect-square md:h-auto md:w-auto dark:border-slate-600 dark:text-slate-400 dark:hover:text-brand-300"
                    style="--showcase-order: {tiles.length}"
                    onclick={() => onmore?.()}
                    data-showcase-more
                >
                    {$_('leaderboard.showcase_more', { values: { count: moreCount }, default: '{count} more below' })}
                </button>
            {/if}
        </div>
    </section>
{/if}

<style>
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

    /* Tiles rise into place on first paint, in rank order. */
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

    .showcase-tile {
        animation: showcase-rise 0.45s cubic-bezier(0.2, 0.7, 0.2, 1) both;
        animation-delay: calc(0.12s + var(--showcase-order, 0) * 0.05s);
    }

    @media (prefers-reduced-motion: reduce) {
        .showcase-drift,
        .showcase-tile {
            animation: none;
        }
    }

    :global(.reduced-motion) .showcase-drift,
    :global(.reduced-motion) .showcase-tile {
        animation: none;
    }
</style>
