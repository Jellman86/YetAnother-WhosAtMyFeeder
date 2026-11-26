<script lang="ts">
    import { weatherConditionMessage } from '../utils/weather-condition';
    import { getThumbnailUrl } from '../api';
    import type { Detection } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import { getTemperatureUnitForSystem, resolveWeatherUnitSystem } from '../utils/weather-units';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { HoverPopout } from '../utils/hover-popout.svelte';
    import HoverPopoutPanel from './HoverPopoutPanel.svelte';
    import { SCORE_TEXT, scoreBand } from '../utils/score-tone';

    interface Props {
        /** The clearest frame, used when a visit has only one. */
        detection: Detection;
        /** Every frame in the visit. Each one previews itself. */
        frames?: Detection[];
        frameCount?: number;
        primaryName: string;
        secondaryName?: string | null;
        onopen?: (detection: Detection) => void;
        /** False renders the thumbnails as decoration: no tab stop, no click.
         * The Explorer's selection mode owns every activation through the
         * row overlay, which is labelled for selecting, not previewing. */
        interactive?: boolean;
        /** What activating the thumbnail does, when it is more specific than previewing the species. */
        label?: string | null;
        /** Off where the surrounding row already states the capture count in words. */
        showCount?: boolean;
    }

    let {
        detection,
        frames = [],
        frameCount = 1,
        primaryName,
        secondaryName = null,
        onopen,
        interactive = true,
        label = null,
        showCount = true
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
    const uid = $props.id();
    const popout = new HoverPopout(uid);

    function thumbnailUrl(frame: Detection): string {
        return getThumbnailUrl(frame.frigate_event, detectionsStore.settledMediaVersion(frame.frigate_event));
    }

    // Snapshots can disappear upstream; a missing one degrades to a placeholder of the
    // same size rather than a hole that shifts the row (CLAUDE.md §5). Failures are kept per
    // address, so a photograph saved by a later run is tried.
    let failed = $state<Set<string>>(new Set());

    function markFailed(url: string | null): void {
        if (!url) return;
        const next = new Set(failed);
        next.add(url);
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

    // The stored condition is the backend's English word; the reader gets it in their language.
    function conditionText(stored: string | null | undefined): string {
        const message = weatherConditionMessage(stored);
        if (!message) return '';
        return message.key ? $_(message.key, { default: message.default }) : message.default;
    }
</script>

<div
    bind:this={popout.root}
    class="relative flex items-center"
    data-detection-preview
    onmouseleave={() => popout.hide()}
    onfocusout={popout.focusOut}
    onkeydown={popout.keydown}
    role="presentation"
>
    {#each stack as frame, index (frame.frigate_event)}
        <div
            class="relative"
            class:-ml-1={index > 0}
            class:hidden={index > 0}
            class:sm:block={index > 0}
            onpointerenter={(event) => popout.pointerEnter(event, index)}
            onfocusin={(event) => popout.focusIn(event, index)}
            role="presentation"
        >
            {#snippet thumbnail(frame: Detection)}
                {#if failed.has(thumbnailUrl(frame))}
                    <span
                        class="flex h-9 w-9 items-center justify-center rounded-lg border-2 border-surface bg-surface-raised text-subtle"
                        aria-hidden="true"
                    >
                        <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                    </span>
                {:else}
                    <img
                        src={thumbnailUrl(frame)}
                        alt=""
                        loading="lazy"
                        decoding="async"
                        width="36"
                        height="36"
                        class="h-9 w-9 rounded-lg border-2 border-surface bg-surface-raised object-cover"
                        onerror={(event) => markFailed(event.currentTarget.getAttribute('src'))}
                    />
                {/if}
            {/snippet}

            {#if interactive}
                <button
                    type="button"
                    bind:this={popout.triggers[index]}
                    aria-describedby={popout.describedBy(index)}
                    class="grid min-h-11 min-w-11 place-items-center rounded-lg focus-ring"
                    onclick={() => onopen?.(frame)}
                >
                    <span class="sr-only">
                        {label ?? $_('dashboard.field_log.preview_trigger', {
                            values: { species: primaryName },
                            default: 'Preview {species}'
                        })}
                    </span>
                    {@render thumbnail(frame)}
                </button>
            {:else}
                <span bind:this={popout.triggers[index]} class="grid min-h-11 min-w-11 place-items-center rounded-lg" aria-hidden="true">
                    {@render thumbnail(frame)}
                </span>
            {/if}

            {#if popout.openIndex === index}
                <HoverPopoutPanel {popout} {index} data-detection-preview-panel>
                    {#if failed.has(thumbnailUrl(frame))}
                        <div class="flex h-32 w-full items-center justify-center bg-surface-raised text-subtle">
                            <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                        </div>
                    {:else}
                        <img
                            src={thumbnailUrl(frame)}
                            alt={$_('dashboard.field_log.preview_alt', {
                                values: { species: primaryName, camera: frame.camera_name },
                                default: '{species} on {camera}'
                            })}
                            loading="lazy"
                            decoding="async"
                            class="h-32 w-full bg-surface-raised object-cover"
                            onerror={(event) => markFailed(event.currentTarget.getAttribute('src'))}
                        />
                    {/if}
                    <div class="space-y-1 p-3">
                        <div class="flex items-baseline justify-between gap-2">
                            <p class="min-w-0 wrap-break-word font-display text-sm font-bold text-strong">
                                {primaryName}
                            </p>
                            <span class="shrink-0 text-xs font-bold tabular-nums {SCORE_TEXT[scoreBand(frame.score)]}" data-preview-score>
                                {score(frame)}%
                            </span>
                        </div>
                        {#if secondaryName}
                            <p class="wrap-break-word text-2xs italic text-muted">
                                {secondaryName}
                            </p>
                        {/if}
                        <p class="text-2xs text-muted">
                            {formatTime(frame.detection_time)} &middot; {frame.camera_name}{conditionText(frame.weather_condition)
                                ? ` · ${conditionText(frame.weather_condition)}`
                                : ''}{formatTemperature(frame.temperature, temperatureUnit)
                                ? ` ${formatTemperature(frame.temperature, temperatureUnit)}`
                                : ''}
                        </p>
                        {#if frameCount > 1}
                            <p class="text-2xs text-muted">
                                {$_('dashboard.field_log.preview_frame_position', {
                                    values: { position: index + 1, count: frameCount },
                                    default: 'Frame {position} of {count} in this visit'
                                })}
                            </p>
                        {/if}
                    </div>
                </HoverPopoutPanel>
            {/if}
        </div>
    {/each}

    {#if showCount && frameCount > 1}
        <span class="ml-1.5 text-2xs font-semibold text-muted sm:hidden">
            +{frameCount - 1}
        </span>
    {/if}
    {#if showCount && frameCount > VISIBLE_FRAMES}
        <span class="ml-1.5 hidden text-2xs font-semibold text-muted sm:inline">
            +{frameCount - VISIBLE_FRAMES}
        </span>
    {/if}
</div>
