<script lang="ts">
    import { fade, fly } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { withAuthParams } from '../api/core';
    import {
        shareSegments,
        spotlightGroups,
        SPOTLIGHT_LIST,
        type Presence,
        type ShowcaseRow
    } from '../leaderboard/showcase';

    /**
     * The leaderboard's spotlight. One species at a time is shown large, its photograph at no
     * more than half again its stored size, over a blurred copy of itself; beside it the ranked
     * list, and above both a bar of who made up the window. The spotlight tours the list slowly
     * until someone chooses a species, and never moves for a person who asked for less motion.
     *
     * Species that are probably misidentifications never take a place in the tour, the list or
     * the bar's named segments: they are counted in the bar and named apart to be checked.
     *
     * While it tours, the spotlight is not announced (a new species every few seconds would talk
     * over everything); once someone chooses, the change is announced politely.
     *
     * Every photograph says where it came from: this feeder's newest crop, a labelled reference
     * image when there is none, or a plain placeholder.
     */
    interface Props {
        rows: ShowcaseRow[];
        /** What the leader is, e.g. "Most visits this month"; another species is named by rank. */
        eyebrow: string;
        rankEyebrow: (rank: number) => string;
        countLabel: (count: number) => string;
        /** The species' colour in the timeline and composition charts. */
        colourFor: (key: string) => string;
        otherColour: string;
        presenceFor: (row: ShowcaseRow) => Presence | null;
        evidenceFor?: (key: string) => string | null;
        nearbyRadiusKm?: number | null;
        onopen: (key: string) => void;
        onmore?: () => void;
    }

    let {
        rows,
        eyebrow,
        rankEyebrow,
        countLabel,
        colourFor,
        otherColour,
        presenceFor,
        evidenceFor,
        nearbyRadiusKm = null,
        onopen,
        onmore
    }: Props = $props();

    const TOUR_MS = 7000;
    // A crop is shown at most half again its stored size: past that a feeder crop goes soft.
    const MAX_UPSCALE = 1.5;

    const groups = $derived(spotlightGroups(rows));
    const segments = $derived(shareSegments(rows));
    // A window where every species is flagged still has something to show, flagged as such.
    const tourRows = $derived(groups.list.length > 0 ? groups.list : rows.slice(0, SPOTLIGHT_LIST));
    const leaderCount = $derived(Math.max(1, ...tourRows.map((row) => row.count)));
    const total = $derived(rows.reduce((sum, row) => sum + row.count, 0));

    // The leader until someone chooses; a choice that leaves the ranking falls back to it.
    let chosenKey = $state<string | null>(null);
    const selected = $derived(tourRows.find((row) => row.key === chosenKey) ?? tourRows[0] ?? null);
    const presence = $derived(selected ? presenceFor(selected) : null);

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

    // The tour runs until someone chooses a species or pauses it, rests while a pointer or
    // keyboard focus is on the spotlight, and never starts for reduced motion.
    let tourOn = $state(true);
    let held = $state(false);
    let tourEpoch = $state(0);
    const touring = $derived(tourOn && !reduceMotion && tourRows.length > 1);

    function advance(): void {
        const index = tourRows.findIndex((row) => row.key === selected?.key);
        chosenKey = tourRows[(index + 1) % tourRows.length]?.key ?? null;
    }
    function choose(key: string): void {
        chosenKey = key;
        tourOn = false;
    }
    function toggleTour(): void {
        tourOn = !tourOn;
        tourEpoch += 1;
    }

    // Each segment of the bar previews its species on hover and keyboard focus (never on touch,
    // where a tap chooses the species and the spotlight names it). The pop-out stays open while the
    // pointer travels into it, closes on Escape, and rests the tour while it is open.
    const POPOUT_WIDTH = 256;
    const POPOUT_GRACE_MS = 120;
    const popoutId = `spotlight-popout-${Math.random().toString(36).slice(2, 9)}`;
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
        if (kind === 'species') choose(key);
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
    const picture = $derived(selected ? pictureFor(selected) : null);
    // The pop-out shows the species' stock (reference) photograph, which is what helps put a name to
    // a colour; the feeder's own crop stands in only where there is no reference.
    function stockPictureFor(row: ShowcaseRow): Picture {
        if (row.reference && !failed.has(row.reference)) return { url: row.reference, source: 'reference', raw: row.reference };
        if (row.photo && !failed.has(row.photo)) return { url: withAuthParams(row.photo), source: 'feeder', raw: row.photo };
        return null;
    }

    let stageWidth = $state(0);
    let stageHeight = $state(0);
    let natural = $state<Record<string, { w: number; h: number }>>({});
    function measure(url: string, image: HTMLImageElement): void {
        if (image.naturalWidth > 0) natural = { ...natural, [url]: { w: image.naturalWidth, h: image.naturalHeight } };
    }
    function photoSize(url: string): string {
        const size = natural[url];
        if (!size || stageWidth === 0 || stageHeight === 0) return 'max-width: 100%; max-height: 100%;';
        const scale = Math.min(stageWidth / size.w, stageHeight / size.h, MAX_UPSCALE);
        return `width: ${Math.round(size.w * scale)}px; height: ${Math.round(size.h * scale)}px;`;
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
    function presenceText(value: Presence): string {
        const values = { count: value.present.filter(Boolean).length, total: value.present.length };
        if (value.bucket === 'hour') return $_('leaderboard.spotlight_presence_hours', { values, default: 'On camera in {count} of {total} hours' });
        if (value.bucket === 'month') return $_('leaderboard.spotlight_presence_months', { values, default: 'On camera in {count} of {total} months' });
        return $_('leaderboard.spotlight_presence_days', { values, default: 'On camera on {count} of {total} days' });
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

{#if rows.length > 0 && selected}
    <section class="space-y-4" data-leaderboard-spotlight aria-label={eyebrow}>
        <div class="flex flex-wrap items-center justify-between gap-3">
            <h2 class="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                {$_('leaderboard.spotlight_share_heading', { default: 'Share by species' })}
            </h2>
            {#if !reduceMotion && tourRows.length > 1}
                <button
                    type="button"
                    class="btn btn-secondary min-h-11 gap-2 rounded-full px-4 text-xs"
                    aria-label={tourOn
                        ? $_('leaderboard.spotlight_pause_label', { default: 'Pause the species tour' })
                        : $_('leaderboard.spotlight_play_label', { default: 'Play the species tour' })}
                    onclick={toggleTour}
                    data-spotlight-tour
                >
                    {#if tourOn}
                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M8 5v14M16 5v14" /></svg>
                        {$_('leaderboard.spotlight_pause', { default: 'Pause tour' })}
                    {:else}
                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round" aria-hidden="true"><path d="M7 5l12 7-12 7z" /></svg>
                        {$_('leaderboard.spotlight_play', { default: 'Play tour' })}
                    {/if}
                </button>
            {/if}
        </div>

        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="relative" bind:this={barElement} onkeydown={closeOnEscape}>
            <div class="flex h-12 gap-1 overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-900" data-spotlight-share>
                {#each segments as segment (segment.key)}
                    <button
                        type="button"
                        class="spotlight-segment min-w-0 overflow-hidden whitespace-nowrap text-left text-sm font-semibold {segment.kind === 'species' && segment.percent >= 5 ? 'px-3' : 'px-0'} {segment.kind === 'checks' ? 'bg-amber-500/70 dark:bg-amber-700/80' : ''} text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white"
                        style:flex-basis="{barReady ? segment.percent : 0}%"
                        style:background-color={segment.kind === 'species' ? colourFor(segment.key) : segment.kind === 'others' ? otherColour : undefined}
                        style:opacity={segment.key === selected.key || segment.key === openKey ? 1 : 0.6}
                        aria-label={segmentLabel(segment.key, segment.kind, segment.count)}
                        aria-pressed={segment.kind === 'species' ? segment.key === selected.key : undefined}
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

        <div
            class="grid gap-5 md:grid-cols-12"
            role="group"
            aria-label={eyebrow}
            onmouseenter={() => (held = true)}
            onmouseleave={() => (held = false)}
            onfocusin={() => (held = true)}
            onfocusout={() => (held = false)}
        >
            <article
                class="relative isolate min-h-96 overflow-hidden md:col-span-7 rounded-2xl border border-slate-200/70 bg-slate-950 text-white dark:border-slate-700/60"
                aria-live={touring ? 'off' : 'polite'}
                data-spotlight-stage
                data-photo-source={picture?.source ?? 'none'}
            >
                {#key selected.key}
                    {#if picture}
                        <img
                            src={picture.url}
                            alt=""
                            aria-hidden="true"
                            class="pointer-events-none absolute inset-0 -z-10 h-full w-full scale-125 object-cover opacity-80 blur-3xl brightness-50 saturate-150"
                            in:fade|global={{ duration: reduceMotion ? 0 : 500 }}
                        />
                    {/if}
                {/key}
                {#if touring}
                    {#key `${selected.key}:${tourEpoch}`}
                        <div
                            class="spotlight-progress absolute left-0 top-0 h-1"
                            style:background-color={colourFor(selected.key)}
                            style:animation-duration="{TOUR_MS}ms"
                            style:animation-play-state={held || openKey !== null ? 'paused' : 'running'}
                            onanimationend={advance}
                            data-spotlight-progress
                        ></div>
                    {/key}
                {/if}

                <div class="relative flex h-full flex-col gap-4 p-5 md:p-6">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                        <div class="flex flex-wrap items-center gap-2">
                            <span class="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/80" data-spotlight-eyebrow>
                                {selected.rank === 1 ? eyebrow : rankEyebrow(selected.rank)}
                            </span>
                            {#if selected.flagged}
                                <span class="inline-flex items-center gap-1.5 rounded-full bg-amber-400 px-2 py-0.5 text-xs font-semibold text-amber-950" data-spotlight-flag>
                                    <span class="h-1.5 w-1.5 rounded-full bg-amber-950" aria-hidden="true"></span>{$_('leaderboard.showcase_not_nearby', { default: 'Not reported nearby' })}
                                </span>
                            {/if}
                        </div>
                        {#if evidenceFor?.(selected.key)}
                            <span class="text-xs text-white/75">{evidenceFor(selected.key)}</span>
                        {/if}
                    </div>

                    <div class="flex h-56 items-center justify-center md:h-60" bind:clientWidth={stageWidth} bind:clientHeight={stageHeight}>
                        {#key selected.key}
                            {#if picture}
                                <img
                                    src={picture.url}
                                    alt={selected.displayName}
                                    decoding="async"
                                    class="block rounded-lg shadow-2xl shadow-black/50"
                                    style={photoSize(picture.url)}
                                    onload={(event) => measure(picture.url, event.currentTarget as HTMLImageElement)}
                                    onerror={() => markFailed(picture.raw)}
                                    in:fly|global={{ y: reduceMotion ? 0 : 10, duration: reduceMotion ? 0 : 480 }}
                                />
                            {:else}
                                <span class="text-sm italic text-white/60" in:fade|global={{ duration: reduceMotion ? 0 : 300 }}>
                                    {$_('leaderboard.spotlight_no_photo', { default: 'No photo from this feeder yet' })}
                                </span>
                            {/if}
                        {/key}
                    </div>
                    {#if picture?.source === 'reference'}
                        <p class="-mt-2 text-center text-[11px] text-white/70" data-spotlight-reference-note>{referenceLabel(selected)}</p>
                    {/if}

                    <div class="flex flex-wrap items-end justify-between gap-4">
                        <div class="min-w-0">
                            <h3 class="font-display text-3xl font-bold leading-tight md:text-4xl">{selected.displayName}</h3>
                            {#if selected.subName}
                                <p class="mt-0.5 text-sm italic text-white/70">{selected.subName}</p>
                            {/if}
                        </div>
                        <dl class="flex gap-6 text-right">
                            <div>
                                <dd class="font-display text-2xl font-bold tabular-nums md:text-3xl">{selected.count.toLocaleString()}</dd>
                                <dt class="text-xs text-white/70">{countLabel(selected.count)}</dt>
                            </div>
                            <div>
                                <dd class="font-display text-2xl font-bold tabular-nums md:text-3xl">{percentText(selected.count)}</dd>
                                <dt class="text-xs text-white/70">{$_('leaderboard.spotlight_of_total', { default: 'of the total' })}</dt>
                            </div>
                            {#if selected.avgConfidence !== null}
                                <div>
                                    <dd class="font-display text-2xl font-bold tabular-nums md:text-3xl">{Math.round(selected.avgConfidence * 100)}%</dd>
                                    <dt class="text-xs text-white/70">{$_('leaderboard.avg_confidence', { default: 'Avg confidence' }).toLowerCase()}</dt>
                                </div>
                            {/if}
                        </dl>
                    </div>

                    {#if presence}
                        <div class="space-y-2" data-spotlight-presence>
                            <div class="grid gap-1" style:grid-template-columns="repeat({presence.present.length}, minmax(0, 1fr))" aria-hidden="true">
                                {#each presence.present as present, index (index)}
                                    <span
                                        class="spotlight-cell h-5 rounded-sm"
                                        style:background-color={present ? colourFor(selected.key) : 'rgb(255 255 255 / 0.08)'}
                                    ></span>
                                {/each}
                            </div>
                            <div class="flex justify-between gap-3 text-xs text-white/70">
                                <span>{presence.firstLabel ?? ''}</span>
                                <span class="text-white/85">{presenceText(presence)}</span>
                                <span>{presence.lastLabel ?? ''}</span>
                            </div>
                        </div>
                    {/if}

                    <div class="mt-auto">
                        <button type="button" class="btn btn-secondary min-h-11 px-4 text-xs" onclick={() => onopen(selected.key)}>
                            {$_('leaderboard.view_species', { values: { species: selected.displayName }, default: 'View {species}' })}
                        </button>
                    </div>
                </div>
            </article>

            <div class="flex flex-col gap-1.5 md:col-span-5">
                <ol class="flex flex-col gap-1.5" data-spotlight-list>
                    {#each tourRows as row (row.key)}
                        {@const thumb = pictureFor(row)}
                        <li>
                            <button
                                type="button"
                                class="flex w-full items-center gap-3 rounded-xl border px-2.5 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {row.key === selected.key
                                    ? 'border-slate-300 bg-slate-100 dark:border-slate-600 dark:bg-slate-800/70'
                                    : 'border-transparent hover:bg-slate-50 dark:hover:bg-slate-800/40'}"
                                aria-pressed={row.key === selected.key}
                                aria-label={$_('leaderboard.spotlight_show', { values: { species: row.displayName }, default: 'Show {species} in the spotlight' })}
                                onclick={() => choose(row.key)}
                            >
                                <span class="w-5 shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">{row.rank}</span>
                                {#if thumb}
                                    <img src={thumb.url} alt="" loading="lazy" decoding="async" class="h-10 w-10 shrink-0 rounded-lg object-cover" onerror={() => markFailed(thumb.raw)} />
                                {:else}
                                    <span class="h-10 w-10 shrink-0 rounded-lg bg-slate-200 dark:bg-slate-800" aria-hidden="true"></span>
                                {/if}
                                <span class="flex min-w-0 flex-1 flex-col gap-1.5">
                                    <span class="flex items-baseline justify-between gap-3">
                                        <span class="truncate text-sm font-semibold text-slate-900 dark:text-white">{row.displayName}</span>
                                        <span class="shrink-0 text-sm tabular-nums text-slate-500 dark:text-slate-400">{row.count.toLocaleString()}</span>
                                    </span>
                                    <span class="block h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" aria-hidden="true">
                                        <span
                                            class="spotlight-fill block h-full rounded-full"
                                            style:width="{barReady ? Math.max(1.5, (row.count / leaderCount) * 100) : 0}%"
                                            style:background-color={colourFor(row.key)}
                                        ></span>
                                    </span>
                                </span>
                            </button>
                        </li>
                    {/each}
                </ol>
                {#if groups.others.species > 0}
                    <button
                        type="button"
                        class="flex min-h-11 items-center justify-between gap-3 rounded-xl px-3 text-sm text-slate-500 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-400 dark:hover:text-brand-300"
                        onclick={() => onmore?.()}
                        data-spotlight-more
                    >
                        <span>{$_('leaderboard.showcase_more', { values: { count: groups.others.species }, default: '{count} more below' })}</span>
                        <span class="tabular-nums">{groups.others.count.toLocaleString()} {countLabel(groups.others.count)}</span>
                    </button>
                {/if}
            </div>
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
    /* The bar and the list's fills grow into place once; afterwards a choice only changes opacity. */
    .spotlight-segment {
        transition:
            flex-basis 0.9s cubic-bezier(0.2, 0.8, 0.2, 1),
            opacity 0.3s ease;
    }

    .spotlight-segment:hover {
        opacity: 1 !important;
    }

    .spotlight-fill {
        transition: width 0.9s cubic-bezier(0.2, 0.8, 0.2, 1);
    }

    .spotlight-cell {
        transition: background-color 0.4s ease;
    }

    /* The tour's clock: one sweep per species; its end moves the spotlight on. */
    @keyframes spotlight-progress {
        from {
            width: 0;
        }
        to {
            width: 100%;
        }
    }

    .spotlight-progress {
        animation-name: spotlight-progress;
        animation-timing-function: linear;
        animation-fill-mode: forwards;
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

        .spotlight-segment,
        .spotlight-fill,
        .spotlight-cell {
            transition: none;
        }
    }

    :global(.reduced-motion) .spotlight-popout {
        animation: none;
    }

    :global(.reduced-motion) .spotlight-segment,
    :global(.reduced-motion) .spotlight-fill,
    :global(.reduced-motion) .spotlight-cell {
        transition: none;
    }
</style>
