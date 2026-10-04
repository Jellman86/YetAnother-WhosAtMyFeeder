<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { getReelImageUrl } from '../api';
    import { shareSegments, spotlightGroups, type ShowcaseRow } from '../leaderboard/showcase';
    import { packTiles, readableInk, WALL_MINIMUM, type WallTile } from '../leaderboard/wall';
    import { formatDateTime } from '../utils/datetime';
    import VisitFilm from './VisitFilm.svelte';

    /**
     * The leaderboard's opener: a contact sheet of this feeder's own visits in the window, one
     * photograph per visit, newest first, packed densely like a photo library, with the leading
     * species' best visits drawn large. A share bar on top is its navigation: each segment is a
     * species sized by its share; hovering or focusing one opens it out to say its share and count
     * and lights that species' visits on the wall while the rest step back, and a click pins that
     * highlight (the only way to see it on touch).
     *
     * Hovering or focusing a visit rings it, draws its photograph in a little closer, and opens a
     * pop-out beside it: the larger photograph, names, the classifier's confidence, when and where it
     * was seen, and a few silent seconds of the visit where a film is made. Nothing resizes or moves
     * under the pointer, and the pop-out glides between visits instead of blinking. On touch a tap
     * opens the species. Every visit is a button, with a single Tab stop and arrow-key movement.
     * A photograph that fails to load leaves the wall rather than leaving a hole in it.
     */
    interface Props {
        tiles: WallTile[];
        /** Every ranked species: the header names the first unflagged one, the share bar sums them all. */
        rows: ShowcaseRow[];
        /** What the leader is, e.g. "Most visits, last 30 days". */
        eyebrow: string;
        label: string;
        countLabel: (count: number) => string;
        /** The species' colour in the charts, so a highlight matches the rest of the page. */
        colourFor: (key: string | null) => string;
        otherColour: string;
        loading: boolean;
        /** Visits to draw at most; a guest's photographs share a request budget, so the page caps them. */
        maxTiles?: number;
        onopen: (key: string) => void;
        /** The share bar's "needs a check" segment points at the list of flagged species. */
        onchecks: () => void;
    }

    let { tiles, rows, eyebrow, label, countLabel, colourFor, otherColour, loading, maxTiles, onopen, onchecks }: Props = $props();

    const id = $props.id();
    const popoutId = `wall-popout-${id}`;
    const hintId = `wall-hint-${id}`;

    const groups = $derived(spotlightGroups(rows));
    const segments = $derived(shareSegments(rows));
    const segmentKeys = $derived(new Set(segments.map((segment) => segment.key)));
    const total = $derived(rows.reduce((sum, row) => sum + row.count, 0));
    const leader = $derived(groups.list[0] ?? null);
    const rowByKey = (key: string): ShowcaseRow | undefined => rows.find((row) => row.key === key);

    let reduceMotion = $state(false);
    $effect(() => {
        if (typeof window === 'undefined') return;
        const query = window.matchMedia('(prefers-reduced-motion: reduce)');
        const preferences = new MutationObserver(sync);
        function sync(): void {
            reduceMotion = query.matches || document.documentElement.classList.contains('reduced-motion');
        }
        sync();
        query.addEventListener('change', sync);
        preferences.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => {
            query.removeEventListener('change', sync);
            preferences.disconnect();
        };
    });

    // The grid is exact: a whole number of equal columns across the container's content box, square
    // cells of whatever size that leaves, and a fixed number of rows (more once the wall is opened
    // out). Columns come from the width alone, so the wall's cells are the same size whether it holds
    // a dozen visits or a hundred. `packTiles` lays tiles out the way the grid will, so a full wall
    // ends in a full row.
    const GAP = 3;
    const FRAME = 3;
    const OPENED_ROWS = 24;
    let width = $state(0);
    let opened = $state(false);
    const target = $derived(width < 520 ? 56 : width < 900 ? 68 : 78);
    const columns = $derived(Math.max(4, Math.round((width - FRAME * 2 + GAP) / (target + GAP))));
    const cell = $derived(Math.max(24, (width - FRAME * 2 - GAP * (columns - 1)) / columns));
    const rowCount = $derived(opened ? OPENED_ROWS : width < 520 ? 8 : 6);

    let failed = $state<Set<string>>(new Set());
    function markFailed(event: string): void {
        failed = new Set([...failed, event]);
    }
    const usable = $derived(tiles.slice(0, maxTiles ?? tiles.length).filter((tile) => !failed.has(tile.frigateEvent)));
    const shown = $derived(width === 0 ? [] : packTiles(usable, columns, rowCount));
    const hasMore = $derived(!opened && usable.length > shown.length);
    const large = (tile: WallTile): boolean => tile.featured && columns >= 4;
    const skeleton = $derived(Array.from({ length: columns * 3 }, (_unused, index) => index));

    // The tiles rise into place once, on first paint; a wall that reflows later does not replay it.
    let introDone = $state(false);
    $effect(() => {
        if (introDone || shown.length === 0) return;
        const timer = setTimeout(() => (introDone = true), 1300);
        return () => clearTimeout(timer);
    });
    const rising = $derived(!introDone && !reduceMotion);

    // Which species the share bar lights: the segment under the pointer or focus, else the pinned
    // one. A key that is no longer in the bar (another window, another source) lights nothing, and a
    // species with no visit on the wall dims nothing: a highlight must always point at something.
    let hoverSegment = $state<string | null>(null);
    let pinnedSegment = $state<string | null>(null);
    const activeSegment = $derived.by((): string | null => {
        if (hoverSegment !== null && segmentKeys.has(hoverSegment)) return hoverSegment;
        if (pinnedSegment !== null && segmentKeys.has(pinnedSegment)) return pinnedSegment;
        return null;
    });
    const pinned = $derived(pinnedSegment !== null && segmentKeys.has(pinnedSegment) ? pinnedSegment : null);
    const othersKeys = $derived(new Set(groups.others.members));
    const lit = $derived.by((): ReadonlySet<string> | null => {
        if (activeSegment === null || activeSegment === 'checks') return null;
        const keys = activeSegment === 'others' ? othersKeys : new Set([activeSegment]);
        return shown.some((tile) => tile.speciesKey !== null && keys.has(tile.speciesKey)) ? keys : null;
    });
    const isLit = (tile: WallTile): boolean => lit !== null && tile.speciesKey !== null && lit.has(tile.speciesKey);

    // A visit is opened after a short intent delay so a sweep across the wall does not strobe; once a
    // pop-out is open, moving to a neighbour is immediate so it follows the pointer instead of blinking.
    const INTENT_MS = 220;
    const GRACE_MS = 200;
    const POPOUT_WIDTH = 296;
    const POPOUT_GAP = 12;
    let activeTile = $state<string | null>(null);
    let activeElement: HTMLElement | null = null;
    let intentTimer: ReturnType<typeof setTimeout> | undefined;
    let closeTimer: ReturnType<typeof setTimeout> | undefined;
    let popoutHeight = $state(0);

    interface Anchor {
        left: number;
        top: number;
        right: number;
        bottom: number;
        viewportWidth: number;
        viewportHeight: number;
    }
    let anchor = $state<Anchor | null>(null);

    const open = $derived(activeTile ? (shown.find((tile) => tile.key === activeTile) ?? null) : null);

    // The pop-out sits against the viewport, on the side of the tile that points into the wall (a tile
    // in the left half opens rightwards and the reverse), centred on the tile and kept on screen; a
    // narrow screen puts it under (or over) the tile. Derived from the tile's rectangle and the pop-out's
    // measured height, so nothing has to be kept in step by hand.
    const place = $derived.by((): { left: number; top: number; side: 'right' | 'left' | 'below' } | null => {
        if (anchor === null) return null;
        const height = popoutHeight || 400;
        const { left, top, right, bottom, viewportWidth, viewportHeight } = anchor;
        const centre = (left + right) / 2;
        const roomRight = viewportWidth - right - POPOUT_GAP - 8;
        const roomLeft = left - POPOUT_GAP - 8;
        const preferRight = centre < viewportWidth / 2;
        const clampTop = Math.min(Math.max(8, (top + bottom) / 2 - height / 2), Math.max(8, viewportHeight - height - 8));
        if (preferRight ? roomRight >= POPOUT_WIDTH : roomLeft < POPOUT_WIDTH && roomRight >= POPOUT_WIDTH) {
            return { left: right + POPOUT_GAP, top: clampTop, side: 'right' };
        }
        if (roomLeft >= POPOUT_WIDTH) return { left: left - POPOUT_GAP - POPOUT_WIDTH, top: clampTop, side: 'left' };
        const fitsBelow = bottom + POPOUT_GAP + height <= viewportHeight - 8;
        return {
            left: Math.min(Math.max(8, centre - POPOUT_WIDTH / 2), Math.max(8, viewportWidth - POPOUT_WIDTH - 8)),
            top: fitsBelow ? bottom + POPOUT_GAP : Math.max(8, top - POPOUT_GAP - height),
            side: 'below'
        };
    });

    function anchorOf(element: HTMLElement): Anchor {
        const box = element.getBoundingClientRect();
        return { left: box.left, top: box.top, right: box.right, bottom: box.bottom, viewportWidth: window.innerWidth, viewportHeight: window.innerHeight };
    }
    function openTile(tile: WallTile, trigger: HTMLElement): void {
        clearTimeout(intentTimer);
        clearTimeout(closeTimer);
        hoverSegment = null;
        activeElement = trigger;
        anchor = anchorOf(trigger);
        activeTile = tile.key;
    }
    function scheduleClose(): void {
        clearTimeout(intentTimer);
        clearTimeout(closeTimer);
        closeTimer = setTimeout(closeAll, GRACE_MS);
    }
    function holdOpen(): void {
        clearTimeout(closeTimer);
    }
    function closeAll(): void {
        clearTimeout(intentTimer);
        clearTimeout(closeTimer);
        activeTile = null;
        activeElement = null;
        anchor = null;
    }
    $effect(() => () => {
        clearTimeout(intentTimer);
        clearTimeout(closeTimer);
    });

    // A mouse or pen hovers; touch has no hover, so it falls through to the tap that opens the species.
    function hoverTile(event: PointerEvent, tile: WallTile): void {
        if (event.pointerType === 'touch') return;
        const trigger = event.currentTarget as HTMLElement;
        clearTimeout(closeTimer);
        if (activeTile !== null) {
            openTile(tile, trigger);
            return;
        }
        clearTimeout(intentTimer);
        intentTimer = setTimeout(() => openTile(tile, trigger), INTENT_MS);
    }
    function focusTile(event: FocusEvent, tile: WallTile): void {
        focusKey = tile.key;
        const target = event.currentTarget as HTMLElement;
        try {
            if (!target.matches(':focus-visible')) return;
        } catch {
            // No :focus-visible: treat focus as keyboard focus.
        }
        openTile(tile, target);
    }
    function pickTile(tile: WallTile): void {
        closeAll();
        if (tile.speciesKey) onopen(tile.speciesKey);
    }

    // One Tab stop for the whole wall, then the arrow keys move between visits by where they are on
    // screen; Tabbing through a hundred photographs would make everything after the wall unreachable.
    let focusKey = $state<string | null>(null);
    let gridElement = $state<HTMLElement | null>(null);
    const tabStop = $derived(shown.some((tile) => tile.key === focusKey) ? focusKey : (shown[0]?.key ?? null));
    function moveFocus(event: KeyboardEvent): void {
        if (!gridElement) return;
        const key = event.key;
        const buttons = [...gridElement.querySelectorAll<HTMLElement>('[data-capture-wall-tile]')];
        const current = event.currentTarget as HTMLElement;
        let next: HTMLElement | undefined;
        if (key === 'Home') next = buttons[0];
        else if (key === 'End') next = buttons[buttons.length - 1];
        else if (key.startsWith('Arrow')) {
            const from = current.getBoundingClientRect();
            const cx = from.left + from.width / 2;
            const cy = from.top + from.height / 2;
            let best = Infinity;
            for (const candidate of buttons) {
                if (candidate === current) continue;
                const box = candidate.getBoundingClientRect();
                const dx = box.left + box.width / 2 - cx;
                const dy = box.top + box.height / 2 - cy;
                const along = key === 'ArrowRight' ? dx : key === 'ArrowLeft' ? -dx : key === 'ArrowDown' ? dy : -dy;
                const across = key === 'ArrowRight' || key === 'ArrowLeft' ? Math.abs(dy) : Math.abs(dx);
                if (along <= 2) continue;
                const cost = along + across * 3;
                if (cost < best) {
                    best = cost;
                    next = candidate;
                }
            }
        } else return;
        event.preventDefault();
        next?.focus();
    }

    // Escape lets go of whatever is open or pinned, wherever the pointer or focus is, and nothing else
    // answers it. The pop-out follows its tile while the page scrolls and goes when the tile is off screen.
    $effect(() => {
        if (activeTile === null && pinned === null) return;
        const onKey = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return;
            event.stopPropagation();
            if (activeTile !== null) closeAll();
            else pinnedSegment = null;
        };
        let frame = 0;
        const follow = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
                if (activeElement === null) return;
                const box = activeElement.getBoundingClientRect();
                if (!activeElement.isConnected || box.bottom < 0 || box.top > window.innerHeight) closeAll();
                else anchor = anchorOf(activeElement);
            });
        };
        const dismiss = () => closeAll();
        window.addEventListener('keydown', onKey, true);
        window.addEventListener('scroll', follow, { passive: true });
        window.addEventListener('resize', dismiss);
        return () => {
            cancelAnimationFrame(frame);
            window.removeEventListener('keydown', onKey, true);
            window.removeEventListener('scroll', follow);
            window.removeEventListener('resize', dismiss);
        };
    });

    function portal(node: HTMLElement) {
        document.body.appendChild(node);
        return { destroy: () => node.remove() };
    }

    // A photograph fades in as it arrives, over the species-tinted tile, instead of popping.
    function photo(node: HTMLImageElement, fail: () => void) {
        const ready = () => node.classList.add('ready');
        if (node.complete && node.naturalWidth > 0) ready();
        node.addEventListener('load', ready);
        node.addEventListener('error', fail);
        return {
            destroy() {
                node.removeEventListener('load', ready);
                node.removeEventListener('error', fail);
            }
        };
    }

    // The share bar. Opening a segment closes any visit's pop-out first, so the two never fight over
    // what is lit. A click pins the highlight and a second click lets go.
    function segmentEnter(key: string): void {
        closeAll();
        hoverSegment = key;
    }
    function segmentLeave(key: string): void {
        if (hoverSegment === key) hoverSegment = null;
    }
    function pickSegment(key: string, kind: 'species' | 'others' | 'checks'): void {
        if (kind === 'checks') {
            onchecks();
            return;
        }
        pinnedSegment = pinned === key ? null : key;
    }
    const pinnedRow = $derived(pinned !== null && pinned !== 'others' ? (rowByKey(pinned) ?? null) : null);
    function percentOfTotal(count: number): string {
        if (total <= 0) return '0%';
        const percent = (count / total) * 100;
        return percent > 0 && percent < 1 ? '<1%' : `${Math.round(percent)}%`;
    }
    type Kind = 'species' | 'others' | 'checks';
    function segmentName(key: string, kind: Kind): string {
        if (kind === 'others') return $_('leaderboard.wall_others', { values: { count: groups.others.species }, default: '{count} other species' });
        if (kind === 'checks') return $_('leaderboard.spotlight_needs_check', { default: 'Needs a check' });
        return rowByKey(key)?.displayName ?? key;
    }
    function segmentLabel(segment: { key: string; kind: Kind; count: number }): string {
        return `${segmentName(segment.key, segment.kind)}, ${segment.count.toLocaleString()} ${countLabel(segment.count)}, ${percentOfTotal(segment.count)}`;
    }
    const CHECK_COLOUR = '#f59e0b';
    function segmentColour(segment: { key: string; kind: Kind }): string {
        if (segment.kind === 'species') return colourFor(segment.key);
        if (segment.kind === 'others') return otherColour;
        return CHECK_COLOUR;
    }
    // A segment opens out to this share when hovered, focused or pinned, so a thin one can be read.
    const OPEN_SHARE = 30;
    function segmentGrow(segment: { key: string; percent: number }): number {
        return activeSegment === segment.key ? Math.max(segment.percent, OPEN_SHARE) : Math.max(segment.percent, 0.4);
    }

    function tileName(tile: WallTile): string {
        return $_('leaderboard.wall_tile', {
            values: { name: tile.name, time: formatDateTime(tile.at) },
            default: '{name}, seen {time}'
        });
    }
    function percent(score: number): string {
        return `${Math.round(score * 100)}%`;
    }
</script>

<section class="wall-section space-y-3" aria-label={label} data-capture-wall>
    {#if leader}
        <header class="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
            <div class="min-w-0">
                <p class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{eyebrow}</p>
                <div class="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    <h2 class="font-display text-3xl font-bold leading-tight text-slate-900 dark:text-white sm:text-4xl">{leader.displayName}</h2>
                    <p class="text-sm tabular-nums text-slate-600 dark:text-slate-300">
                        <span class="font-semibold text-slate-900 dark:text-white">{leader.count.toLocaleString()}</span>
                        {countLabel(leader.count)}
                    </p>
                </div>
                {#if leader.subName}
                    <p class="text-sm italic text-slate-500 dark:text-slate-400">{leader.subName}</p>
                {/if}
            </div>
            {#if pinnedRow}
                <button type="button" class="btn btn-secondary text-xs" onclick={() => onopen(pinnedRow.key)} data-capture-wall-open>
                    {$_('leaderboard.wall_open', { values: { name: pinnedRow.displayName }, default: 'Open {name}' })}
                </button>
            {/if}
        </header>
    {/if}

    {#if segments.length > 0}
        <ul
            class="share flex h-12 gap-1 overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-900"
            aria-label={$_('leaderboard.spotlight_share_heading', { default: 'Share by species' })}
            data-capture-wall-share
        >
            {#each segments as segment (segment.key)}
                {@const colour = segmentColour(segment)}
                {@const out = activeSegment === segment.key}
                <li class="segment" style:flex-grow={segmentGrow(segment)}>
                    <button
                        type="button"
                        class="segment-button {pinned === segment.key ? 'pinned' : ''}"
                        style:background-color={colour}
                        style:color={readableInk(colour)}
                        aria-label={segmentLabel(segment)}
                        aria-pressed={segment.kind === 'checks' ? undefined : pinned === segment.key}
                        data-capture-wall-segment={segment.kind}
                        onpointerenter={(event) => event.pointerType !== 'touch' && segmentEnter(segment.key)}
                        onpointerleave={() => segmentLeave(segment.key)}
                        onfocus={(event) => (event.currentTarget.matches(':focus-visible') ? segmentEnter(segment.key) : undefined)}
                        onblur={() => segmentLeave(segment.key)}
                        onclick={() => pickSegment(segment.key, segment.kind)}
                    >
                        {#if segment.percent >= 14 || out}
                            <span class="segment-name">{segmentName(segment.key, segment.kind)}</span>
                            <span class="segment-meta">
                                {#if out}{percentOfTotal(segment.count)} · {segment.count.toLocaleString()} {countLabel(segment.count)}{:else}{percentOfTotal(segment.count)}{/if}
                            </span>
                        {/if}
                    </button>
                </li>
            {/each}
        </ul>
    {/if}

    {#if loading || usable.length >= WALL_MINIMUM}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
            class="wall relative overflow-hidden rounded-2xl border border-slate-200/80 bg-slate-100/70 p-[3px] dark:border-slate-700/60 dark:bg-slate-950/60 {lit !== null ? 'has-active' : ''}"
            bind:clientWidth={width}
            onpointerleave={scheduleClose}
            data-capture-wall-grid
        >
            {#if shown.length === 0}
                <div class="wall-grid" style:--cols={columns} style:--cell="{cell}px" style:--gap="{GAP}px" aria-hidden="true">
                    {#each skeleton as slot (slot)}
                        <span class="tile skeleton" style:animation-delay="{(slot % 9) * 70}ms"></span>
                    {/each}
                </div>
                <p class="sr-only" role="status">{$_('leaderboard.wall_loading', { default: 'Loading photographs' })}</p>
            {:else}
                <p id={hintId} class="sr-only">{$_('leaderboard.wall_keys', { default: 'Use the arrow keys to move between visits.' })}</p>
                <div
                    class="wall-grid"
                    role="group"
                    aria-label={label}
                    aria-describedby={hintId}
                    bind:this={gridElement}
                    style:--cols={columns}
                    style:--cell="{cell}px"
                    style:--gap="{GAP}px"
                >
                    {#each shown as tile, index (tile.key)}
                        <button
                            type="button"
                            class="tile {large(tile) ? 'featured' : ''} {rising ? 'rising' : ''} {isLit(tile) ? 'lit' : ''} {activeTile === tile.key ? 'hovered' : ''}"
                            style:--tint={tile.speciesKey ? colourFor(tile.speciesKey) : undefined}
                            style:animation-delay={rising ? `${Math.min(index * 9, 520)}ms` : undefined}
                            tabindex={tabStop === tile.key ? 0 : -1}
                            aria-label={tileName(tile)}
                            aria-describedby={activeTile === tile.key ? popoutId : undefined}
                            aria-disabled={tile.speciesKey === null}
                            data-capture-wall-tile={tile.key}
                            data-species={tile.speciesKey ?? ''}
                            onpointerenter={(event) => hoverTile(event, tile)}
                            onpointerleave={scheduleClose}
                            onfocus={(event) => focusTile(event, tile)}
                            onblur={scheduleClose}
                            onkeydown={moveFocus}
                            onclick={() => pickTile(tile)}
                        >
                            <img
                                src={getReelImageUrl(tile.frigateEvent)}
                                alt=""
                                loading="lazy"
                                decoding="async"
                                draggable="false"
                                class="tile-photo"
                                use:photo={() => markFailed(tile.frigateEvent)}
                            />
                            {#if tile.hasClip}
                                <span class="clip-badge" aria-hidden="true">
                                    <svg viewBox="0 0 16 16" class="h-2.5 w-2.5" fill="currentColor"><path d="M4 2.5v11l9-5.5z" /></svg>
                                </span>
                            {/if}
                        </button>
                    {/each}
                </div>
            {/if}
        </div>

        {#if shown.length > 0}
            <div class="flex flex-wrap items-center justify-between gap-2">
                <p class="text-xs text-slate-500 dark:text-slate-400">
                    {$_('leaderboard.wall_footer', { values: { count: shown.length }, default: '{count} recent visits. Each opens its species.' })}
                </p>
                {#if hasMore || opened}
                    <button type="button" class="btn btn-ghost text-xs" aria-expanded={opened} onclick={() => (opened = !opened)} data-capture-wall-more>
                        {opened ? $_('leaderboard.wall_less', { default: 'Show fewer visits' }) : $_('leaderboard.wall_more', { default: 'Show more visits' })}
                    </button>
                {/if}
            </div>
        {/if}
    {/if}
</section>

{#if open && place}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div
        id={popoutId}
        use:portal
        role="tooltip"
        class="wall-popout fixed z-[70] rounded-2xl border border-slate-200 bg-white p-2.5 shadow-2xl dark:border-slate-700 dark:bg-slate-900 {place.side}"
        style:left="{place.left}px"
        style:top="{place.top}px"
        style:width="{POPOUT_WIDTH}px"
        bind:clientHeight={popoutHeight}
        onpointerenter={holdOpen}
        onpointerleave={scheduleClose}
        data-capture-wall-popout
    >
        {#key open.key}
            <div class="popout-content">
                <div
                    class="relative overflow-hidden rounded-xl"
                    style:aspect-ratio="4 / 3"
                    style:background-color="color-mix(in srgb, {open.speciesKey ? colourFor(open.speciesKey) : '#64748b'} 30%, #0f172a)"
                >
                    <VisitFilm frigateEvent={open.frigateEvent} poster={getReelImageUrl(open.frigateEvent)} film={open.film} class="h-full w-full" />
                    {#if open.rank !== null}
                        <span class="absolute left-2 top-2 rounded-full bg-slate-950/70 px-2 py-0.5 text-[11px] font-bold tabular-nums text-white backdrop-blur-sm">
                            {$_('leaderboard.wall_rank', { values: { rank: open.rank }, default: 'Rank {rank}' })}
                        </span>
                    {/if}
                    {#if open.film || open.hasClip}
                        <span class="absolute bottom-2 right-2 inline-flex items-center gap-1 rounded-full bg-slate-950/70 px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur-sm">
                            <svg viewBox="0 0 16 16" class="h-2.5 w-2.5" fill="currentColor" aria-hidden="true"><path d="M4 2.5v11l9-5.5z" /></svg>
                            {$_('leaderboard.wall_clip', { default: 'Clip' })}
                        </span>
                    {/if}
                </div>
                <div class="px-1 pb-1 pt-2.5">
                    <p class="flex items-center gap-2 font-display text-lg font-bold leading-tight text-slate-900 dark:text-white">
                        <span class="h-2.5 w-2.5 shrink-0 rounded-full" style:background-color={colourFor(open.speciesKey)} aria-hidden="true"></span>
                        <span class="min-w-0 truncate">{open.name}</span>
                    </p>
                    {#if open.subName}
                        <p class="truncate text-sm italic text-slate-500 dark:text-slate-400">{open.subName}</p>
                    {/if}
                    <dl class="mt-2.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                        <dt class="text-slate-500 dark:text-slate-400">{$_('leaderboard.wall_confidence', { default: 'Confidence' })}</dt>
                        <dd class="flex items-center gap-2 font-semibold tabular-nums text-slate-900 dark:text-white">
                            {percent(open.score)}
                            <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700" aria-hidden="true">
                                <span class="block h-full rounded-full bg-accent-500" style:width={percent(open.score)}></span>
                            </span>
                        </dd>
                        <dt class="text-slate-500 dark:text-slate-400">{$_('leaderboard.wall_seen', { default: 'Seen' })}</dt>
                        <dd class="text-slate-800 dark:text-slate-100">{formatDateTime(open.at)}</dd>
                        {#if open.camera}
                            <dt class="text-slate-500 dark:text-slate-400">{$_('leaderboard.wall_camera', { default: 'Camera' })}</dt>
                            <dd class="truncate text-slate-800 dark:text-slate-100">{open.camera}</dd>
                        {/if}
                        <dt class="text-slate-500 dark:text-slate-400">{$_('leaderboard.wall_visit', { default: 'Visit' })}</dt>
                        <dd class="text-slate-800 dark:text-slate-100">
                            {$_('leaderboard.wall_frames', { values: { count: open.captures }, default: '{count, plural, one {# frame} other {# frames}}' })}
                        </dd>
                    </dl>
                    {#if open.speciesKey}
                        <p class="mt-2.5 border-t border-slate-200 pt-2 text-[11px] font-semibold text-brand-700 dark:border-slate-700 dark:text-brand-300">
                            {$_('leaderboard.wall_open', { values: { name: open.name }, default: 'Open {name}' })}
                        </p>
                    {/if}
                </div>
            </div>
        {/key}
    </div>
{/if}

<style>
    /* The share bar: every segment's width is its share, an opened one widens to read, and the others
       give way. Widths are flex weights, which animate. Thin segments keep a target a finger can hit. */
    .segment {
        flex-basis: 0;
        flex-shrink: 1;
        min-width: 24px;
        transition: flex-grow 0.38s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .segment-button {
        display: flex;
        height: 100%;
        width: 100%;
        flex-direction: column;
        justify-content: center;
        overflow: hidden;
        padding: 0 10px;
        text-align: left;
        white-space: nowrap;
        cursor: pointer;
        transition: filter 0.2s ease-out;
    }

    .segment-button:hover {
        filter: brightness(1.06);
    }

    /* Two tones so the ring shows on every species colour, light or dark. */
    .segment-button:focus-visible {
        outline: 2px solid #020617;
        outline-offset: -4px;
        box-shadow: inset 0 0 0 2px #fff;
    }

    .segment-button.pinned {
        box-shadow: inset 0 -4px 0 currentColor;
    }

    .segment-name {
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 0.8125rem;
        font-weight: 700;
        line-height: 1.15;
    }

    .segment-meta {
        overflow: hidden;
        text-overflow: ellipsis;
        font-size: 0.75rem;
        font-weight: 600;
        line-height: 1.15;
        font-variant-numeric: tabular-nums;
    }

    .wall-grid {
        display: grid;
        grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
        grid-auto-rows: var(--cell);
        grid-auto-flow: dense;
        gap: var(--gap);
    }

    .tile {
        position: relative;
        display: block;
        overflow: hidden;
        border-radius: 5px;
        padding: 0;
        cursor: pointer;
        background-color: color-mix(in srgb, var(--tint, #64748b) 30%, #0f172a);
        transition: opacity 0.28s ease-out;
    }

    .tile[aria-disabled='true'] {
        cursor: default;
    }

    .tile.featured {
        grid-column: span 2;
        grid-row: span 2;
        border-radius: 9px;
    }

    .tile-photo {
        display: block;
        width: 100%;
        height: 100%;
        object-fit: cover;
        opacity: 0;
        transform: scale(1);
        transition:
            opacity 0.4s ease-out,
            transform 0.6s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .tile-photo:global(.ready) {
        opacity: 1;
    }

    .clip-badge {
        position: absolute;
        right: 4px;
        bottom: 4px;
        display: flex;
        height: 18px;
        width: 18px;
        align-items: center;
        justify-content: center;
        border-radius: 9999px;
        background: rgb(2 6 23 / 0.62);
        color: white;
    }

    /* The hovered visit never changes size, so nothing under or around it moves: a two-tone ring drawn
       over the photograph, and the photograph itself drawn in a little closer. */
    .tile::after {
        content: '';
        position: absolute;
        inset: 0;
        border-radius: inherit;
        pointer-events: none;
        box-shadow:
            inset 0 0 0 0 transparent,
            inset 0 0 0 0 transparent;
        transition: box-shadow 0.2s ease-out;
    }

    .tile.hovered::after,
    .tile:focus-visible::after {
        box-shadow:
            inset 0 0 0 2px #fff,
            inset 0 0 0 4px #020617;
    }

    .tile.hovered .tile-photo {
        transform: scale(1.08);
    }

    .tile:focus-visible {
        outline: none;
    }

    /* While the share bar lights a species the others step back. They stay legible: emphasis, not a veil. */
    .wall.has-active .tile:not(.lit) {
        opacity: 0.5;
    }

    .tile.rising {
        animation: wall-rise 0.45s cubic-bezier(0.22, 1, 0.36, 1) backwards;
    }

    .skeleton {
        cursor: default;
        animation: wall-pulse 1.4s ease-in-out infinite;
    }

    .wall-popout {
        transition:
            left 0.2s cubic-bezier(0.22, 1, 0.36, 1),
            top 0.2s cubic-bezier(0.22, 1, 0.36, 1);
        animation: popout-in 0.18s cubic-bezier(0.22, 1, 0.36, 1);
    }

    .wall-popout.left {
        transform-origin: right center;
    }

    .wall-popout.right {
        transform-origin: left center;
    }

    .wall-popout.below {
        transform-origin: center top;
    }

    .popout-content {
        animation: content-in 0.16s ease-out;
    }

    @keyframes wall-rise {
        from {
            opacity: 0;
            transform: translateY(8px);
        }
        to {
            opacity: 1;
            transform: none;
        }
    }

    @keyframes wall-pulse {
        0%,
        100% {
            opacity: 0.45;
        }
        50% {
            opacity: 0.8;
        }
    }

    @keyframes popout-in {
        from {
            opacity: 0;
            transform: scale(0.96);
        }
        to {
            opacity: 1;
            transform: none;
        }
    }

    @keyframes content-in {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        .segment,
        .segment-button,
        .tile,
        .tile-photo,
        .tile::after,
        .wall-popout {
            transition: none;
        }
        .tile.hovered .tile-photo {
            transform: none;
        }
        .tile.rising,
        .skeleton,
        .wall-popout,
        .popout-content {
            animation: none;
        }
    }

    :global(.reduced-motion) .segment,
    :global(.reduced-motion) .segment-button,
    :global(.reduced-motion) .tile,
    :global(.reduced-motion) .tile-photo,
    :global(.reduced-motion) .tile::after,
    :global(.reduced-motion) .wall-popout {
        transition: none;
    }

    :global(.reduced-motion) .tile.hovered .tile-photo {
        transform: none;
    }

    :global(.reduced-motion) .tile.rising,
    :global(.reduced-motion) .skeleton,
    :global(.reduced-motion) .wall-popout,
    :global(.reduced-motion) .popout-content {
        animation: none;
    }
</style>
