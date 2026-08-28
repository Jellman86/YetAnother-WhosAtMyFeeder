<script lang="ts">
    import { getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import { getTemperatureUnitForSystem, resolveWeatherUnitSystem } from '../utils/weather-units';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { portal } from '../utils/portal';

    interface Props {
        /** The clearest frame, used when a visit has only one. */
        detection: Detection;
        /** Every frame in the visit. Each one previews itself. */
        frames?: Detection[];
        frameCount?: number;
        primaryName: string;
        secondaryName?: string | null;
        onopen?: (detection: Detection) => void;
    }

    let {
        detection,
        frames = [],
        frameCount = 1,
        primaryName,
        secondaryName = null,
        onopen
    }: Props = $props();

    /**
     * Desktop shows up to this many frames; the rest are counted. Two is the cap
     * because the species name shares the row: a third thumbnail was truncating
     * names like "House Sparrow" at ordinary desktop widths, and the name is the
     * primary reading while the stack is a recognition aid.
     */
    const VISIBLE_FRAMES = 2;

    const stack = $derived(frames.length > 0 ? frames.slice(0, VISIBLE_FRAMES) : [detection]);

    // Each frame owns its preview, so hovering the second thumbnail of a visit shows the
    // second frame rather than repeating the clearest one.
    let openIndex = $state<number | null>(null);
    let rootEl = $state<HTMLElement | null>(null);
    let closeTimer: ReturnType<typeof setTimeout> | null = null;

    // A pointer travelling from the thumbnail to the panel crosses a gap; closing on the
    // first mouseleave would make the panel impossible to reach (WCAG 2.2 SC 1.4.13).
    const CLOSE_GRACE_MS = 120;

    /**
     * The panel is portalled to the body and placed in viewport coordinates.
     *
     * Positioned inside the row, it was clipped by any ancestor that hides its
     * overflow, which the Explorer's list frame does to round its corners, and
     * it could be painted under a later row's controls. Neither is fixable from
     * inside the row, so the panel leaves it.
     */
    const PANEL_WIDTH = 240;
    const GAP = 8;
    const VIEWPORT_MARGIN = 8;
    let triggers: HTMLElement[] = [];
    let anchor = $state<{ x: number; y: number; above: boolean } | null>(null);

    function place(index: number): void {
        const trigger = triggers[index];
        if (!trigger) return;
        const rect = trigger.getBoundingClientRect();
        // A row near the bottom of the window has no space beneath it, so the
        // panel flips above its thumbnail rather than running off the screen.
        const estimatedHeight = 220;
        const above = rect.bottom + GAP + estimatedHeight > window.innerHeight;
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
        if (next instanceof Node && rootEl?.contains(next)) return;
        hide(true);
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape' && openIndex !== null) {
            event.preventDefault();
            event.stopPropagation();
            hide(true);
        }
    }

    $effect(() => {
        return () => {
            if (closeTimer) clearTimeout(closeTimer);
        };
    });

    // Placed in viewport coordinates, so scrolling or resizing would leave the
    // panel behind. Closing is honest; a panel pointing at the wrong row is not.
    $effect(() => {
        if (openIndex === null) return;
        const close = () => hide(true);
        window.addEventListener('scroll', close, true);
        window.addEventListener('resize', close);
        return () => {
            window.removeEventListener('scroll', close, true);
            window.removeEventListener('resize', close);
        };
    });

    // Snapshots can disappear upstream; a missing one degrades to a placeholder of the
    // same size rather than a hole that shifts the row (CLAUDE.md §5).
    let failed = $state<Set<string>>(new Set());

    function markFailed(eventId: string): void {
        const next = new Set(failed);
        next.add(eventId);
        failed = next;
    }

    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));

    function score(frame: Detection): number {
        return Math.round((frame.score ?? 0) * 100);
    }
</script>

<div
    bind:this={rootEl}
    class="relative flex items-center"
    data-detection-preview
    onmouseleave={() => hide()}
    onfocusout={handleFocusOut}
    onkeydown={handleKeydown}
    role="presentation"
>
    {#each stack as frame, index (frame.frigate_event)}
        <div
            class="relative"
            class:-ml-1={index > 0}
            class:hidden={index > 0}
            class:sm:block={index > 0}
            onmouseenter={() => show(index)}
            onfocusin={() => show(index)}
            role="presentation"
        >
            <button
                type="button"
                bind:this={triggers[index]}
                class="grid min-h-11 min-w-11 place-items-center rounded-lg focus-ring"
                aria-expanded={openIndex === index}
                onclick={() => onopen?.(frame)}
            >
                <span class="sr-only">
                    {$_('dashboard.field_log.preview_trigger', {
                        values: { species: primaryName },
                        default: 'Preview {species}'
                    })}
                </span>
                {#if failed.has(frame.frigate_event)}
                    <span
                        class="flex h-9 w-9 items-center justify-center rounded-lg border-2 border-white bg-slate-100 text-slate-300 dark:border-slate-900 dark:bg-slate-800 dark:text-slate-600"
                        aria-hidden="true"
                    >
                        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                    </span>
                {:else}
                    <img
                        src={getThumbnailUrl(frame.frigate_event)}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        width="36"
                        height="36"
                        class="h-9 w-9 rounded-lg border-2 border-white object-cover dark:border-slate-900"
                        onerror={() => markFailed(frame.frigate_event)}
                    />
                {/if}
            </button>

            {#if openIndex === index && anchor}
                <div
                    use:portal
                    style="left: {anchor.x}px; top: {anchor.y}px;"
                    class="fixed z-[70] w-60 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 animate-in fade-in zoom-in-95 motion-reduce:animate-none dark:border-slate-700 dark:bg-slate-900 {anchor.above
                        ? '-translate-x-1/2 -translate-y-full'
                        : '-translate-x-1/2'}"
                    role="tooltip"
                    data-detection-preview-panel
                    onmouseenter={() => show(index)}
                    onmouseleave={() => hide()}
                >
                    {#if failed.has(frame.frigate_event)}
                        <div class="flex h-32 w-full items-center justify-center bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600">
                            <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                        </div>
                    {:else}
                        <img
                            src={getThumbnailUrl(frame.frigate_event)}
                            alt={$_('dashboard.field_log.preview_alt', {
                                values: { species: primaryName, camera: frame.camera_name },
                                default: '{species} on {camera}'
                            })}
                            loading="lazy"
                            decoding="async"
                            class="h-32 w-full object-cover"
                            onerror={() => markFailed(frame.frigate_event)}
                        />
                    {/if}
                    <div class="space-y-1 p-3">
                        <div class="flex items-baseline justify-between gap-2">
                            <p class="truncate font-display text-sm font-bold text-slate-950 dark:text-white">
                                {primaryName}
                            </p>
                            <span class="shrink-0 text-xs font-bold tabular-nums text-brand-700 dark:text-brand-300">
                                {score(frame)}%
                            </span>
                        </div>
                        {#if secondaryName}
                            <p class="truncate text-[11px] italic text-slate-500 dark:text-slate-400">
                                {secondaryName}
                            </p>
                        {/if}
                        <p class="text-[11px] text-slate-500 dark:text-slate-400">
                            {formatTime(frame.detection_time)} &middot; {frame.camera_name}{frame.weather_condition
                                ? ` · ${frame.weather_condition}`
                                : ''}{formatTemperature(frame.temperature, temperatureUnit)
                                ? ` ${formatTemperature(frame.temperature, temperatureUnit)}`
                                : ''}
                        </p>
                        {#if frameCount > 1}
                            <p class="text-[11px] text-slate-500 dark:text-slate-400">
                                {$_('dashboard.field_log.preview_frame_position', {
                                    values: { position: index + 1, count: frameCount },
                                    default: 'Frame {position} of {count} in this visit'
                                })}
                            </p>
                        {/if}
                    </div>
                </div>
            {/if}
        </div>
    {/each}

    {#if frameCount > 1}
        <span class="ml-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400 sm:hidden">
            +{frameCount - 1}
        </span>
    {/if}
    {#if frameCount > VISIBLE_FRAMES}
        <span class="ml-1.5 hidden text-[11px] font-semibold text-slate-500 sm:inline dark:text-slate-400">
            +{frameCount - VISIBLE_FRAMES}
        </span>
    {/if}
</div>
