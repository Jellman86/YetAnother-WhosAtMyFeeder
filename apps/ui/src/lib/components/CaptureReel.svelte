<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { getReelImageUrl, type AboutShowcaseItem } from '../api';
    import { formatDateTime } from '../utils/datetime';

    /**
     * The About page's opener: this install's own photographs, one crop per species, in two
     * rows that drift opposite ways. Every card is a button that opens the visit's record.
     *
     * The seamless loop is the row repeated until it is wider than the viewport, then once
     * more, and the drift moves by exactly one copy. The copies are decoration: hidden from
     * readers and out of the Tab order, so a keyboard user meets each visit once. Hover or
     * focus pauses the drift. Under reduced motion the copies are dropped and each row becomes
     * a still strip that scrolls sideways, so nothing moves and nothing is lost.
     */
    interface Props {
        items: AboutShowcaseItem[];
        /** The visit whose record is being fetched, so its card can say so. */
        openingEvent?: string | null;
        onopen: (item: AboutShowcaseItem) => void;
    }

    let { items, openingEvent = null, onopen }: Props = $props();

    // Fewer than six photographs make one row; a second would only repeat the first.
    const rows = $derived.by(() => {
        if (items.length < 6) return [items];
        return [
            items.filter((_item, index) => index % 2 === 0),
            items.filter((_item, index) => index % 2 === 1)
        ];
    });

    // One copy's width, measured, so the loop shifts by exactly that and the row is always
    // covered: a short row on a wide screen would otherwise drift into empty space.
    let rowWidth = $state(0);
    let setWidths = $state<number[]>([]);

    // A card drifting under overflow: hidden could receive keyboard focus while off screen. While
    // focus is inside the reel the rows stand still and scroll like the reduced-motion layout, and
    // the focused card is brought into view.
    let keyboardFocus = $state(false);
    let reelEl = $state<HTMLElement | null>(null);
    function handleFocusIn(event: FocusEvent): void {
        keyboardFocus = true;
        const target = event.target;
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

    function label(item: AboutShowcaseItem): string {
        return $_('about.opener.open_visit', {
            values: { name: item.display_name, time: formatDateTime(item.detection_time) },
            default: 'Open the {name} visit from {time}'
        });
    }
</script>

{#if items.length > 0}
    <div
        bind:this={reelEl}
        class="reel relative {keyboardFocus ? 'still' : ''}"
        data-about-reel
        role="region"
        aria-label={$_('about.opener.reel_label', { default: 'Recent photographs from this feeder' })}
        onfocusin={handleFocusIn}
        onfocusout={handleFocusOut}
    >
        <div class="fade pointer-events-none absolute inset-y-0 left-0 z-10 w-10 bg-gradient-to-r from-surface-light to-transparent dark:from-surface-dark sm:w-24" aria-hidden="true"></div>
        <div class="fade pointer-events-none absolute inset-y-0 right-0 z-10 w-10 bg-gradient-to-l from-surface-light to-transparent dark:from-surface-dark sm:w-24" aria-hidden="true"></div>
        {#each rows as row, rowIndex (rowIndex)}
            <div class="row" data-about-reel-row bind:clientWidth={rowWidth}>
                <div
                    class="track {rowIndex % 2 === 1 ? 'reverse' : ''}"
                    style="--reel-duration: {Math.max(28, row.length * 7)}s; --reel-shift: {-(setWidths[rowIndex] ?? 0)}px"
                >
                    {#each copiesFor(rowIndex) as loop, copyIndex (copyIndex)}
                        <div
                            class="set"
                            aria-hidden={loop}
                            data-about-reel-copy={loop ? 'loop' : 'first'}
                            bind:clientWidth={() => setWidths[rowIndex] ?? 0, (width) => { if (!loop) setWidths[rowIndex] = width; }}
                        >
                            {#each row as item (item.frigate_event)}
                                {@const opening = openingEvent === item.frigate_event}
                                <button
                                    type="button"
                                    class="cap group relative w-[168px] shrink-0 overflow-hidden rounded-2xl border border-slate-200/80 bg-white/95 text-left shadow-card transition-colors hover:border-brand-300/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:border-slate-700/60 dark:bg-slate-800/85 dark:shadow-card-dark sm:w-[216px]"
                                    tabindex={loop ? -1 : 0}
                                    aria-label={label(item)}
                                    aria-busy={opening}
                                    data-about-reel-card={item.frigate_event}
                                    onclick={() => onopen(item)}
                                >
                                    <img
                                        src={getReelImageUrl(item.frigate_event)}
                                        alt=""
                                        loading="lazy"
                                        decoding="async"
                                        width="216"
                                        height="150"
                                        class="h-[118px] w-full bg-slate-900 object-cover sm:h-[150px]"
                                    />
                                    <div class="flex items-center justify-between gap-2 px-3 pb-2.5 pt-2">
                                        <div class="min-w-0">
                                            <div class="truncate text-[13px] font-semibold text-slate-900 dark:text-white">{item.display_name}</div>
                                            <div class="truncate text-[11px] text-slate-500 dark:text-slate-400">{formatDateTime(item.detection_time)}</div>
                                        </div>
                                        <span class="shrink-0 rounded-full border border-accent-500/30 bg-accent-500/15 px-2 py-0.5 text-[11px] font-bold tabular-nums text-accent-700 dark:text-accent-300">
                                            {Math.round(item.score * 100)}%
                                        </span>
                                    </div>
                                    {#if opening}
                                        <span class="absolute inset-0 flex items-center justify-center bg-slate-950/45" aria-hidden="true">
                                            <span class="inline-block h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
                                        </span>
                                    {/if}
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
