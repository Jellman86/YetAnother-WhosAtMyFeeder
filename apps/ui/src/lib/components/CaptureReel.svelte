<script lang="ts">
    import { getReelImageUrl } from '../api';
    import type { ReelCard } from '../leaderboard/showcase';
    import VisitFilm from './VisitFilm.svelte';

    /**
     * The leaderboard's opener: this install's own photographs, one per leading species, in
     * two rows that drift opposite ways. The leading species' cards play a few silent seconds
     * of the visit once a film is made. Every card is a button.
     *
     * The seamless loop is the row repeated until it is wider than the viewport, then once
     * more, and the drift moves by exactly one copy. The copies are decoration: hidden from
     * readers and out of the Tab order, so a keyboard user meets each card once. A film is
     * downloaded once however many copies show it. Hover or focus pauses the drift. Under
     * reduced motion the copies are dropped, no film plays, and each row becomes a still strip
     * that scrolls sideways, so nothing moves and nothing is lost.
     */
    interface Props {
        cards: ReelCard[];
        label: string;
        onopen: (card: ReelCard) => void;
    }

    let { cards, label, onopen }: Props = $props();

    // Fewer than six photographs make one row; a second would only repeat the first.
    const rows = $derived.by(() => {
        if (cards.length < 6) return [cards];
        return [cards.filter((_card, index) => index % 2 === 0), cards.filter((_card, index) => index % 2 === 1)];
    });

    // One copy's width, measured, so the loop shifts by exactly that and the row is always
    // covered: a short row on a wide screen would otherwise drift into empty space.
    let rowWidth = $state(0);
    let setWidths = $state<number[]>([]);

    // A card drifting under overflow: hidden could receive keyboard focus while off screen. While
    // keyboard focus is inside the reel the rows stand still and scroll like the reduced-motion
    // layout, and the focused card is brought into view. A click focuses the card too, but that
    // focus is not keyboard focus: treating it as such would drop the drift's transform and make
    // the whole row jump under the pointer, so only :focus-visible focus stills the reel.
    let keyboardFocus = $state(false);
    let reelEl = $state<HTMLElement | null>(null);
    function isKeyboardFocus(target: EventTarget | null): boolean {
        if (!(target instanceof Element)) return false;
        try {
            return target.matches(':focus-visible');
        } catch {
            return true;
        }
    }
    function handleFocusIn(event: FocusEvent): void {
        const target = event.target;
        if (!isKeyboardFocus(target)) return;
        keyboardFocus = true;
        if (target instanceof HTMLElement) {
            target.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        }
    }
    function handleFocusOut(event: FocusEvent): void {
        const next = event.relatedTarget;
        if (next instanceof Node && reelEl?.contains(next)) return;
        keyboardFocus = false;
    }
    function copiesFor(rowIndex: number): boolean[] {
        const setWidth = setWidths[rowIndex] ?? 0;
        const needed = setWidth > 0 && rowWidth > 0 ? Math.ceil(rowWidth / setWidth) + 1 : 2;
        return Array.from({ length: Math.max(2, needed) }, (_copy, index) => index > 0);
    }
</script>

{#if cards.length > 0}
    <div
        bind:this={reelEl}
        class="reel relative {keyboardFocus ? 'still' : ''}"
        data-capture-reel
        role="region"
        aria-label={label}
        onfocusin={handleFocusIn}
        onfocusout={handleFocusOut}
    >
        <div class="fade pointer-events-none absolute inset-y-0 left-0 z-10 w-10 bg-gradient-to-r from-surface-light to-transparent dark:from-surface-dark sm:w-24" aria-hidden="true"></div>
        <div class="fade pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-gradient-to-l from-surface-light to-transparent dark:from-surface-dark sm:w-24" aria-hidden="true"></div>
        {#each rows as row, rowIndex (rowIndex)}
            <div class="row" data-capture-reel-row bind:clientWidth={rowWidth}>
                <div
                    class="track {rowIndex % 2 === 1 ? 'reverse' : ''}"
                    style="--reel-duration: {Math.max(28, row.length * 7)}s; --reel-shift: {-(setWidths[rowIndex] ?? 0)}px"
                >
                    {#each copiesFor(rowIndex) as loop, copyIndex (copyIndex)}
                        <div
                            class="set"
                            aria-hidden={loop}
                            data-capture-reel-copy={loop ? 'loop' : 'first'}
                            bind:clientWidth={() => setWidths[rowIndex] ?? 0, (width) => { if (!loop) setWidths[rowIndex] = width; }}
                        >
                            {#each row as card (card.key)}
                                <button
                                    type="button"
                                    class="cap group relative w-[168px] shrink-0 cursor-pointer overflow-hidden rounded-2xl border border-slate-200/80 bg-white/95 text-left shadow-card transition-[transform,box-shadow,border-color] duration-200 ease-out hover:-translate-y-1 hover:border-brand-400/70 hover:shadow-xl active:translate-y-0 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 motion-reduce:transform-none dark:border-slate-700/60 dark:bg-slate-800/85 dark:shadow-card-dark dark:hover:border-brand-400/60 sm:w-[216px]"
                                    tabindex={loop ? -1 : 0}
                                    aria-label={card.label}
                                    data-capture-reel-card={card.key}
                                    onclick={() => onopen(card)}
                                >
                                    <VisitFilm
                                        frigateEvent={card.frigateEvent}
                                        poster={getReelImageUrl(card.frigateEvent)}
                                        film={card.film}
                                        width={216}
                                        height={150}
                                        class="h-[118px] w-full bg-slate-900 transition-transform duration-300 ease-out group-hover:scale-[1.04] motion-reduce:transform-none sm:h-[150px]"
                                    />
                                    <div class="flex items-center justify-between gap-2 px-3 pb-2.5 pt-2">
                                        <div class="min-w-0">
                                            <div class="truncate text-[13px] font-semibold text-slate-900 dark:text-white">{card.title}</div>
                                            <div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{card.detail}</div>
                                        </div>
                                        <span class="shrink-0 rounded-full border border-accent-500/30 bg-accent-500/15 px-2 py-0.5 text-[11px] font-bold tabular-nums text-accent-700 dark:text-accent-300">
                                            {card.badge}
                                        </span>
                                    </div>
                                </button>
                            {/each}
                        </div>
                    {/each}
                </div>
            </div>
        {/each}
    </div>
{/if}

<style>
    .reel {
        display: flex;
        flex-direction: column;
        gap: 12px;
        overflow: hidden;
    }

    .row {
        overflow: hidden;
        padding: 4px 0;
    }

    .track {
        display: flex;
        width: max-content;
        animation: reel-drift var(--reel-duration, 48s) linear infinite;
    }

    .track.reverse {
        animation-direction: reverse;
        animation-duration: calc(var(--reel-duration, 48s) * 1.18);
    }

    /* The loop copy sits flush after the first; the trailing padding is the seam's gap. */
    .set {
        display: flex;
        gap: 12px;
        padding-right: 12px;
    }

    .reel:hover .track,
    .reel:focus-within .track {
        animation-play-state: paused;
    }

    @keyframes reel-drift {
        to {
            transform: translateX(var(--reel-shift, -50%));
        }
    }

    /* No drift: one copy of each row, scrolled by hand. Both the OS preference and the
       app's own accessibility setting say so. */
    @media (prefers-reduced-motion: reduce) {
        .track {
            animation: none;
            width: auto;
        }
        .row {
            overflow-x: auto;
        }
        .set[aria-hidden='true'] {
            display: none;
        }
    }

    :global(.reduced-motion) .track,
    .reel.still .track {
        animation: none;
        width: auto;
    }

    :global(.reduced-motion) .row,
    .reel.still .row {
        overflow-x: auto;
    }

    :global(.reduced-motion) .set[aria-hidden='true'],
    .reel.still .set[aria-hidden='true'] {
        display: none;
    }
</style>
