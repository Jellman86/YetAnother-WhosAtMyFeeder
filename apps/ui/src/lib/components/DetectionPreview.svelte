<script lang="ts">
    import { getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import { getTemperatureUnitForSystem, resolveWeatherUnitSystem } from '../utils/weather-units';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';

    interface Props {
        /** The frame worth showing: the clearest one in the visit. */
        detection: Detection;
        /** Up to three frames from the visit, drawn as a stack. */
        frames?: Detection[];
        /** Frames folded into the visit, including any beyond the stack. */
        frameCount?: number;
        primaryName: string;
        secondaryName?: string | null;
        onopen?: () => void;
    }

    let {
        detection,
        frames = [],
        frameCount = 1,
        primaryName,
        secondaryName = null,
        onopen
    }: Props = $props();

    const stack = $derived(frames.length > 0 ? frames.slice(0, 3) : [detection]);

    // Snapshots can disappear upstream; a missing one must degrade to a placeholder of
    // the same size rather than leaving a hole that shifts the row (CLAUDE.md §5).
    let failedThumbnails = $state<Set<string>>(new Set());
    let panelImageFailed = $state(false);

    function markFailed(eventId: string): void {
        const next = new Set(failedThumbnails);
        next.add(eventId);
        failedThumbnails = next;
    }

    let open = $state(false);
    let rootEl = $state<HTMLElement | null>(null);
    let closeTimer: ReturnType<typeof setTimeout> | null = null;

    // A pointer travelling from the thumbnail to the panel crosses a gap; closing on the
    // first mouseleave would make the panel impossible to reach (WCAG 2.2 SC 1.4.13).
    const CLOSE_GRACE_MS = 120;

    function show(): void {
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        open = true;
    }

    function hide(immediate = false): void {
        if (closeTimer) clearTimeout(closeTimer);
        if (immediate) {
            closeTimer = null;
            open = false;
            return;
        }
        closeTimer = setTimeout(() => {
            open = false;
            closeTimer = null;
        }, CLOSE_GRACE_MS);
    }

    function handleFocusOut(event: FocusEvent): void {
        const next = event.relatedTarget;
        if (next instanceof Node && rootEl?.contains(next)) return;
        hide(true);
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape' && open) {
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

    const score = $derived(Math.round((detection.score ?? 0) * 100));
    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperature = $derived(
        formatTemperature(detection.temperature, getTemperatureUnitForSystem(weatherUnitSystem))
    );
</script>

<div
    bind:this={rootEl}
    class="relative"
    data-detection-preview
    onmouseenter={show}
    onmouseleave={() => hide()}
    onfocusin={show}
    onfocusout={handleFocusOut}
    onkeydown={handleKeydown}
    role="presentation"
>
    <button
        type="button"
        class="flex items-center rounded-xl focus-ring"
        aria-expanded={open}
        onclick={() => onopen?.()}
    >
        <span class="sr-only">
            {$_('dashboard.field_log.preview_trigger', {
                values: { species: primaryName },
                default: 'Preview {species}'
            })}
        </span>
        {#each stack as frame, index (frame.frigate_event)}
            {#if failedThumbnails.has(frame.frigate_event)}
                <span
                    class="flex h-9 w-9 items-center justify-center rounded-lg border-2 border-white bg-slate-100 text-slate-300 dark:border-slate-900 dark:bg-slate-800 dark:text-slate-600"
                    class:-ml-2={index > 0}
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
                    class:-ml-2={index > 0}
                    onerror={() => markFailed(frame.frigate_event)}
                />
            {/if}
        {/each}
        {#if frameCount > 3}
            <span class="ml-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                +{frameCount - 3}
            </span>
        {/if}
    </button>

    {#if open}
        <div
            class="absolute left-1/2 top-full z-30 mt-2 w-60 -translate-x-1/2 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl shadow-slate-950/20 animate-in fade-in zoom-in-95 motion-reduce:animate-none dark:border-slate-700 dark:bg-slate-900"
            role="tooltip"
            data-detection-preview-panel
        >
            {#if panelImageFailed}
                <div class="flex h-32 w-full items-center justify-center bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600">
                    <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                </div>
            {:else}
                <img
                    src={getThumbnailUrl(detection.frigate_event)}
                    alt={$_('dashboard.field_log.preview_alt', {
                        values: { species: primaryName, camera: detection.camera_name },
                        default: '{species} on {camera}'
                    })}
                    loading="lazy"
                    decoding="async"
                    class="h-32 w-full object-cover"
                    onerror={() => (panelImageFailed = true)}
                />
            {/if}
            <div class="space-y-1 p-3">
                <div class="flex items-baseline justify-between gap-2">
                    <p class="truncate font-display text-sm font-bold text-slate-950 dark:text-white">
                        {primaryName}
                    </p>
                    <span class="shrink-0 text-xs font-bold tabular-nums text-brand-700 dark:text-brand-300">
                        {score}%
                    </span>
                </div>
                {#if secondaryName}
                    <p class="truncate text-[11px] italic text-slate-500 dark:text-slate-400">
                        {secondaryName}
                    </p>
                {/if}
                <p class="text-[11px] text-slate-500 dark:text-slate-400">
                    {formatTime(detection.detection_time)} · {detection.camera_name}{detection.weather_condition
                        ? ` · ${detection.weather_condition}`
                        : ''}{temperature ? ` ${temperature}` : ''}
                </p>
                {#if frameCount > 1}
                    <p class="text-[11px] text-slate-500 dark:text-slate-400">
                        {$_('dashboard.field_log.preview_frames', {
                            values: { count: frameCount },
                            default: '{count} frames in this visit, clearest shown'
                        })}
                    </p>
                {/if}
            </div>
        </div>
    {/if}
</div>
