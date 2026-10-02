<script lang="ts">
    import { fetchCameraStatuses } from '../api';
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
    }

    let { detections, visits, cameraVisits = null }: Props = $props();

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
                cameraStatus = await fetchCameraStatuses(controller.signal);
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
            configuredCameras: settingsStore.settings?.cameras ?? null
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
</script>

<!--
    What is running at the feeder, in one place: each camera with its last visit and the window's
    visits, then the weather the visits came in. Status is an owner reading; a guest sees the rows
    without a live dot.
-->
<section class="space-y-3" data-desk-feeder-now data-desk-cameras aria-labelledby="desk-feeder-now-title">
    <div>
        <h3 id="desk-feeder-now-title" class="flex items-center gap-2 font-display text-sm font-bold text-slate-950 dark:text-white">
            <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" />
            </svg>
            {$_('dashboard.desk.feeder_now', { default: 'At the feeder now' })}
        </h3>
        <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}</p>
    </div>

    {#if cameraRows.length === 0}
        <p class="text-xs text-slate-500 dark:text-slate-400">
            {$_('dashboard.desk.cameras_empty', {
                default: 'No cameras reporting yet. Add them in Settings → Connection.'
            })}
        </p>
    {:else}
        <ul class="divide-y divide-slate-200/70 dark:divide-slate-700/50">
            {#each cameraRows as camera (camera.name)}
                <li class="flex items-center gap-2.5 py-2 text-sm">
                    <span
                        class="h-2 w-2 shrink-0 rounded-full {camera.status === 'online'
                            ? 'bg-emerald-500'
                            : camera.status === 'offline'
                              ? 'bg-rose-500'
                              : 'bg-slate-300 dark:bg-slate-600'}"
                        aria-hidden="true"
                    ></span>
                    <span class="min-w-0 flex-1 truncate text-slate-800 dark:text-slate-100">
                        {camera.name}
                        {#if camera.status === 'offline'}
                            <span class="text-xs text-rose-700 dark:text-rose-300">· {$_('dashboard.desk.camera_offline', { default: 'offline' })}</span>
                        {/if}
                    </span>
                    {#if camera.lastSeen}
                        <span class="shrink-0 text-xs tabular-nums text-slate-500 dark:text-slate-400">{formatTime(camera.lastSeen)}</span>
                    {/if}
                    <span class="w-20 shrink-0 text-right tabular-nums text-slate-900 dark:text-white">
                        {camera.visits}
                        <span class="text-xs font-normal text-slate-500 dark:text-slate-400">
                            {camera.visits === 0
                                ? $_('dashboard.desk.camera_no_visits', { default: 'no visits' })
                                : $_('dashboard.day_bar.visits', { default: 'visits' })}
                        </span>
                    </span>
                </li>
            {/each}
        </ul>
    {/if}

    {#if conditions}
        <p class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-t border-slate-200/70 pt-2.5 text-xs text-slate-500 dark:border-slate-700/50 dark:text-slate-400" data-desk-conditions>
            <span class="font-display text-base font-bold text-slate-900 dark:text-white">
                {formatTemperature(conditions.latest.temperature, temperatureUnit)}
            </span>
            {#if conditions.latest.weather_condition}
                <span>{conditions.latest.weather_condition}</span>
            {/if}
            <span aria-hidden="true">·</span>
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
