<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import { shareSegments, spotlightGroups, type ShowcaseRow } from '../leaderboard/showcase';

    /**
     * Who made up the leaderboard's window, as one bar in the charts' species colours, so a
     * species that dominates reads as a proportion. The reel above it shows the photographs.
     *
     * Each segment opens a pop-out on hover and keyboard focus (never on touch, where a tap opens
     * the species): the common and scientific name over the species' stock photograph, labelled
     * with where it came from, and its count and share. Species that are probably
     * misidentifications are counted in the bar and named beneath it, to be checked.
     */
    interface Props {
        rows: ShowcaseRow[];
        /** What the bar counts, e.g. "Most visits this month". */
        label: string;
        countLabel: (count: number) => string;
        /** The species' colour in the timeline and composition charts. */
        colourFor: (key: string) => string;
        otherColour: string;
        nearbyRadiusKm?: number | null;
        onopen: (key: string) => void;
        onmore?: () => void;
    }

    let { rows, label, countLabel, colourFor, otherColour, nearbyRadiusKm = null, onopen, onmore }: Props = $props();

    const groups = $derived(spotlightGroups(rows));
    const segments = $derived(shareSegments(rows));
    const total = $derived(rows.reduce((sum, row) => sum + row.count, 0));

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

    // The pop-out stays open while the pointer travels into it and closes on Escape.
    const POPOUT_WIDTH = 256;
    const POPOUT_GRACE_MS = 120;
    const popoutId = `share-popout-${Math.random().toString(36).slice(2, 9)}`;
    let barElement = $state<HTMLElement | null>(null);
    let checksElement = $state<HTMLElement | null>(null);
    let openKey = $state<string | null>(null);
    let popoutLeft = $state(0);
    let closeTimer: ReturnType<typeof setTimeout> | undefined;
    const popout = $derived.by(() => {
        if (openKey === null) return null;
        if (openKey === 'others') {
            const listed = new Set(groups.list.map((row) => row.key));
            return { kind: 'others' as const, row: null, members: rows.filter((row) => !row.flagged && !listed.has(row.key)) };
        }
        if (openKey === 'checks') return { kind: 'checks' as const, row: null, members: groups.checks };
        const row = rowByKey(openKey);
        return row ? { kind: 'species' as const, row, members: [] } : null;
    });
    function openPopout(key: string, trigger: HTMLElement): void {
        clearTimeout(closeTimer);
        if (barElement) {
            const bar = barElement.getBoundingClientRect();
            const segment = trigger.getBoundingClientRect();
            const half = POPOUT_WIDTH / 2;
            const centre = segment.left - bar.left + segment.width / 2;
            popoutLeft = Math.min(Math.max(centre, half), Math.max(half, bar.width - half));
        }
        openKey = key;
    }
    function cancelPopoutClose(): void {
        clearTimeout(closeTimer);
    }
    function schedulePopoutClose(): void {
        clearTimeout(closeTimer);
        closeTimer = setTimeout(() => (openKey = null), POPOUT_GRACE_MS);
    }
    function closeOnEscape(event: KeyboardEvent): void {
        if (event.key === 'Escape' && openKey !== null) {
            clearTimeout(closeTimer);
            openKey = null;
        }
    }
    $effect(() => () => clearTimeout(closeTimer));
    function pickSegment(key: string, kind: 'species' | 'others' | 'checks'): void {
        if (kind === 'species') onopen(key);
        else if (kind === 'others') onmore?.();
        else checksElement?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
    }

    // The bar grows into place once, on first paint.
    let grown = $state(false);
    $effect(() => {
        if (grown || rows.length === 0) return;
        const frame = requestAnimationFrame(() => (grown = true));
        return () => cancelAnimationFrame(frame);
    });
    const barReady = $derived(grown || reduceMotion);

    // A photograph that fails to load falls back to the next honest source, never to a hole.
    let failed = $state<Set<string>>(new Set());
    function markFailed(url: string): void {
        failed = new Set([...failed, url]);
    }
    type Picture = { url: string; source: 'feeder' | 'reference'; raw: string } | null;
    function pictureFor(row: ShowcaseRow): Picture {
        if (row.photo && !failed.has(row.photo)) return { url: withAuthParams(row.photo), source: 'feeder', raw: row.photo };
        if (row.reference && !failed.has(row.reference)) return { url: row.reference, source: 'reference', raw: row.reference };
        return null;
    }
    // The pop-out shows the species' stock (reference) photograph, which is what helps put a name to
    // a colour; the feeder's own crop stands in only where there is no reference.
    function stockPictureFor(row: ShowcaseRow): Picture {
        if (row.reference && !failed.has(row.reference)) return { url: row.reference, source: 'reference', raw: row.reference };
        if (row.photo && !failed.has(row.photo)) return { url: withAuthParams(row.photo), source: 'feeder', raw: row.photo };
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
    function percentText(count: number): string {
        if (total <= 0) return '0%';
        const percent = (count / total) * 100;
        return percent > 0 && percent < 1 ? '<1%' : `${Math.round(percent)}%`;
    }
    function rowByKey(key: string): ShowcaseRow | undefined {
        return rows.find((row) => row.key === key);
    }
    function segmentLabel(key: string, kind: string, count: number): string {
        if (kind === 'others') {
            return `${$_('leaderboard.other_species', { default: 'Other' })}, ${count.toLocaleString()} ${countLabel(count)}`;
        }
        if (kind === 'checks') {
            return `${$_('leaderboard.spotlight_needs_check', { default: 'Needs a check' })}, ${count.toLocaleString()} ${countLabel(count)}`;
        }
        const row = rowByKey(key);
        return `${row?.displayName ?? key}, ${count.toLocaleString()} ${countLabel(count)}, ${percentText(count)}`;
    }
</script>

{#if rows.length > 0}
    <section class="space-y-3" data-leaderboard-share aria-label={label}>
        <h2 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
            {label}
        </h2>

        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="relative" bind:this={barElement} onkeydown={closeOnEscape}>
            <div class="flex h-12 gap-1 overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-900" data-spotlight-share>
                {#each segments as segment (segment.key)}
                    <button
                        type="button"
                        class="spotlight-segment min-w-0 overflow-hidden whitespace-nowrap text-left text-sm font-semibold {segment.kind === 'species' && segment.percent >= 5 ? 'px-3' : 'px-0'} {segment.kind === 'checks' ? 'bg-amber-500/70 dark:bg-amber-700/80' : ''} text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white"
                        style:flex-basis="{barReady ? segment.percent : 0}%"
                        style:background-color={segment.kind === 'species' ? colourFor(segment.key) : segment.kind === 'others' ? otherColour : undefined}
                        style:opacity={openKey === null || segment.key === openKey ? 1 : 0.6}
                        aria-label={segmentLabel(segment.key, segment.kind, segment.count)}
                        aria-expanded={openKey === segment.key}
                        aria-describedby={openKey === segment.key ? popoutId : undefined}
                        onpointerenter={(event) => {
                            if (event.pointerType !== 'touch') openPopout(segment.key, event.currentTarget);
                        }}
                        onpointerleave={schedulePopoutClose}
                        onfocus={(event) => {
                            if (event.currentTarget.matches(':focus-visible')) openPopout(segment.key, event.currentTarget);
                        }}
                        onblur={schedulePopoutClose}
                        onclick={() => pickSegment(segment.key, segment.kind)}
                        data-spotlight-segment={segment.kind}
                    >
                        {#if segment.kind === 'species'}
                            {#if segment.percent >= 22}{rowByKey(segment.key)?.displayName} {segment.count.toLocaleString()}{:else if segment.percent >= 5}{segment.count.toLocaleString()}{/if}
                        {/if}
                    </button>
                {/each}
            </div>

            {#if popout}
                <div
                    id={popoutId}
                    role="tooltip"
                    class="spotlight-popout absolute bottom-full z-30 mb-2 w-64 -translate-x-1/2 rounded-xl border border-slate-200 bg-white p-3 shadow-xl dark:border-slate-700 dark:bg-slate-900"
                    style:left="{popoutLeft}px"
                    onpointerenter={cancelPopoutClose}
                    onpointerleave={schedulePopoutClose}
                    data-spotlight-popout
                >
                    {#if popout.kind === 'species' && popout.row}
                        {@const stock = stockPictureFor(popout.row)}
                        <div class="mb-2.5 flex h-36 items-center justify-center overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800">
                            {#if stock}
                                <img src={stock.url} alt="" class="h-full w-full object-cover" onerror={() => markFailed(stock.raw)} />
                            {:else}
                                <span class="text-xs italic text-slate-500 dark:text-slate-400">{$_('leaderboard.spotlight_no_photo', { default: 'No photo from this feeder yet' })}</span>
                            {/if}
                        </div>
                        <p class="font-display text-lg font-bold leading-tight text-slate-900 dark:text-white">{popout.row.displayName}</p>
                        {#if popout.row.subName}
                            <p class="text-sm italic text-slate-500 dark:text-slate-400">{popout.row.subName}</p>
                        {/if}
                        <p class="mt-1.5 text-sm tabular-nums text-slate-700 dark:text-slate-200">
                            {popout.row.count.toLocaleString()} {countLabel(popout.row.count)} · {percentText(popout.row.count)}
                        </p>
                        {#if stock}
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400" data-spotlight-popout-source>
                                {stock.source === 'reference'
                                    ? referenceLabel(popout.row)
                                    : $_('leaderboard.spotlight_feeder_photo', { default: 'Photo from this feeder' })}
                            </p>
                        {/if}
                    {:else}
                        <p class="font-display text-base font-bold text-slate-900 dark:text-white">
                            {popout.kind === 'checks'
                                ? $_('leaderboard.spotlight_needs_check', { default: 'Needs a check' })
                                : $_('leaderboard.other_species', { default: 'Other' })}
                        </p>
                        <ul class="mt-1.5 space-y-1 text-sm">
                            {#each popout.members.slice(0, 6) as member (member.key)}
                                <li class="flex justify-between gap-3">
                                    <span class="min-w-0 truncate text-slate-700 dark:text-slate-200">{member.displayName}</span>
                                    <span class="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">{member.count.toLocaleString()}</span>
                                </li>
                            {/each}
                        </ul>
                        {#if popout.members.length > 6}
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.showcase_more', { values: { count: popout.members.length - 6 }, default: '{count} more below' })}</p>
                        {/if}
                    {/if}
                </div>
            {/if}
        </div>

        {#if groups.checks.length > 0}
            <div class="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-4 dark:border-slate-700" bind:this={checksElement} data-spotlight-checks>
                <div class="flex w-full flex-col gap-1 sm:w-52">
                    <span class="inline-flex items-center gap-1.5 self-start rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-950/70 dark:text-amber-300">
                        <span class="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden="true"></span>{$_('leaderboard.spotlight_needs_check', { default: 'Needs a check' })}
                    </span>
                    {#if nearbyRadiusKm}
                        <span class="text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.unlikely_reason', { values: { radius: nearbyRadiusKm }, default: 'Not reported within {radius} km' })}</span>
                    {/if}
                </div>
                {#each groups.checks as row (row.key)}
                    {@const thumb = pictureFor(row)}
                    <button
                        type="button"
                        class="flex min-h-11 items-center gap-3 rounded-xl border border-slate-200 bg-white py-1.5 pl-1.5 pr-3 text-left transition-colors hover:border-amber-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-amber-600"
                        aria-label={`${$_('leaderboard.spotlight_review', { default: 'Review' })} ${row.displayName}`}
                        onclick={() => onopen(row.key)}
                    >
                        {#if thumb}
                            <img src={thumb.url} alt="" loading="lazy" decoding="async" class="h-9 w-9 rounded-lg object-cover" onerror={() => markFailed(thumb.raw)} />
                        {:else}
                            <span class="h-9 w-9 rounded-lg bg-slate-200 dark:bg-slate-800" aria-hidden="true"></span>
                        {/if}
                        <span class="flex flex-col">
                            <span class="text-sm font-semibold text-slate-900 dark:text-white">{row.displayName}</span>
                            <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">{row.count.toLocaleString()} {countLabel(row.count)}</span>
                        </span>
                        <span class="ml-1 text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('leaderboard.spotlight_review', { default: 'Review' })}</span>
                    </button>
                {/each}
            </div>
        {/if}
    </section>
{/if}

<style>
    /* The bar grows into place once; afterwards only the pop-out changes its look. */
    .spotlight-segment {
        transition:
            flex-basis 0.9s cubic-bezier(0.2, 0.8, 0.2, 1),
            opacity 0.3s ease;
    }

    .spotlight-segment:hover {
        opacity: 1 !important;
    }

    /* The pop-out rises a little into place; under reduced motion it simply appears. */
    @keyframes spotlight-popout {
        from {
            opacity: 0;
            transform: translate(-50%, 4px) scale(0.98);
        }
        to {
            opacity: 1;
            transform: translate(-50%, 0) scale(1);
        }
    }

    .spotlight-popout {
        animation: spotlight-popout 0.16s ease-out;
    }

    @media (prefers-reduced-motion: reduce) {
        .spotlight-popout {
            animation: none;
        }

        .spotlight-segment {
            transition: none;
        }
    }

    :global(.reduced-motion) .spotlight-popout {
        animation: none;
    }

    :global(.reduced-motion) .spotlight-segment {
        transition: none;
    }
</style>
