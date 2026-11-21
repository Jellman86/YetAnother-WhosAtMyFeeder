<script lang="ts">
    import { weatherConditionMessage } from '../utils/weather-condition';
    import Separator from './Separator.svelte';
    import { readCameraStatuses } from '../api';
    import type { CameraStatusResponse, Detection } from '../api';
    import type { DetectionVisit } from '../utils/visit-grouping';
    import { buildDashboardCameraRows } from '../utils/dashboard-cameras';
    import { formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import { getTemperatureUnitForSystem, resolveWeatherUnitSystem } from '../utils/weather-units';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { _ } from 'svelte-i18n';

    interface Props {
        /** The detections the log is showing, newest first. */
        detections: Detection[];
        visits: DetectionVisit[];
        /** The day summary's visits per camera, for the whole window; null for a guest who may not see camera names. */
        cameraVisits?: Array<{ camera: string; visits: number; last_seen?: string | null }> | null;
        /** The day is still being read: camera names may be known, their visits are not. */
        loading?: boolean;
        /** The day could not be read, so visit counts stay unknown rather than zero. */
        unavailable?: boolean;
    }

    let { detections, visits, cameraVisits = null, loading = false, unavailable = false }: Props = $props();

    let cameraStatus = $state<CameraStatusResponse | null>(null);
    let cameraRequested = false;

    // Camera status is an owner reading: a guest request only collects a 403, and
    // the desk already builds its camera rows from the visits a guest can see.
    $effect(() => {
        if (!authStore.hasOwnerAccess || cameraRequested) return;
        cameraRequested = true;
        const controller = new AbortController();

        void (async () => {
            try {
                cameraStatus = await readCameraStatuses(controller.signal);
            } catch (error) {
                if (controller.signal.aborted) return;
                // Camera health is supporting context; the desk stays usable without it.
                if (isTransientRequestError(error)) {
                    logger.warn('Camera status unavailable', { message: getErrorMessage(error) });
                } else {
                    logger.error('Failed to fetch camera status', error);
                }
            }
        })();

        return () => controller.abort();
    });

    const cameraRows = $derived(
        buildDashboardCameraRows({
            cameraStatus,
            visits,
            cameraVisits,
            configuredCameras: settingsStore.settings?.cameras ?? null,
            countsMeasured: !loading && !unavailable
        })
    );

    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));

    const conditions = $derived.by(() => {
        const latest = detections.find(
            (detection) => detection.temperature !== undefined && detection.temperature !== null
        );
        const temperatures = detections
            .map((detection) => detection.temperature)
            .filter((value): value is number => value !== undefined && value !== null);

        if (!latest || temperatures.length === 0) return null;

        return {
            latest,
            low: Math.min(...temperatures),
            high: Math.max(...temperatures)
        };
    });

    // The stored condition is the backend's English word; the reader gets it in their language.
    function conditionText(stored: string | null | undefined): string {
        const message = weatherConditionMessage(stored);
        if (!message) return '';
        return message.key ? $_(message.key, { default: message.default }) : message.default;
    }
</script>

<!--
    What is running at the feeder, in one place: each camera with its last visit and the window's
    visits, then the weather the visits came in. Status is an owner reading; a guest sees the rows
    without a live dot.
-->
<section class="panel space-y-4" data-desk-feeder-now data-desk-cameras aria-labelledby="desk-feeder-now-title">
    <div>
        <h2 id="desk-feeder-now-title" class="flex items-center gap-2 font-display text-xl font-bold text-strong">
            <svg class="h-5 w-5 text-accent-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" />
            </svg>
            {$_('dashboard.desk.feeder_now', { default: 'At the feeder now' })}
        </h2>
        <p class="mt-0.5 text-sm text-muted">{$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}</p>
    </div>

    {#if loading}
        <p role="status" class="sr-only">{$_('dashboard.desk.cameras_loading', { default: 'Loading camera visits…' })}</p>
    {/if}
    {#if cameraRows.length === 0 && loading}
        <ul class="divide-y divide-line" aria-hidden="true">
            {#each ['w-20', 'w-16'] as width (width)}
                <li class="flex h-9 items-center gap-2.5 py-2">
                    <span class="h-2 w-2 shrink-0 rounded-full bg-line"></span>
                    <span class="h-3 rounded-sm bg-line animate-pulse motion-reduce:animate-none {width}" data-loading-placeholder></span>
                    <span class="ml-auto h-3 w-12 rounded-sm bg-line animate-pulse motion-reduce:animate-none" data-loading-placeholder></span>
                </li>
            {/each}
        </ul>
    {:else if cameraRows.length === 0 && unavailable}
        <p class="text-xs text-muted" data-desk-camera-visits-unavailable>
            {$_('dashboard.desk.camera_visits_unavailable', { default: 'Visit counts could not be loaded.' })}
        </p>
    {:else if cameraRows.length === 0}
        <p class="text-xs text-muted">
            {$_('dashboard.desk.cameras_empty', {
                default: 'No cameras reporting yet. Add them in Settings → Connection.'
            })}
        </p>
    {:else}
        <ul class="divide-y divide-line">
            {#each cameraRows as camera (camera.name)}
                <li class="flex flex-wrap items-center gap-x-2.5 gap-y-1 py-2 text-sm" data-desk-camera={camera.name}>
                    <span
                        class="h-2 w-2 shrink-0 rounded-full {camera.status === 'online'
                            ? 'bg-status-ok-line'
                            : camera.status === 'offline'
                              ? 'bg-status-fail-line'
                              : 'bg-line'}"
                        aria-hidden="true"
                    ></span>
                    <span class="min-w-0 flex-1 wrap-break-word text-strong">
                        {camera.name}
                        {#if camera.status === 'offline'}
                            <span class="text-xs text-status-fail">· {$_('dashboard.desk.camera_offline', { default: 'offline' })}</span>
                        {/if}
                    </span>
                    {#if camera.lastSeen}
                        <span class="shrink-0 text-xs tabular-nums text-muted">{formatTime(camera.lastSeen)}</span>
                    {/if}
                    <span class="ml-auto min-w-20 shrink-0 text-right tabular-nums text-strong">
                        {#if camera.visits === null && loading}
                            <span class="ml-auto inline-block h-3 w-12 translate-y-0.5 rounded-sm bg-line animate-pulse motion-reduce:animate-none" aria-hidden="true" data-loading-placeholder></span>
                        {:else if camera.visits === null}
                            <span aria-hidden="true">–</span>
                            <span class="sr-only">{$_('dashboard.day_bar.unavailable', { default: 'not available' })}</span>
                        {:else}
                            {camera.visits}
                            <span class="text-xs font-normal text-muted">
                                {camera.visits === 0
                                    ? $_('dashboard.desk.camera_no_visits', { default: 'no visits' })
                                    : $_('dashboard.desk.camera_visits_unit', {
                                          values: { count: camera.visits },
                                          default: '{count, plural, one {visit} other {visits}}'
                                      })}
                            </span>
                        {/if}
                    </span>
                </li>
            {/each}
        </ul>
        {#if unavailable}
            <p class="text-xs text-muted" data-desk-camera-visits-unavailable>
                {$_('dashboard.desk.camera_visits_unavailable', { default: 'Visit counts could not be loaded.' })}
            </p>
        {/if}
    {/if}

    {#if conditions}
        <p class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-t border-line pt-2.5 text-xs text-muted" data-desk-conditions>
            <span class="font-display text-base font-bold text-strong">
                {formatTemperature(conditions.latest.temperature, temperatureUnit)}
            </span>
            {#if conditionText(conditions.latest.weather_condition)}
                <span>{conditionText(conditions.latest.weather_condition)}</span>
            {/if}
            <Separator />
            <span>
                {$_('dashboard.desk.temperature_span', {
                    values: {
                        low: formatTemperature(conditions.low, temperatureUnit),
                        high: formatTemperature(conditions.high, temperatureUnit)
                    },
                    default: 'Visits ranged {low} to {high}'
                })}
            </span>
        </p>
    {/if}
</section>
