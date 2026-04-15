<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { fetchSpeciesInfo } from '../api/species';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import { getDetectionClassificationSource } from '../detection-classification-source';

    import { getBirdNames } from '../naming';
    import { formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import {
        getTemperatureUnitForSystem,
        resolveWeatherUnitSystem
    } from '../utils/weather-units';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        hideProgress?: boolean;
    }

    let { detection, onclick, hideProgress = false }: Props = $props();

    let speciesThumbnailUrl = $state<string | null>(null);

    $effect(() => {
        const speciesName = detection.scientific_name || detection.display_name;
        if (!speciesName) return;
        let cancelled = false;
        speciesThumbnailUrl = null;
        fetchSpeciesInfo(speciesName)
            .then((info) => { if (!cancelled) speciesThumbnailUrl = info.thumbnail_url; })
            .catch(() => { if (!cancelled) speciesThumbnailUrl = null; });
        return () => { cancelled = true; };
    });

    // Check if this detection is being reclassified
    let reclassifyProgress = $derived(!hideProgress ? detectionsStore.getReclassificationProgress(detection.frigate_event) : null);

    // Dynamic Naming Logic
    let naming = $derived.by(() => {
        const showCommon = settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false;
        return getBirdNames(detection, showCommon, preferSci);
    });

    let primaryName = $derived(naming.primary);
    let subName = $derived(naming.secondary);
    let currentClassificationSource = $derived(getDetectionClassificationSource(detection));
    let hasAudioSignal = $derived(
        detection.audio_confirmed
            || !!detection.audio_species
            || (detection.audio_context_species?.length ?? 0) > 0
    );
    let temperatureUnit = $derived(getTemperatureUnitForSystem(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    ));

    // True when detection is less than 5 minutes old
    let isFresh = $derived(
        Date.now() - new Date(detection.detection_time).getTime() < 5 * 60 * 1000
    );

    // Confidence level for color-coded pill
    let confidencePct = $derived(Math.round((detection.score || 0) * 100));
    let confidencePillClass = $derived(
        confidencePct >= 80
            ? 'bg-emerald-500/90 text-white'
            : confidencePct >= 60
                ? 'bg-amber-500/90 text-white'
                : 'bg-red-500/90 text-white'
    );

    function getRelativeTime(dateString: string, t: any): string {
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

            if (diffInSeconds < 3600) { // Less than 1 hour
                return t('dashboard.hero.just_discovered');
            }

            const hours = Math.floor(diffInSeconds / 3600);
            if (hours < 24) {
                if (hours === 1) return t('dashboard.hero.one_hour_ago');
                return t('dashboard.hero.hours_ago', { values: { count: hours } });
            }

            const days = Math.floor(diffInSeconds / 86400);
            if (days === 1) return t('dashboard.hero.one_day_ago');
            return t('dashboard.hero.days_ago', { values: { count: days } });
        } catch {
            return t('dashboard.hero.just_discovered');
        }
    }

</script>

<div
    role="button"
    tabindex="0"
    onclick={onclick}
    onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onclick?.()}
    class="relative w-full aspect-video sm:aspect-auto h-full min-h-[320px] rounded-3xl overflow-hidden group shadow-lg border-4 border-white dark:border-slate-800 text-left cursor-pointer focus:outline-none focus:ring-4 focus:ring-teal-500/30 transition-all"
>
    <!-- Reclassification Overlay -->
    {#if reclassifyProgress}
        <ReclassificationOverlay progress={reclassifyProgress} small={true} />
    {/if}

    <!-- Background Image -->
    <img
        src={getThumbnailUrl(detection.frigate_event)}
        alt={detection.display_name}
        class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
    />

    <!-- Gradient Overlay — frosted bottom band -->
    <div class="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-transparent"></div>
    <div class="absolute bottom-0 left-0 right-0 h-2/3 backdrop-blur-[1px] [mask-image:linear-gradient(to_top,black_30%,transparent)]"></div>

    <!-- Content Overlay -->
    <div class="absolute bottom-0 left-0 right-0 p-6 sm:p-8 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div class="flex-1 min-w-0">
            <!-- Badge row: time, confidence, audio -->
            <div class="flex flex-wrap items-center gap-2 mb-2">
                <!-- Time badge with optional live pulse -->
                <span class="inline-flex items-center gap-1.5 px-2 py-0.5 bg-teal-700 text-white text-[10px] font-bold uppercase tracking-widest rounded-md">
                    {#if isFresh}
                        <span class="relative flex h-2 w-2 shrink-0" aria-hidden="true">
                            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-300 opacity-75"></span>
                            <span class="relative inline-flex rounded-full h-2 w-2 bg-teal-200"></span>
                        </span>
                    {/if}
                    {getRelativeTime(detection.detection_time, $_)}
                </span>

                <!-- Confidence pill -->
                {#if currentClassificationSource !== 'manual'}
                    <span class="px-2 py-0.5 {confidencePillClass} text-[10px] font-bold uppercase tracking-widest rounded-md">
                        {confidencePct}% {$_('dashboard.hero.conf')}
                    </span>
                {/if}

                <!-- Audio badge -->
                {#if hasAudioSignal}
                    <span class="px-2 py-0.5 {detection.audio_confirmed ? 'bg-blue-500' : 'bg-slate-500'} text-white text-[10px] font-bold uppercase tracking-widest rounded-md flex items-center gap-1">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                        {detection.audio_confirmed ? $_('dashboard.hero.audio_confirmed') : $_('detection.audio_detected')}
                    </span>
                {/if}
            </div>

            <h2 class="text-3xl sm:text-4xl font-black text-white drop-shadow-lg tracking-tight truncate">
                {primaryName}
            </h2>

            {#if subName}
                <p class="text-lg italic text-white/70 drop-shadow mt-1 truncate">
                    {subName}
                </p>
            {/if}

            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mt-4 text-white/80 text-xs sm:text-sm font-medium">
                <span class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-teal-400"></span>
                    {formatTime(detection.detection_time)}
                </span>
                <span class="flex items-center gap-1.5">
                    <svg class="w-3.5 h-3.5 text-white/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    {detection.camera_name}
                </span>
                {#if detection.weather_condition}
                    <span class="flex items-center gap-1.5">
                        <svg class="w-3.5 h-3.5 text-white/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                        </svg>
                        {detection.weather_condition}
                    </span>
                {/if}
                {#if detection.temperature !== undefined && detection.temperature !== null}
                    <span class="font-bold text-white/90">
                        {formatTemperature(detection.temperature, temperatureUnit)}
                    </span>
                {/if}
            </div>
        </div>

        <!-- Right side: species thumbnail + view details button -->
        <div class="flex flex-col items-end gap-2 self-end sm:self-auto shrink-0">
            {#if speciesThumbnailUrl}
                <div
                    class="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl overflow-hidden border-2 border-white/30 shadow-lg shadow-black/40 ring-1 ring-black/10 flex-shrink-0"
                    title={primaryName}
                >
                    <img
                        src={speciesThumbnailUrl}
                        alt={primaryName}
                        class="w-full h-full object-cover"
                    />
                </div>
            {/if}
            <div class="px-4 py-2 bg-teal-700 hover:bg-teal-800 text-white text-xs font-bold uppercase tracking-widest rounded-full transition-colors shadow-lg">
                {$_('dashboard.hero.view_details')}
            </div>
        </div>
    </div>
</div>
