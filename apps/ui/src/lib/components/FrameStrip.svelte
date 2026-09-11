<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { portal } from '../utils/portal';
    import {
        formatOffset,
        momentImageUrl,
        momentThumbnailUrl,
        type FrameMoment
    } from '../utils/frame-moments';

    /**
     * One ordered strip of the visit's moments (#256).
     *
     * Each thumbnail is a moment of the visit, oldest first. Hover or focus opens a pop-out
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
        canRegenerate?: boolean;
        regeneratePending?: boolean;
        onuse: (moment: FrameMoment) => void;
        onregenerate?: () => void;
    }

    let {
        moments,
        current,
        primaryName,
        loading = false,
        applyingKey = null,
        busy = false,
        asRecordedUrl = null,
        canRegenerate = false,
        regeneratePending = false,
        onuse,
        onregenerate
    }: Props = $props();

    let openIndex = $state<number | null>(null);
    let rootEl = $state<HTMLElement | null>(null);
    let triggers: HTMLElement[] = [];
    let closeTimer: ReturnType<typeof setTimeout> | null = null;

    // A pointer travelling from the thumbnail up into the panel crosses a gap; closing on the
    // first mouseleave would make the panel impossible to reach (WCAG 2.2 SC 1.4.13).
    const CLOSE_GRACE_MS = 120;
    const PANEL_WIDTH = 288;
    const PANEL_ESTIMATED_HEIGHT = 320;
    const GAP = 8;
    const VIEWPORT_MARGIN = 8;

    let anchor = $state<{ x: number; y: number; above: boolean } | null>(null);

    function place(index: number): void {
        const trigger = triggers[index];
        if (!trigger) return;
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
        anchor = { x: centre, y: above ? rect.top - GAP : rect.bottom + GAP, above };
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
        if (next instanceof Node && (rootEl?.contains(next) || panelEl?.contains(next))) return;
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
        if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
        event.preventDefault();
        if (openIndex !== index) show(index);
        queueMicrotask(() => panelEl?.querySelector<HTMLElement>('button, [tabindex]')?.focus());
    }

    function handlePanelKeydown(event: KeyboardEvent): void {
        if (event.key === 'Tab' || event.key === 'Escape') {
            event.preventDefault();
            event.stopPropagation();
            const index = openIndex;
            if (event.key === 'Escape') hide(true);
            if (index !== null) triggers[index]?.focus();
        }
    }

    let panelEl = $state<HTMLElement | null>(null);

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
        window.addEventListener('scroll', follow, true);
        window.addEventListener('resize', follow);
        return () => {
            if (pending !== null) cancelAnimationFrame(pending);
            window.removeEventListener('scroll', follow, true);
            window.removeEventListener('resize', follow);
        };
    });

    // A moment that disappears (regeneration replaced the list) must not leave a panel open
    // over nothing.
    $effect(() => {
        if (openIndex !== null && openIndex >= moments.length) {
            openIndex = null;
        }
    });

    /**
     * Shows the strip's trailing hint only while it actually overflows. The hint is a separate,
     * pointer-transparent layer so desktop browsers never hit-test through a CSS mask.
     * Thumbnails load lazily, so image loads are watched as well as resizes.
     */
    function watchOverflow(node: HTMLElement) {
        const shell = node.closest<HTMLElement>('[data-snapshot-strip-shell]');
        const update = () => {
            const hasMoreToRight = node.scrollLeft + node.clientWidth < node.scrollWidth - 1;
            shell?.style.setProperty('--strip-fade-opacity', hasMoreToRight ? '1' : '0');
        };
        update();
        const resize = new ResizeObserver(update);
        resize.observe(node);
        // The container keeps its size when the moment list changes, so a resize alone would
        // leave the fade describing a strip that is no longer there.
        const mutation = new MutationObserver(update);
        mutation.observe(node, { childList: true });
        node.addEventListener('load', update, true);
        node.addEventListener('scroll', update, { passive: true });
        return {
            destroy() {
                resize.disconnect();
                mutation.disconnect();
                shell?.style.removeProperty('--strip-fade-opacity');
                node.removeEventListener('load', update, true);
                node.removeEventListener('scroll', update);
            }
        };
    }

    // A thumbnail that fails to load degrades to a same-size placeholder, never a hole.
    let failed = $state<Set<string>>(new Set());
    function markFailed(key: string): void {
        const next = new Set(failed);
        next.add(key);
        failed = next;
    }

    function thumbnailFor(moment: FrameMoment): string | null {
        return moment.asRecorded ? asRecordedUrl : momentThumbnailUrl(moment);
    }

    function imageFor(moment: FrameMoment): string | null {
        return moment.asRecorded ? asRecordedUrl : momentImageUrl(moment);
    }

    function framingLabel(moment: FrameMoment): string {
        if (moment.asRecorded) {
            return $_('detection.snapshot_framing_as_recorded', { default: 'As Frigate recorded it' });
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
</script>

<div
    bind:this={rootEl}
    class="flex flex-col gap-1 px-3 pb-3"
    data-frame-strip
    aria-busy={loading || busy}
    onmouseleave={() => hide()}
    onfocusout={handleFocusOut}
    onkeydown={handleKeydown}
    role="presentation"
>
    <div class="flex min-h-4 items-center justify-between gap-2 px-1 text-[10px] font-semibold text-white/65" aria-live="polite">
        <span>
            {#if loading}
                {$_('detection.snapshot_candidates_loading', { default: 'Loading frames...' })}
            {:else if moments.length === 0}
                {$_('detection.frame_strip_empty', { default: 'No frames kept from this visit yet.' })}
            {:else if moments.length === 1}
                {$_('detection.frame_strip_count_one', { default: '1 frame from this visit' })}
            {:else}
                {$_('detection.frame_strip_count', {
                    values: { count: moments.length },
                    default: '{count} frames from this visit'
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
            <div class="snapshot-strip -my-2 flex min-w-0 gap-1.5 overflow-x-auto px-1 py-3" use:watchOverflow>
                {#each moments as moment, index (moment.key)}
                    {@const chosen = isCurrent(moment)}
                    {@const thumb = thumbnailFor(moment)}
                    <div
                        class="relative shrink-0"
                        onmouseenter={() => show(index)}
                        onfocusin={() => show(index)}
                        role="presentation"
                    >
                        <button
                            type="button"
                            bind:this={triggers[index]}
                            class="relative min-h-11 min-w-11 shrink-0 rounded-md p-1 transition duration-200 ease-out motion-reduce:transform-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 {chosen
                                ? 'z-10 -translate-y-1 scale-105 bg-white/15 opacity-100 shadow-lg shadow-black/50'
                                : 'opacity-80 hover:opacity-100'}"
                            aria-pressed={chosen}
                            aria-expanded={openIndex === index}
                            aria-label={$_('detection.frame_compare', {
                                values: { position: moment.position, count: moments.length },
                                default: 'Compare frame {position} of {count}'
                            })}
                            onclick={(event) => { event.stopPropagation(); show(index); }}
                            onkeydown={(event) => handleTriggerKeydown(event, index)}
                        >
                            {#if thumb && !failed.has(moment.key)}
                                <img
                                    src={thumb}
                                    alt=""
                                    loading="lazy"
                                    decoding="async"
                                    width="48"
                                    height="36"
                                    class="h-9 w-12 rounded-md object-cover"
                                    onerror={() => markFailed(moment.key)}
                                />
                            {:else}
                                <span class="flex h-9 w-12 items-center justify-center rounded-md bg-slate-800 text-slate-500" aria-hidden="true">
                                    <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                    </svg>
                                </span>
                            {/if}
                            {#if chosen}
                                <span class="pointer-events-none absolute bottom-1.5 left-1.5 rounded bg-brand-500 px-1 text-[9px] font-bold leading-4 text-slate-950">
                                    {$_('detection.frame_chosen_badge', { default: 'Chosen' })}
                                </span>
                            {/if}
                        </button>

                        {#if openIndex === index && anchor}
                            {@const image = imageFor(moment)}
                            {@const read = readLine(moment)}
                            {@const applying = applyingKey === moment.key}
                            <div
                                bind:this={panelEl}
                                use:portal
                                style="left: {anchor.x}px; top: {anchor.y}px;"
                                class="fixed z-[70] w-72 max-w-[calc(100vw-16px)] overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 text-slate-100 shadow-2xl shadow-slate-950/40 motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-95 {anchor.above
                                    ? '-translate-x-1/2 -translate-y-full'
                                    : '-translate-x-1/2'}"
                                role="presentation"
                                data-frame-strip-panel
                                onmouseenter={cancelScheduledClose}
                                onmouseleave={() => hide()}
                                onfocusout={handleFocusOut}
                                onkeydown={handlePanelKeydown}
                            >
                              <div
                                role="group"
                                aria-label={$_('detection.frame_position', {
                                    values: { position: moment.position, count: moments.length },
                                    default: 'Frame {position} of {count}'
                                })}
                              >
                                {#if image && !failed.has(moment.key)}
                                    <img
                                        src={image}
                                        alt={primaryName}
                                        loading="lazy"
                                        decoding="async"
                                        class="h-40 w-full bg-slate-950 object-contain"
                                        onerror={() => markFailed(moment.key)}
                                    />
                                {:else}
                                    <div class="flex h-40 w-full items-center justify-center bg-slate-950 text-slate-600" aria-hidden="true">
                                        <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                        </svg>
                                    </div>
                                {/if}
                                <div class="flex flex-col gap-1.5 p-3 text-[13px]">
                                    <div class="flex items-baseline justify-between gap-2">
                                        <span class="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                                            {$_('detection.frame_position', {
                                                values: { position: moment.position, count: moments.length },
                                                default: 'Frame {position} of {count}'
                                            })}
                                            &middot; {framingLabel(moment)}
                                        </span>
                                        {#if formatOffset(moment.offsetSeconds)}
                                            <span class="shrink-0 text-xs tabular-nums text-slate-400">{formatOffset(moment.offsetSeconds)}</span>
                                        {/if}
                                    </div>
                                    {#if read}
                                        <div class="flex items-baseline justify-between gap-2">
                                            <span class="text-slate-400">{$_('detection.frame_model_read', { default: 'Model reads this frame as' })}</span>
                                            <span class="shrink-0 font-semibold text-white">{read}</span>
                                        </div>
                                        <p class="text-xs text-slate-500">
                                            {$_('detection.frame_read_note', {
                                                default: 'A read of one frame. The identification stays until you change it.'
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
                                            onclick={(event) => { event.stopPropagation(); onuse(moment); }}
                                        >
                                            {#if applying}
                                                <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true"></span>
                                            {/if}
                                            {$_('detection.frame_use', { default: 'Use this frame' })}
                                        </button>
                                    {/if}
                                </div>
                              </div>
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
            <div
                class="snapshot-strip-fade pointer-events-none absolute inset-y-2 right-0 w-14 bg-gradient-to-r from-transparent to-slate-950/80 transition-opacity duration-150 motion-reduce:transition-none"
                data-snapshot-strip-fade
                aria-hidden="true"
            ></div>
        </div>
        {#if canRegenerate && onregenerate}
            <button
                type="button"
                class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-brand-300/35 bg-brand-500/15 text-brand-100 transition-colors hover:bg-brand-500/25 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                disabled={regeneratePending || busy}
                title={$_('detection.snapshot_regenerate', { default: 'Regenerate snapshots' })}
                aria-label={$_('detection.snapshot_regenerate', { default: 'Regenerate snapshots' })}
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
</div>

<style>
    /*
     * The strip sits over a dark gradient on the image, where a native scrollbar is both ugly
     * and low contrast. The bar is hidden and a pointer-transparent sibling darkens the right
     * edge instead, so there is still a signal that more frames exist without blocking selection.
     * Scrolling by wheel, trackpad and keyboard is unaffected.
     */
    .snapshot-strip {
        scrollbar-width: none;
        -ms-overflow-style: none;
    }

    .snapshot-strip::-webkit-scrollbar {
        display: none;
    }

    .snapshot-strip-fade {
        opacity: var(--strip-fade-opacity, 0);
    }
</style>
