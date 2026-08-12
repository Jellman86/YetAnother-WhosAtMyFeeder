<script lang="ts">
    import { onMount } from 'svelte';
    import { fetchCameraStatuses } from '../api';
    import type { AudioSummaryResponse, CameraStatusResponse, Detection } from '../api';
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
        birdnetEnabled?: boolean;
        /** Fetched once by the page and shared with the day bar. */
        audioSummary?: AudioSummaryResponse | null;
    }

    let { detections, birdnetEnabled = false, audioSummary = null }: Props = $props();

    let cameraStatus = $state<CameraStatusResponse | null>(null);

    onMount(() => {
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

    interface CameraRow {
        name: string;
        visits: number;
        status: 'online' | 'offline' | 'unknown';
        /** The most recent visit, so a quiet camera is visibly quiet. */
        lastSeen: string | null;
    }

    const cameraRows = $derived.by<CameraRow[]>(() => {
        const visitsByCamera = new Map<string, number>();
        const lastSeenByCamera = new Map<string, string>();
        for (const detection of detections) {
            const camera = detection.camera_name;
            if (!camera) continue;
            visitsByCamera.set(camera, (visitsByCamera.get(camera) ?? 0) + 1);
            const seen = lastSeenByCamera.get(camera);
            if (!seen || detection.detection_time > seen) {
                lastSeenByCamera.set(camera, detection.detection_time);
            }
        }

        const known = cameraStatus?.cameras ?? [];
        const rows: CameraRow[] = known.map((camera) => ({
            name: camera.camera,
            visits: visitsByCamera.get(camera.camera) ?? 0,
            status: camera.status,
            lastSeen: lastSeenByCamera.get(camera.camera) ?? null
        }));

        // A camera that produced detections but is missing from the status list still belongs here.
        for (const [name, visits] of visitsByCamera) {
            if (!rows.some((row) => row.name === name)) {
                rows.push({
                    name,
                    visits,
                    status: 'unknown',
                    lastSeen: lastSeenByCamera.get(name) ?? null
                });
            }
        }

        return rows.sort((left, right) => right.visits - left.visits || left.name.localeCompare(right.name));
    });

    const crossConfirmed = $derived(
        detections.reduce((total, detection) => total + (detection.audio_confirmed ? 1 : 0), 0)
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

<section class="space-y-3" data-desk-cameras aria-labelledby="desk-cameras-title">
    <h3 id="desk-cameras-title" class="flex items-center gap-2 font-display text-sm font-bold text-slate-950 dark:text-white">
        <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" />
            <path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" />
        </svg>
        {$_('dashboard.desk.cameras', { default: 'Cameras' })}
    </h3>

    {#if cameraRows.length === 0}
        <p class="text-xs text-slate-500 dark:text-slate-400">
            {$_('dashboard.desk.cameras_empty', {
                default: 'No cameras reporting yet. Add them in Settings → Connection.'
            })}
        </p>
    {:else}
        <ul class="divide-y divide-slate-200/70 dark:divide-slate-700/50">
            {#each cameraRows as camera (camera.name)}
                <li class="flex items-center gap-2 py-1.5 text-xs">
                    <span
                        class="h-1.5 w-1.5 shrink-0 rounded-full {camera.status === 'online'
                            ? 'bg-emerald-500'
                            : camera.status === 'offline'
                              ? 'bg-rose-500'
                              : 'bg-slate-400 dark:bg-slate-500'}"
                        aria-hidden="true"
                    ></span>
                    <span class="min-w-0 flex-1 truncate text-slate-700 dark:text-slate-200">{camera.name}</span>
                    {#if camera.lastSeen}
                        <span class="shrink-0 text-[11px] text-slate-500 dark:text-slate-400">
                            {formatTime(camera.lastSeen)}
                        </span>
                    {/if}
                    <span class="shrink-0 tabular-nums text-slate-900 dark:text-white">
                        {camera.visits}
                        <span class="text-[11px] font-normal text-slate-500 dark:text-slate-400">
                            {camera.visits === 0
                                ? $_('dashboard.desk.camera_no_visits', { default: 'no visits' })
                                : $_('dashboard.day_bar.visits', { default: 'visits' })}
                        </span>
                    </span>
                </li>
            {/each}
        </ul>
    {/if}
</section>

{#if birdnetEnabled}
    <section class="space-y-3" data-desk-sensors aria-labelledby="desk-sensors-title">
        <h3 id="desk-sensors-title" class="flex items-center gap-2 font-display text-sm font-bold text-slate-950 dark:text-white">
            <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path stroke-linecap="round" d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
            {$_('dashboard.desk.sensors', { default: 'Audio vs camera' })}
        </h3>

        <dl class="flex gap-5">
            <div>
                <dd class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white">
                    {audioSummary?.total ?? '—'}
                </dd>
                <dt class="text-[11px] text-slate-500 dark:text-slate-400">
                    {$_('dashboard.desk.heard', { default: 'heard' })}
                </dt>
            </div>
            <div>
                <dd class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white">
                    {detections.length}
                </dd>
                <dt class="text-[11px] text-slate-500 dark:text-slate-400">
                    {$_('dashboard.desk.seen', { default: 'seen' })}
                </dt>
            </div>
            <div>
                <dd
                    class="font-display text-lg font-bold tabular-nums {crossConfirmed === 0
                        ? 'text-accent-700 dark:text-accent-300'
                        : 'text-slate-900 dark:text-white'}"
                >
                    {crossConfirmed}
                </dd>
                <dt class="text-[11px] text-slate-500 dark:text-slate-400">
                    {$_('dashboard.desk.both', { default: 'both' })}
                </dt>
            </div>
        </dl>

        {#if audioSummary && crossConfirmed === 0 && audioSummary.total > 0}
            <p class="rounded-lg bg-accent-50 px-2.5 py-2 text-[11px] leading-relaxed text-accent-800 dark:bg-accent-950/40 dark:text-accent-200">
                {$_('dashboard.desk.no_cross_confirmation', {
                    values: { count: audioSummary.total },
                    default:
                        '{count} calls were heard but none lined up with a camera visit. The microphone and the cameras may be covering different ground.'
                })}
            </p>
        {/if}
    </section>
{/if}

{#if conditions}
    <section class="space-y-2" data-desk-conditions aria-labelledby="desk-conditions-title">
        <h3 id="desk-conditions-title" class="font-display text-sm font-bold text-slate-950 dark:text-white">
            {$_('dashboard.desk.conditions', { default: 'Conditions' })}
        </h3>
        <p class="flex items-baseline gap-2">
            <span class="font-display text-xl font-bold text-slate-900 dark:text-white">
                {formatTemperature(conditions.latest.temperature, temperatureUnit)}
            </span>
            {#if conditions.latest.weather_condition}
                <span class="text-xs text-slate-500 dark:text-slate-400">
                    {conditions.latest.weather_condition}
                </span>
            {/if}
        </p>
        <p class="text-[11px] text-slate-500 dark:text-slate-400">
            {$_('dashboard.desk.temperature_span', {
                values: {
                    low: formatTemperature(conditions.low, temperatureUnit),
                    high: formatTemperature(conditions.high, temperatureUnit)
                },
                default: 'Visits ranged {low} to {high}'
            })}
        </p>
    </section>
{/if}
