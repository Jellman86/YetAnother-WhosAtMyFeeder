<script lang="ts">
    import { tick, untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { portal } from '../utils/portal';
    import MediaImage from './MediaImage.svelte';
    import {
        formatOffset,
        preferredCandidate,
        momentImageUrl,
        momentThumbnailUrl,
        type FrameMoment
    } from '../utils/frame-moments';

    /**
     * One ordered strip of the visit's photograph choices (#256).
     *
     * A frame with several birds offers each crop separately. Hover or focus opens a pop-out
     * that shows the frame at decision size with what the model read in it, and one action,
     * "Use this frame", which changes the record's photograph and nothing else. Where a frame
     * came from is not shown here; Details holds that.
     */
    interface Props {
        moments: FrameMoment[];
        /** The moment the record uses as its photograph now, if it is one of these. */
        current: FrameMoment | null;
        primaryName: string;
        loading?: boolean;
        /** The moment being saved as the photograph, while the request is in flight. */
        applyingKey?: string | null;
        /** Any save or regeneration in flight; every action waits for it. */
        busy?: boolean;
        /** The camera's own snapshot, for the as-recorded moment which has no candidate record. */
        asRecordedUrl?: string | null;
        /**
         * The record's saved photograph. It is the current moment's own picture, so it stands in
         * when that moment's candidate file is gone, and only for that moment.
         */
        photographUrl?: string | null;
        /** What to say when the visit has no frames at all; the strip's own wording otherwise. */
        emptyText?: string | null;
        canRegenerate?: boolean;
        regeneratePending?: boolean;
        onuse: (moment: FrameMoment) => void;
        onregenerate?: () => void;
        eventId?: string;
        onremove?: (candidateId: string, dismissed: boolean) => Promise<void>;
    }

    let {
        moments,
        current,
        primaryName,
        loading = false,
        applyingKey = null,
        busy = false,
        asRecordedUrl = null,
        photographUrl = null,
        emptyText = null,
        canRegenerate = false,
        regeneratePending = false,
        onuse,
        onregenerate,
        eventId,
        onremove
    }: Props = $props();

    let openIndex = $state<number | null>(null);
    // With one moment there is nothing to choose between, so it carries no "Chosen" mark.
    const marksChoice = $derived(moments.length > 1);
    // An earlier photograph is not a frame of the clip, so a strip holding one, like a strip of
    // several birds' crops, counts photo options rather than frames.
    let removedPhoto = $state<{ eventId: string; candidateId: string } | null>(null);
    let removalError = $state(false);
    let hoverPaused = false;
    let undoButton = $state<HTMLButtonElement | null>(null);
    async function removeChoice(moment: FrameMoment): Promise<void> {
        const candidate = preferredCandidate(moment);
        const subject = eventId;
        if (!candidate || !subject || !onremove || busy) return;
        removalError = false;
        try {
            await onremove(candidate.candidate_id, true);
            if (eventId === subject) {
                hoverPaused = true;
                hide(true);
                removedPhoto = { eventId: subject, candidateId: candidate.candidate_id };
                await tick();
                if (eventId === subject) undoButton?.focus();
            }
        } catch {
            if (eventId === subject) removalError = true;
        }
    }
    async function undoRemoval(): Promise<void> {
        if (!removedPhoto || removedPhoto.eventId !== eventId || !onremove || busy) return;
        const previous = removedPhoto;
        removalError = false;
        try {
            await onremove(previous.candidateId, false);
            if (removedPhoto === previous) removedPhoto = null;
        } catch { removalError = true; }
    }

    const offersPhotoOptions = $derived(
        moments.some((moment) => moment.choice === 'crop' || moment.choice === 'previous')
    );
    let rootEl = $state<HTMLElement | null>(null);
    let triggers = $state<HTMLElement[]>([]);
    let closeTimer: ReturnType<typeof setTimeout> | null = null;

    // A pointer travelling from the thumbnail up into the panel crosses a gap; closing on the
    // first mouseleave would make the panel impossible to reach (WCAG 2.2 SC 1.4.13).
    const CLOSE_GRACE_MS = 120;
    const PANEL_WIDTH = 288;
    const PANEL_ESTIMATED_HEIGHT = 320;
    const GAP = 8;
    const VIEWPORT_MARGIN = 8;

    let anchor = $state<{ x: number; y: number; above: boolean; sheet: boolean } | null>(null);

    // On a phone there is no room beside a thumbnail and no hover to lose: the panel becomes
    // a sheet at the foot of the screen, with a backdrop and its own Close.
    const SHEET_QUERY = '(max-width: 639px)';

    function isSheet(): boolean {
        return typeof window !== 'undefined' && window.matchMedia(SHEET_QUERY).matches;
    }

    // A tap is not a hover. A touch browser replays a tap as mouseenter, then (on Android and
    // desktop Chrome, not iOS Safari, which does not focus a button on tap) focus, then click.
    // If either of the first two opened the sheet, its backdrop would be under the finger by the
    // time the click arrived and would close it again, so the sheet would only flicker. Hover
    // opens the pop-out for a hovering pointer alone (a mouse or a pen held above the screen),
    // focus opens it for the keyboard alone, and a tap opens it by its click. The sheet never
    // opens on hover: a backdrop under a hovering pointer is a mouseleave, which would close
    // what the mouseenter had just opened.
    function hoverOpen(index: number, event: PointerEvent): void {
        if (hoverPaused) return;
        if (event.pointerType === 'touch' || isSheet()) return;
        show(index);
    }

    function focusOpen(index: number, event: FocusEvent): void {
        if (!isKeyboardFocus(event.target)) return;
        show(index);
    }

    function isKeyboardFocus(target: EventTarget | null): boolean {
        if (!(target instanceof Element)) return true;
        try {
            return target.matches(':focus-visible');
        } catch {
            // A browser without :focus-visible cannot tell a tap from a Tab; opening is the
            // safer reading, and its taps close the pop-out by focusout in any case.
            return true;
        }
    }

    // The sheet has a backdrop, a Close and Escape; the pointer wandering off is not a
    // dismissal there.
    function hoverClose(): void {
        if (anchor?.sheet) return;
        hide();
    }

    function place(index: number): void {
        const trigger = triggers[index];
        if (!trigger) return;
        if (isSheet()) {
            anchor = { x: 0, y: 0, above: false, sheet: true };
            return;
        }
        const rect = trigger.getBoundingClientRect();
        // The strip sits at the foot of the photograph, so the panel normally opens above it
        // and only drops below when the top of the window is too close.
        const above = rect.top - GAP - PANEL_ESTIMATED_HEIGHT >= VIEWPORT_MARGIN
            || rect.bottom + GAP + PANEL_ESTIMATED_HEIGHT > window.innerHeight;
        const half = PANEL_WIDTH / 2;
        const centre = Math.min(
            Math.max(rect.left + rect.width / 2, half + VIEWPORT_MARGIN),
            window.innerWidth - half - VIEWPORT_MARGIN
        );
        anchor = { x: centre, y: above ? rect.top - GAP : rect.bottom + GAP, above, sheet: false };
    }

    function show(index: number): void {
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        place(index);
        openIndex = index;
    }

    function cancelScheduledClose(): void {
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
    }

    function hide(immediate = false): void {
        if (closeTimer) clearTimeout(closeTimer);
        if (immediate) {
            closeTimer = null;
            openIndex = null;
            return;
        }
        closeTimer = setTimeout(() => {
            openIndex = null;
            closeTimer = null;
        }, CLOSE_GRACE_MS);
    }

    function handleFocusOut(event: FocusEvent): void {
        const next = event.relatedTarget;
        // In the sheet, focus that goes nowhere (a tap on its picture) is not focus moving on: the
        // backdrop, Close and Escape dismiss it. A desktop pop-out closes as before, so a click
        // on plain page or a switch away never strands it with only the record's Escape left.
        if (!(next instanceof Node)) {
            if (!anchor?.sheet) hide(true);
            return;
        }
        if (rootEl?.contains(next) || panelEl?.contains(next)) return;
        hide(true);
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape' && openIndex !== null) {
            // The modal closes on Escape too; a pop-out closes first and the modal stays.
            event.preventDefault();
            event.stopPropagation();
            const index = openIndex;
            hide(true);
            triggers[index]?.focus();
        }
    }

    // The panel is portalled to the body, outside the dialog's focus trap, so Tab never
    // reaches it. The arrow keys carry focus down into the panel and Tab carries it back.
    function handleTriggerKeydown(event: KeyboardEvent, index: number): void {
        const along = alongStrip(event.key, index);
        if (along !== null) {
            event.preventDefault();
            triggers[along]?.focus();
            return;
        }
        if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
        event.preventDefault();
        if (openIndex !== index) show(index);
        queueMicrotask(() => panelEl?.querySelector<HTMLElement>('button, [tabindex]')?.focus());
    }

    // Left, Right, Home and End move along the strip, so the last of many is one key away.
    function alongStrip(key: string, index: number): number | null {
        const last = moments.length - 1;
        if (key === 'ArrowLeft') return Math.max(index - 1, 0);
        if (key === 'ArrowRight') return Math.min(index + 1, last);
        if (key === 'Home') return 0;
        if (key === 'End') return last;
        return null;
    }

    // Focus returns to the trigger before the pop-out hides: moving focus replays focusin on the
    // trigger, and on an index that is still open that is a no-op, whereas after hiding it would
    // reopen what Escape had just closed.
    function handlePanelKeydown(event: KeyboardEvent): void {
        if (event.key === 'Tab' || event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            const index = openIndex;
            if (index !== null) triggers[index]?.focus();
            if (event.key === 'Escape') hide(true);
        }
    }

    let panelEl = $state<HTMLElement | null>(null);

    // Once a choice becomes the photograph, its Use button gives way to a label and the focus on
    // it would fall to the page, where neither the strip's Escape nor the modal's can hear it. On
    // a phone that leaves the sheet open with no key to close it. Focus moves to the panel's
    // Close, or to the thumbnail if the panel has gone, and only when it had nowhere else to be.
    let usedKey = $state<string | null>(null);

    function use(moment: FrameMoment): void {
        usedKey = moment.key;
        onuse(moment);
    }

    $effect(() => {
        const key = usedKey;
        if (key === null || current?.key !== key) return;
        const index = moments.findIndex((moment) => moment.key === key);
        untrack(() => {
            usedKey = null;
            queueMicrotask(() => {
                const active = document.activeElement;
                if (active && active !== document.body && active.isConnected) return;
                const target = openIndex === index ? panelEl?.querySelector<HTMLElement>('button') : triggers[index];
                target?.focus();
            });
        });
    });

    $effect(() => {
        return () => {
            if (closeTimer) clearTimeout(closeTimer);
        };
    });

    // The panel is placed in viewport coordinates, so it follows its trigger as the modal
    // scrolls, and closes once the trigger has left the window.
    $effect(() => {
        if (openIndex === null) return;
        const index = openIndex;
        let pending: number | null = null;
        const follow = () => {
            if (pending !== null) return;
            pending = requestAnimationFrame(() => {
                pending = null;
                const rect = triggers[index]?.getBoundingClientRect();
                if (!rect || rect.bottom < 0 || rect.top > window.innerHeight) {
                    hide(true);
                    return;
                }
                place(index);
            });
        };
        // Safari does not focus a button on click, so after a click focus can still be on the
        // modal's own Close and its Escape would close the whole modal. While a comparison is
        // open, Escape closes it first wherever focus is. Focus returns to its thumbnail from the
        // strip, the panel or nowhere; focus elsewhere, such as a search being typed, stays put.
        const escape = (event: KeyboardEvent) => {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            const active = document.activeElement;
            const lost = !active || active === document.body;
            if (lost || (active && (rootEl?.contains(active) || panelEl?.contains(active)))) {
                triggers[index]?.focus();
            }
            hide(true);
        };
        window.addEventListener('scroll', follow, true);
        window.addEventListener('resize', follow);
        window.addEventListener('keydown', escape, true);
        return () => {
            if (pending !== null) cancelAnimationFrame(pending);
            window.removeEventListener('scroll', follow, true);
            window.removeEventListener('resize', follow);
            window.removeEventListener('keydown', escape, true);
        };
    });

    // A moment that disappears (regeneration replaced the list) must not leave a panel open
    // over nothing.
    $effect(() => {
        if (openIndex !== null && openIndex >= moments.length) {
            openIndex = null;
        }
    });

    let scrollerEl = $state<HTMLElement | null>(null);
    let moreBefore = $state(false);
    let moreAfter = $state(false);

    // The edge controls sit over the strip's ends, so a thumbnail counts as in view only once it
    // is clear of them. Paging keeps one thumbnail's width of overlap, so nothing is skipped.
    const EDGE_CLEARANCE = 48;
    const THUMBNAIL_STEP = 62;

    /**
     * Tracks whether the strip runs on past either end. Each end then gets a fade and a control;
     * both are hidden while that end is in view. Thumbnails load lazily, so image loads are
     * watched as well as resizes.
     */
    function watchOverflow(node: HTMLElement) {
        const update = () => {
            moreBefore = node.scrollLeft > 1;
            moreAfter = node.scrollLeft + node.clientWidth < node.scrollWidth - 1;
        };
        update();
        const resize = new ResizeObserver(update);
        resize.observe(node);
        // The container keeps its size when the moment list changes, so a resize alone would
        // leave the ends describing a strip that is no longer there.
        const mutation = new MutationObserver(update);
        mutation.observe(node, { childList: true });
        node.addEventListener('load', update, true);
        node.addEventListener('scroll', update, { passive: true });
        return {
            destroy() {
                resize.disconnect();
                mutation.disconnect();
                node.removeEventListener('load', update, true);
                node.removeEventListener('scroll', update);
            }
        };
    }

    function scrollBehavior(): ScrollBehavior {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    }

    function scrollAlong(direction: -1 | 1): void {
        if (!scrollerEl) return;
        const step = Math.max(scrollerEl.clientWidth - EDGE_CLEARANCE * 2 - THUMBNAIL_STEP, THUMBNAIL_STEP);
        scrollerEl.scrollBy({ left: direction * step, behavior: scrollBehavior() });
    }

    /** Scrolls the strip, and only the strip, until a thumbnail is clear of the edge controls. */
    function reveal(trigger: HTMLElement, centre: boolean): void {
        const scroller = scrollerEl;
        if (!scroller || scroller.scrollWidth <= scroller.clientWidth) return;
        const view = scroller.getBoundingClientRect();
        const rect = trigger.getBoundingClientRect();
        const left = rect.left - view.left;
        const right = rect.right - view.left;
        let delta = 0;
        if (left < EDGE_CLEARANCE) delta = left - EDGE_CLEARANCE;
        else if (right > view.width - EDGE_CLEARANCE) delta = right - (view.width - EDGE_CLEARANCE);
        if (delta === 0) return;
        if (centre) delta = (left + right) / 2 - view.width / 2;
        scroller.scrollLeft += delta;
    }

    // Focus that arrives by keyboard (Tab or the arrows) brings its thumbnail clear of the ends.
    // A pointer's focus is left alone: moving the strip under a press would drop its click.
    function revealFocused(event: FocusEvent): void {
        const target = event.target;
        if (!(target instanceof HTMLElement) || !triggers.includes(target)) return;
        if (isKeyboardFocus(target)) reveal(target, false);
    }

    // The photograph in use is in view whenever the strip opens or its list changes, however far
    // along it sits. A list from another capture starts the strip again from its first frame.
    let shownKeys: string[] = [];
    $effect(() => {
        const keys = moments.filter((moment) => !moment.asRecorded).map((moment) => moment.key);
        const index = moments.findIndex((moment) => moment.key === current?.key);
        const trigger = index >= 0 ? triggers[index] : undefined;
        const scroller = scrollerEl;
        untrack(() => {
            if (scroller && keys.length > 0 && !keys.some((key) => shownKeys.includes(key))) {
                scroller.scrollLeft = 0;
            }
            shownKeys = keys;
            if (trigger) reveal(trigger, true);
        });
    });

    // A thumbnail that fails to load degrades to a same-size placeholder, never a hole. The
    // current moment first falls back to the saved photograph, which is the same picture.
    function thumbnailSources(moment: FrameMoment): Array<string | null> {
        return [moment.asRecorded ? asRecordedUrl : momentThumbnailUrl(moment), isCurrent(moment) ? photographUrl : null];
    }

    function imageSources(moment: FrameMoment): Array<string | null> {
        return [moment.asRecorded ? asRecordedUrl : momentImageUrl(moment), isCurrent(moment) ? photographUrl : null];
    }

    function framingLabel(moment: FrameMoment): string {
        if (moment.asRecorded) {
            return $_('detection.snapshot_framing_as_recorded', { default: 'As Frigate recorded it' });
        }
        if (moment.previous) {
            return $_('detection.snapshot_framing_previous', { default: 'An earlier photograph' });
        }
        return moment.crop
            ? $_('detection.snapshot_framing_close', { default: 'Close on the bird' })
            : $_('detection.snapshot_framing_whole', { default: 'Whole frame' });
    }

    function isCurrent(moment: FrameMoment): boolean {
        return current?.key === moment.key;
    }

    function readLine(moment: FrameMoment): string | null {
        if (!moment.read) return null;
        const score = moment.read.score === null ? null : Math.round(moment.read.score * 100);
        return score === null ? moment.read.label : `${moment.read.label} ${score}%`;
    }

    function positionLabel(moment: FrameMoment): string {
        return offersPhotoOptions
            ? $_('detection.photo_option_position', {
                values: { position: moment.position, count: moments.length },
                default: 'Photo option {position} of {count}'
            })
            : $_('detection.frame_position', {
                values: { position: moment.position, count: moments.length },
                default: 'Frame {position} of {count}'
            });
    }
</script>

<div
    bind:this={rootEl}
    class="flex flex-col gap-1 px-3 pb-3"
    data-frame-strip
    aria-busy={loading || busy}
    onpointermove={() => { hoverPaused = false; }}
    onmouseleave={() => { hoverPaused = false; hoverClose(); }}
    onfocusout={handleFocusOut}
    onkeydown={handleKeydown}
    role="presentation"
>
    <div class="flex min-h-4 items-center justify-between gap-2 px-1 text-3xs font-semibold text-white/65" aria-live="polite">
        <span>
            {#if loading}
                {$_('detection.snapshot_candidates_loading', { default: 'Loading frames...' })}
            {:else if moments.length === 0}
                {emptyText ?? $_('detection.frame_strip_empty', { default: 'No frames kept from this visit yet.' })}
            {:else if moments.length === 1}
                {offersPhotoOptions
                    ? $_('detection.photo_option_count_one', { default: '1 photo option from this visit' })
                    : $_('detection.frame_strip_count_one', { default: '1 frame from this visit' })}
            {:else}
                {$_(offersPhotoOptions ? 'detection.photo_option_count' : 'detection.frame_strip_count', {
                    values: { count: moments.length },
                    default: offersPhotoOptions ? '{count} photo options from this visit' : '{count} frames from this visit'
                })}
            {/if}
        </span>
        <span class="hidden truncate text-white/45 sm:inline">
            {$_('detection.frame_strip_hint', {
                default: 'Choosing one changes the photograph, not the identification.'
            })}
        </span>
    </div>
    <div class="flex min-w-0 items-center gap-1.5">
        <div class="snapshot-strip-shell relative min-w-0 flex-1" data-snapshot-strip-shell>
            <div
                bind:this={scrollerEl}
                class="snapshot-strip -my-2 flex min-w-0 gap-1.5 overflow-x-auto px-1 py-3"
                data-frame-strip-scroller
                use:watchOverflow
                onfocusin={revealFocused}
            >
                {#if loading && moments.length === 0}
                    <!-- Holds a thumbnail's room while the frames are read, so they arrive in place. -->
                    <span class="shrink-0 rounded-md p-1" aria-hidden="true" data-frame-strip-pending>
                        <span class="block h-9 w-12 rounded-md bg-slate-800/70"></span>
                    </span>
                {/if}
                {#each moments as moment, index (moment.key)}
                    {@const chosen = isCurrent(moment)}
                    <div
                        class="relative shrink-0"
                        onpointerenter={(event) => hoverOpen(index, event)}
                        onfocusin={(event) => focusOpen(index, event)}
                        role="presentation"
                    >
                        <button
                            type="button"
                            bind:this={triggers[index]}
                            class="relative block min-h-11 min-w-11 shrink-0 rounded-md p-1 transition duration-200 ease-out motion-reduce:transform-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 {chosen && marksChoice
                                ? 'z-10 -translate-y-1 scale-105 bg-white/15 opacity-100 shadow-lg shadow-black/50'
                                : chosen ? 'opacity-100' : 'opacity-80 hover:opacity-100'}"
                            aria-pressed={chosen}
                            aria-expanded={openIndex === index}
                            aria-label={$_(offersPhotoOptions ? 'detection.photo_option_compare' : 'detection.frame_compare', {
                                values: { position: moment.position, count: moments.length },
                                default: offersPhotoOptions ? 'Compare photo option {position} of {count}' : 'Compare frame {position} of {count}'
                            })}
                            onclick={(event) => { event.stopPropagation(); show(index); }}
                            onkeydown={(event) => handleTriggerKeydown(event, index)}
                        >
                            <MediaImage
                                sources={thumbnailSources(moment)}
                                alt=""
                                loading="lazy"
                                decoding="async"
                                width={48}
                                height={36}
                                class="block h-9 w-12 rounded-md bg-slate-800 object-cover"
                                placeholderClass="text-slate-500"
                                iconClass="h-4 w-4"
                            />
                            {#if chosen && marksChoice}
                                <span class="pointer-events-none absolute bottom-1.5 left-1.5 rounded bg-brand-500 px-1 text-3xs font-bold leading-4 text-slate-950">
                                    {$_('detection.frame_chosen_badge', { default: 'Chosen' })}
                                </span>
                            {/if}
                        </button>

                        {#if openIndex === index && anchor}
                            {@const read = readLine(moment)}
                            {@const applying = applyingKey === moment.key}
                            {#if anchor.sheet}
                                <!-- Needs your call is itself a z-[70] layer. Portalled after it and
                                     before the sheet, the backdrop shares that layer and covers it. -->
                                <div
                                    use:portal
                                    class="fixed inset-0 z-[70] bg-slate-950/50"
                                    data-frame-strip-backdrop
                                    onclick={() => hide(true)}
                                    role="presentation"
                                ></div>
                            {/if}
                            <div
                                bind:this={panelEl}
                                use:portal
                                style={anchor.sheet ? '' : `left: ${anchor.x}px; top: ${anchor.y}px;`}
                                class="fixed z-[70] overflow-hidden border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl shadow-slate-950/40 motion-safe:animate-in motion-safe:fade-in {anchor.sheet
                                    ? 'inset-x-0 bottom-0 rounded-t-2xl motion-safe:slide-in-from-bottom-4'
                                    : anchor.above
                                      ? 'w-72 max-w-[calc(100vw-16px)] -translate-x-1/2 -translate-y-full rounded-2xl motion-safe:zoom-in-95'
                                      : 'w-72 max-w-[calc(100vw-16px)] -translate-x-1/2 rounded-2xl motion-safe:zoom-in-95'}"
                                role="presentation"
                                data-frame-strip-panel
                                onmouseenter={cancelScheduledClose}
                                onpointermove={() => { hoverPaused = false; }}
    onmouseleave={() => { hoverPaused = false; hoverClose(); }}
                                onfocusout={handleFocusOut}
                                onkeydown={handlePanelKeydown}
                            >
                              <div
                                class="relative"
                                role="group"
                                aria-label={positionLabel(moment)}
                              >
                                <button
                                    type="button"
                                    class="absolute right-2 top-2 z-10 inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/25 bg-slate-950/60 text-white backdrop-blur-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                                    aria-label={$_('common.close', { default: 'Close' })}
                                    onclick={(event) => { event.stopPropagation(); const current = openIndex; if (current !== null) triggers[current]?.focus(); hide(true); }}
                                >
                                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" /></svg>
                                </button>
                                <MediaImage
                                    sources={imageSources(moment)}
                                    alt={offersPhotoOptions
                                        ? $_('detection.photo_option_image_alt', { default: 'Candidate photograph from this visit' })
                                        : primaryName}
                                    decoding="async"
                                    class="w-full bg-slate-950 object-contain {anchor.sheet ? 'h-56' : 'h-40'}"
                                    placeholderClass="text-slate-600"
                                    iconClass="h-8 w-8"
                                />
                                <div class="flex flex-col gap-1.5 p-3 text-[0.8125rem]">
                                    <div class="flex items-baseline justify-between gap-2">
                                        <span class="text-3xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                                            {positionLabel(moment)}
                                            &middot; {framingLabel(moment)}
                                        </span>
                                        {#if formatOffset(moment.offsetSeconds)}
                                            <span class="shrink-0 text-xs tabular-nums text-slate-400">{formatOffset(moment.offsetSeconds)}</span>
                                        {/if}
                                    </div>
                                    {#if read}
                                        <div class="flex items-baseline justify-between gap-2">
                                            <span class="text-slate-400">{$_(moment.choice === 'crop' ? 'detection.photo_option_model_read' : 'detection.frame_model_read', { default: moment.choice === 'crop' ? 'Model reads this crop as' : 'Model reads this frame as' })}</span>
                                            <span class="shrink-0 font-semibold text-white">{read}</span>
                                        </div>
                                        <p class="text-xs text-slate-500">
                                            {$_('detection.frame_read_note', {
                                                default: 'A read of one frame. The identification stays until you change it.'
                                            })}
                                        </p>
                                    {:else if moment.previous}
                                        <p class="text-xs text-slate-500">
                                            {$_('detection.previous_photo_note', {
                                                default: 'The photograph this record had before a later analysis replaced it.'
                                            })}
                                        </p>
                                    {:else}
                                        <p class="text-xs text-slate-500">
                                            {$_('detection.frame_no_read', { default: 'The model has not read this frame on its own.' })}
                                        </p>
                                    {/if}
                                    {#if chosen}
                                        <span class="mt-1 inline-flex min-h-10 items-center justify-center rounded-xl border border-slate-700 px-3 text-xs font-semibold text-slate-300">
                                            {$_('detection.frame_is_photograph', { default: 'The photograph now' })}
                                        </span>
                                    {:else}
                                        <button
                                            type="button"
                                            class="btn btn-primary mt-1 min-h-10 px-3 text-xs"
                                            disabled={busy}
                                            onclick={(event) => { event.stopPropagation(); use(moment); }}
                                        >
                                            {#if applying}
                                                <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true"></span>
                                            {/if}
                                            {$_(offersPhotoOptions ? 'detection.photo_option_use' : 'detection.frame_use', { default: offersPhotoOptions ? 'Use this photo' : 'Use this frame' })}
                                        </button>
                                    {/if}
                                    {#if onremove && preferredCandidate(moment)}
                                        {@const candidate = preferredCandidate(moment)}
                                        <button type="button" class="btn btn-ghost mt-1 min-h-11 px-3 text-xs"
                                            disabled={busy || Boolean(candidate?.selected)}
                                            onclick={(event) => { event.stopPropagation(); void removeChoice(moment); }}>
                                            {$_('visits.remove_photo', { default: 'Remove photo choice' })}
                                        </button>
                                        {#if candidate?.selected}<p class="text-xs text-slate-500">{$_('visits.choose_first', { default: 'Choose another photograph before removing this one.' })}</p>{/if}
                                    {/if}
                                </div>
                              </div>
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
            {#each [
                { forward: false, shown: moreBefore, label: $_('detection.frame_strip_scroll_left', { default: 'Scroll left' }) },
                { forward: true, shown: moreAfter, label: $_('detection.frame_strip_scroll_right', { default: 'Scroll right' }) }
            ] as end (end.forward)}
                <!-- The fade says the strip runs on; the control takes it there. Keyboard users
                     move along the strip itself, so the control stays out of the Tab order. -->
                <div
                    class="pointer-events-none absolute inset-y-2 w-14 from-transparent to-slate-950/90 transition-opacity duration-150 motion-reduce:transition-none {end.forward ? 'right-0 bg-gradient-to-r' : 'left-0 bg-gradient-to-l'} {end.shown ? 'opacity-100' : 'opacity-0'}"
                    data-snapshot-strip-fade
                    aria-hidden="true"
                ></div>
                <button
                    type="button"
                    tabindex="-1"
                    class="group absolute inset-y-0 flex w-11 items-center transition-[opacity,visibility] duration-150 motion-reduce:transition-none {end.forward ? 'right-0 justify-end' : 'left-0 justify-start'} {end.shown ? 'visible opacity-100' : 'pointer-events-none invisible opacity-0'}"
                    aria-label={end.label}
                    title={end.label}
                    data-frame-strip-back={end.forward ? undefined : ''}
                    data-frame-strip-forward={end.forward ? '' : undefined}
                    onclick={(event) => { event.stopPropagation(); scrollAlong(end.forward ? 1 : -1); }}
                >
                    <span class="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/20 bg-slate-950/75 text-white/80 shadow-md shadow-black/40 backdrop-blur-sm transition-colors group-hover:border-white/40 group-hover:text-white group-active:bg-slate-900">
                        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path d={end.forward ? 'm9 6 6 6-6 6' : 'm15 6-6 6 6 6'} stroke-linecap="round" stroke-linejoin="round" />
                        </svg>
                    </span>
                </button>
            {/each}
        </div>
        {#if canRegenerate && onregenerate}
            <button
                type="button"
                class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-brand-300/35 bg-brand-500/15 text-brand-100 transition-colors hover:bg-brand-500/25 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                disabled={regeneratePending || busy}
                title={$_('detection.snapshot_regenerate', { default: 'Regenerate snapshots and recount birds' })}
                aria-label={$_('detection.snapshot_regenerate', { default: 'Regenerate snapshots and recount birds' })}
                onclick={(event) => { event.stopPropagation(); onregenerate?.(); }}
            >
                {#if regeneratePending}
                    <span class="inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
                {:else}
                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <path d="M20 6v5h-5M4 18v-5h5M6.1 9a7 7 0 0 1 11.5-2.6L20 11M4 13l2.4 4.6A7 7 0 0 0 17.9 15" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                {/if}
            </button>
        {/if}
    </div>
    {#if removedPhoto?.eventId === eventId}
        <div class="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500" role="status">
            <span>{$_('visits.photo_removed', { default: 'Photo removed from the choices.' })}</span>
            <button type="button" class="btn btn-ghost min-h-11 px-3 text-xs" bind:this={undoButton} disabled={busy} onclick={() => void undoRemoval()}>{$_('common.undo', { default: 'Undo' })}</button>
        </div>
    {/if}
    {#if removalError}<p role="alert" class="mt-2 text-sm text-slate-600 dark:text-slate-300">{$_('visits.remove_failed', { default: 'Could not change this photo choice. Try again.' })}</p>{/if}
</div>

<style>
    /*
     * The strip sits over a dark gradient on the image, where a native scrollbar is both ugly
     * and low contrast. The bar is hidden; each end that runs on is darkened by a
     * pointer-transparent fade and carries a control that scrolls it. Swiping, trackpads and the
     * keyboard scroll it as before.
     */
    .snapshot-strip {
        scrollbar-width: none;
        -ms-overflow-style: none;
    }

    .snapshot-strip::-webkit-scrollbar {
        display: none;
    }
</style>
