<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import { hasFrigateMediaIssue } from '../utils/frigate-errors';
    import { FRIGATE_LOGO_URL } from '../assets';
    import { getDetectionClassificationSource } from '../detection-classification-source';

    import { getBirdNames } from '../naming';
    import { formatDate as formatDateValue, formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import {
        formatPrecipitation,
        formatWindSpeed,
        getTemperatureUnitForSystem,
        resolveWeatherUnitSystem
    } from '../utils/weather-units';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onReclassify?: (detection: Detection) => void;
        onRetag?: (detection: Detection) => void;
        onPlay?: (detection: Detection) => void;
        onFetchFullVisit?: (detection: Detection) => void;
        hideProgress?: boolean;
        index?: number;
        selectionMode?: boolean;
        selected?: boolean;
        fullVisitAvailable?: boolean;
        fullVisitFetched?: boolean;
        fullVisitFetchState?: 'idle' | 'fetching' | 'ready' | 'failed';
    }

    let {
        detection,
        onclick,
        onReclassify,
        onRetag,
        onPlay,
        onFetchFullVisit,
        hideProgress = false,
        index = 0,
        selectionMode = false,
        selected = false,
        fullVisitAvailable = false,
        fullVisitFetched = false,
        fullVisitFetchState = 'idle'
    }: Props = $props();

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

    let isVerified = $derived(detection.audio_confirmed && detection.score > 0.7);
    let audioContextSpecies = $derived.by(() => {
        const seen = new Set<string>();
        const values: string[] = [];
        const add = (candidate: unknown) => {
            if (typeof candidate !== 'string') return;
            const normalized = candidate.trim();
            if (!normalized) return;
            const key = normalized.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            values.push(normalized);
        };

        add(detection.audio_species);
        for (const species of detection.audio_context_species ?? []) {
            add(species);
        }
        return values;
    });
    let hasAudioSignal = $derived(detection.audio_confirmed || audioContextSpecies.length > 0);
    let audioNearbySummary = $derived(audioContextSpecies.join(', '));
    let currentClassificationSource = $derived(getDetectionClassificationSource(detection));
    let classificationSource = $derived.by(() => {
        if (currentClassificationSource === 'manual') {
            return { key: 'manual', label: $_('detection.tag_manual') };
        }
        if (currentClassificationSource === 'video') {
            return { key: 'video', label: $_('detection.tag_video') };
        }
        return { key: 'snapshot', label: $_('detection.tag_snapshot') };
    });
    const UNKNOWN_SPECIES_LABELS = new Set(['unknown', 'unknown bird', 'background']);
    let isUnknownSpecies = $derived(
        UNKNOWN_SPECIES_LABELS.has((detection.display_name || '').trim().toLowerCase())
    );
    let processedUnknownStatus = $derived.by(() => {
        if (!isUnknownSpecies) return null;
        const videoStatus = detection.video_classification_status;
        if (currentClassificationSource === 'manual') {
            return {
                label: $_('detection.tag_manual'),
                classes: 'bg-amber-500 text-white shadow-lg shadow-amber-500/30'
            };
        }
        if (videoStatus === 'completed') {
            return {
                label: $_('detection.processed', { default: 'Processed' }),
                classes: 'bg-teal-500 text-white shadow-lg shadow-teal-500/30'
            };
        }
        if (videoStatus === 'failed') {
            return {
                label: $_('detection.video_analysis.failed_title'),
                classes: 'bg-rose-500 text-white shadow-lg shadow-rose-500/30'
            };
        }
        if (videoStatus === 'pending' || videoStatus === 'processing') {
            return {
                label: $_('detection.video_analysis.in_progress'),
                classes: 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
            };
        }
        return null;
    });
    let hasFrigateIssueBadge = $derived(hasFrigateMediaIssue(detection));
    let hasWeather = $derived(
        detection.temperature !== undefined && detection.temperature !== null ||
        !!detection.weather_condition ||
        detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null ||
        detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null ||
        detection.weather_precipitation !== undefined && detection.weather_precipitation !== null ||
        detection.weather_rain !== undefined && detection.weather_rain !== null ||
        detection.weather_snowfall !== undefined && detection.weather_snowfall !== null
    );

    let imageError = $state(false);
    let imageLoaded = $state(false);
    let cardElement = $state<HTMLElement | null>(null);
    let isVisible = $state(false);

    function handleReclassifyClick(event: MouseEvent) {
        event.stopPropagation();
        onReclassify?.(detection);
    }

    function handleRetagClick(event: MouseEvent) {
        event.stopPropagation();
        onRetag?.(detection);
    }

    function handlePlayClick(event: MouseEvent) {
        event.stopPropagation();
        onPlay?.(detection);
    }

    function handleFetchFullVisitClick(event: MouseEvent) {
        event.stopPropagation();
        onFetchFullVisit?.(detection);
    }

    // Lazy load with intersection observer
    $effect(() => {
        if (!cardElement) return;
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting) {
                    isVisible = true;
                    observer.disconnect();
                }
            },
            { rootMargin: '100px' }
        );
        observer.observe(cardElement);
        return () => observer.disconnect();
    });

    function formatDate(dateString: string): string {
        try {
            const date = new Date(dateString);
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            if (date.toDateString() === today.toDateString()) {
                return $_('common.today');
            } else if (date.toDateString() === yesterday.toDateString()) {
                return $_('common.yesterday');
            }
            return formatDateValue(date);
        } catch {
            return '';
        }
    }

    function getConfidenceColor(score: number): string {
        if (score >= 0.9) return 'text-emerald-500';
        if (score >= 0.7) return 'text-amber-500';
        return 'text-red-500';
    }

    function getConfidenceBg(score: number): string {
        if (score >= 0.9) return 'border-emerald-500/30';
        if (score >= 0.7) return 'border-amber-500/30';
        return 'border-red-500/30';
    }

    const rainTotal = $derived(
        (detection.weather_rain ?? 0) + (detection.weather_precipitation ?? 0)
    );
    const weatherConditionText = $derived(
        typeof detection.weather_condition === 'string'
            ? detection.weather_condition.toLowerCase()
            : String(detection.weather_condition ?? '').toLowerCase()
    );
    const hasRain = $derived(
        rainTotal > 0 || weatherConditionText.includes('rain')
    );
    const snowTotal = $derived(
        detection.weather_snowfall ?? 0
    );
    const hasSnow = $derived(
        snowTotal > 0 || weatherConditionText.includes('snow')
    );
    const hasCloud = $derived(
        detection.weather_cloud_cover !== undefined &&
        detection.weather_cloud_cover !== null
    );
    const windSpeed = $derived(
        detection.weather_wind_speed !== undefined &&
        detection.weather_wind_speed !== null
            ? Number(detection.weather_wind_speed)
            : null
    );
    const hasWind = $derived(windSpeed !== null && !Number.isNaN(windSpeed));
    const hasTemperature = $derived(
        detection.temperature !== undefined && detection.temperature !== null
    );
    const weatherConditionSummary = $derived.by(() => summarizeWeatherCondition(detection.weather_condition));
    const hasWeatherCondition = $derived(
        weatherConditionSummary.length > 0
    );
    const hasIcy = $derived(
        hasTemperature && (detection.temperature ?? 0) <= 0
    );
    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            // authStore.locationWeatherUnitSystem is already correctly resolved (including
            // "british") from /api/auth/status for all users. Without it as a middle
            // fallback, "british" collapses to metric via locationTemperatureUnit → "celsius".
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));
    const canPlayVideo = $derived(!!onPlay && (detection.has_clip || fullVisitFetched));
    const showFetchFullVisitAction = $derived(!!onFetchFullVisit && fullVisitAvailable && !fullVisitFetched);
    const fullVisitFetchLabel = $derived.by(() => {
        if (fullVisitFetchState === 'fetching') {
            return $_('video_player.fetching_full_visit', { default: 'Fetching...' });
        }
        if (fullVisitFetchState === 'failed') {
            return $_('video_player.fetch_full_visit_retry', { default: 'Retry full clip' });
        }
        return $_('video_player.fetch_full_visit', { default: 'Fetch full clip' });
    });

    function rainColor(total: number) {
        if (total >= 5) return 'text-blue-600';
        if (total >= 1) return 'text-blue-500';
        if (total > 0) return 'text-blue-400';
        return 'text-blue-300';
    }

    function snowColor(total: number) {
        if (total >= 5) return 'text-indigo-600';
        if (total >= 1) return 'text-indigo-500';
        if (total > 0) return 'text-indigo-400';
        return 'text-indigo-300';
    }

    function windColor(speed: number | null) {
        if (speed === null || Number.isNaN(speed)) return 'text-emerald-400';
        if (speed >= 40) return 'text-rose-500';
        if (speed >= 25) return 'text-amber-500';
        if (speed >= 10) return 'text-emerald-500';
        return 'text-emerald-400';
    }

    function cloudColor(cover?: number | null) {
        if (cover === null || cover === undefined || Number.isNaN(cover)) return 'text-slate-400';
        if (cover >= 80) return 'text-slate-600';
        if (cover >= 50) return 'text-slate-500';
        if (cover >= 20) return 'text-slate-400';
        return 'text-slate-300';
    }

    function formatPrecip(value?: number | null): string {
        const formatted = formatPrecipitation(value, weatherUnitSystem, {
            metric: $_('common.unit_mm', { default: 'mm' }),
            imperial: $_('common.unit_in', { default: 'in' })
        });
        if (formatted) return formatted;
        return weatherUnitSystem === 'imperial'
            ? `0${$_('common.unit_in', { default: 'in' })}`
            : `0${$_('common.unit_mm', { default: 'mm' })}`;
    }

    function summarizeWeatherCondition(value?: string | null): string {
        if (typeof value !== 'string') return '';
        const raw = value.trim();
        if (!raw) return '';
        const text = raw.toLowerCase();

        if (text.includes('thunder') || text.includes('storm')) return 'Storm';
        if (text.includes('sleet')) return 'Sleet';
        if (text.includes('hail')) return 'Hail';
        if (text.includes('snow')) return 'Snow';
        if (text.includes('drizzle')) return 'Drizzle';
        if (text.includes('rain') || text.includes('shower')) return 'Rain';
        if (text.includes('fog') || text.includes('mist') || text.includes('haze')) return 'Fog';
        if (text.includes('cloud')) return text.includes('partly') ? 'Partly Cloudy' : 'Cloudy';
        if (text.includes('clear') || text.includes('sunny')) return 'Clear';

        return raw;
    }
</script>

<div class="relative pt-2 pl-2">
    <div
        bind:this={cardElement}
        class="group relative bg-white/95 dark:bg-slate-800/85 rounded-3xl
               shadow-card dark:shadow-card-dark hover:shadow-card-hover dark:hover:shadow-card-dark-hover
               border border-slate-200/80 dark:border-slate-700/60
               ring-1 ring-slate-200/40 dark:ring-slate-700/40 ring-inset
               hover:border-teal-500/30 dark:hover:border-teal-500/20
               overflow-hidden transition-all duration-500 ease-out
               hover:-translate-y-1.5 flex flex-col h-full
               text-left w-full animate-entrance
               {detection.is_hidden ? 'opacity-60 grayscale-[0.5]' : ''}
               {isVerified ? 'ring-2 ring-emerald-500/20 dark:ring-emerald-500/10' : ''}
               {selected ? 'border-cyan-300/90 dark:border-cyan-400/70 ring-2 ring-cyan-400/45 bg-cyan-50/30 dark:bg-cyan-500/5 shadow-card-hover dark:shadow-card-dark-hover' : ''}"
        style="animation-delay: {index * 40}ms"
    >
    <button
        type="button"
        aria-label="{$_('detection.card_label', { values: { species: primaryName, camera: detection.camera_name } })}"
        onclick={onclick}
        class="absolute inset-0 z-10 rounded-3xl focus:outline-none focus:ring-2 focus:ring-teal-500/50"
    ></button>

    <!-- Reclassification Overlay -->
    {#if reclassifyProgress}
        <ReclassificationOverlay progress={reclassifyProgress} small={true} />
    {/if}

    {#if selectionMode}
        <div class="absolute -left-1.5 -top-1.5 z-30 pointer-events-none">
            <div
                class="inline-flex h-8 w-8 rounded-full border-2 items-center justify-center shadow-lg backdrop-blur-sm
                    {selected
                        ? 'border-cyan-400 bg-cyan-500 text-white shadow-cyan-500/30'
                        : 'border-slate-300/90 dark:border-slate-500/80 bg-white/95 dark:bg-slate-900/95 text-slate-400 dark:text-slate-500 shadow-slate-900/10'}"
            >
                {#if selected}
                    <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                        <path d="M5 10.5l3.2 3.2L15 7" stroke-linecap="round" stroke-linejoin="round"></path>
                    </svg>
                {:else}
                    <span class="inline-block h-2.5 w-2.5 rounded-full border-2 border-current"></span>
                {/if}
            </div>
        </div>
    {/if}

    <!-- Image Section -->
    <div class="relative aspect-[4/3] overflow-hidden">
        {#if !imageError && isVisible}
            {#if !imageLoaded}
                <div class="absolute inset-0 bg-slate-100 dark:bg-slate-800 animate-shimmer bg-[length:200%_100%] bg-gradient-to-r from-transparent via-slate-200/10 to-transparent"></div>
            {/if}
            <img
                src={getThumbnailUrl(detection.frigate_event)}
                alt="{$_('detection.image_alt', { values: { species: primaryName, camera: detection.camera_name } })}"
                loading="lazy"
                class="w-full h-full object-cover transition-transform duration-700 ease-out
                       group-hover:scale-110 group-hover:rotate-1
                       {imageLoaded ? 'opacity-100' : 'opacity-0'}"
                onload={() => imageLoaded = true}
                onerror={() => imageError = true}
            />
            <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20 opacity-60"></div>
            <div class="absolute inset-0 bg-teal-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>

        {:else}
            <div class="absolute inset-0 flex items-center justify-center bg-slate-100 dark:bg-slate-800">
                <svg class="w-12 h-12 text-slate-300 dark:text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        {/if}
        <div class="absolute top-3 left-3 right-3 flex justify-between items-start">
            <div class="flex flex-col gap-1.5">
                {#if detection.is_favorite}
                    <div class="flex items-center gap-1 px-2 py-1 rounded-full bg-amber-500 text-white text-[10px] font-black uppercase tracking-wider shadow-lg shadow-amber-500/30">
                        <svg class="w-3 h-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M11.05 2.927c.3-.921 1.603-.921 1.902 0l2.02 6.217a1 1 0 00.95.69h6.54c.969 0 1.371 1.24.588 1.81l-5.29 3.844a1 1 0 00-.364 1.118l2.02 6.217c.3.921-.755 1.688-1.539 1.118l-5.29-3.844a1 1 0 00-1.175 0l-5.29 3.844c-.783.57-1.838-.197-1.539-1.118l2.02-6.217a1 1 0 00-.364-1.118L.98 11.644c-.783-.57-.38-1.81.588-1.81h6.54a1 1 0 00.95-.69l2.02-6.217z" />
                        </svg>
                        {$_('detection.favorite', { default: 'Favorite' })}
                    </div>
                {/if}
                {#if isVerified}
                    <div class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-500 text-white text-[10px] font-black uppercase tracking-wider shadow-lg shadow-emerald-500/40 animate-fade-in">
                        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.64.304 1.24.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
                        </svg>
                        {$_('detection.verified')}
                    </div>
                {/if}
                {#if detection.is_hidden}
                    <div class="px-2 py-1 rounded-full bg-amber-500 text-white text-[10px] font-bold uppercase tracking-wider shadow-lg">
                        {$_('detection.hidden')}
                    </div>
                {/if}
                {#if processedUnknownStatus}
                    <div class="px-2 py-1 rounded-full text-[10px] font-black uppercase tracking-wider {processedUnknownStatus.classes}">
                        {processedUnknownStatus.label}
                    </div>
                {/if}
                {#if hasFrigateIssueBadge}
                    <div
                        class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-rose-600 text-white text-[10px] font-black uppercase tracking-wider shadow-lg shadow-rose-900/30"
                        title={$_('detection.frigate_media_missing', { default: 'Frigate Media Missing' })}
                    >
                        <img src={FRIGATE_LOGO_URL} alt="" aria-hidden="true" class="w-3.5 h-3.5 rounded-[2px] bg-white/95 p-0.5 object-contain" />
                        <span>{$_('detection.frigate_badge', { default: 'Frigate' })}</span>
                    </div>
                {/if}
            </div>
            <div class="flex flex-col items-end gap-1.5">
                <div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-black/40 text-white text-[9px] font-black uppercase tracking-wider backdrop-blur-md border border-white/10">
                    {#if classificationSource.key === 'manual'}
                        <svg class="w-3 h-3 text-amber-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 4h9m-9 4h7m-7 4h5m-7 4h7M5 6h.01M5 10h.01M5 14h.01M5 18h.01" />
                        </svg>
                    {:else if classificationSource.key === 'video'}
                        <svg class="w-3 h-3 text-teal-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14m-4 4H5a2 2 0 01-2-2V8a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2z" />
                        </svg>
                    {:else}
                        <svg class="w-3 h-3 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                        </svg>
                    {/if}
                    <span>{classificationSource.label}</span>
                </div>
                {#if currentClassificationSource !== 'manual'}
                    <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-2xl bg-white/95 dark:bg-slate-900/95 shadow-xl backdrop-blur-md border {getConfidenceBg(detection.score)}">
                        <span class="w-2 h-2 rounded-full {detection.score >= 0.9 ? 'bg-emerald-500 animate-pulse' : detection.score >= 0.7 ? 'bg-amber-500' : 'bg-red-500'}"></span>
                        <span class="text-xs font-black {getConfidenceColor(detection.score)} leading-none">{(detection.score * 100).toFixed(0)}%</span>
                    </div>
                {/if}
                {#if detection.frigate_score !== undefined && detection.frigate_score !== null}
                    <div class="px-2 py-1 rounded-lg bg-black/40 text-white/90 text-[9px] font-bold backdrop-blur-sm tracking-tight border border-white/5">
                        {$_('detection.frigate_score', { values: { score: (detection.frigate_score * 100).toFixed(0) } })}
                    </div>
                {/if}
            </div>
        </div>
        <div class="absolute bottom-3 left-3 z-20 flex flex-col items-start gap-2">
            <div class="px-2.5 py-1.5 rounded-xl bg-black/40 text-white text-[10px] font-bold backdrop-blur-md border border-white/10 flex items-center gap-1.5">
                <svg class="w-3 h-3 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {formatTime(detection.detection_time)}
            </div>
            {#if canPlayVideo}
                <div class="flex items-center gap-2">
                    {#if fullVisitFetched}
                        <div
                            class="inline-flex h-7 w-7 items-center justify-center rounded-full bg-teal-500/95 text-white shadow-lg shadow-teal-900/30 ring-1 ring-teal-300/35"
                            title={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                            aria-label={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                        >
                            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M7 3H5a2 2 0 00-2 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                                <path d="M13 3h2a2 2 0 012 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                                <path d="M17 13v2a2 2 0 01-2 2h-2" stroke-linecap="round" stroke-linejoin="round"></path>
                                <path d="M7 17H5a2 2 0 01-2-2v-2" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        </div>
                    {/if}
                    <button
                        onclick={handlePlayClick}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                e.stopPropagation();
                                handlePlayClick(e as any);
                            }
                        }}
                        aria-label="{$_('detection.play_video', { values: { species: primaryName } })}"
                        class="inline-flex h-9 items-center gap-2 rounded-xl border border-white/25 bg-black/55 px-3 text-[11px] font-black uppercase tracking-wide text-white shadow-2xl backdrop-blur-sm transition-all duration-200 hover:bg-teal-500/90"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                        <span>{$_('common.play', { default: 'Play' })}</span>
                    </button>
                </div>
            {/if}
            {#if showFetchFullVisitAction}
                <button
                    onclick={handleFetchFullVisitClick}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            e.stopPropagation();
                            handleFetchFullVisitClick(e as any);
                        }
                    }}
                    disabled={fullVisitFetchState === 'fetching'}
                    aria-label={fullVisitFetchLabel}
                    class="inline-flex h-9 items-center gap-2 rounded-xl border border-white/25 bg-black/55 px-3 text-[11px] font-black uppercase tracking-wide text-white shadow-2xl backdrop-blur-sm transition-all duration-200 hover:bg-teal-500/90 disabled:cursor-wait disabled:opacity-70"
                >
                    {#if fullVisitFetchState === 'fetching'}
                        <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"></span>
                    {:else}
                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M10 3v8"></path>
                            <path d="M7 8l3 3 3-3"></path>
                            <path d="M4 14h12"></path>
                        </svg>
                    {/if}
                    <span>{fullVisitFetchLabel}</span>
                </button>
            {/if}
        </div>
        {#if onReclassify || onRetag}
            <div class="absolute bottom-3 right-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-2 group-hover:translate-y-0">
                {#if onReclassify}
                    <button
                        onclick={handleReclassifyClick}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                e.stopPropagation();
                                handleReclassifyClick(e as any);
                            }
                        }}
                        aria-label="{$_('detection.reclassify', { values: { species: primaryName } })}"
                        class="w-9 h-9 rounded-xl bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                               hover:bg-teal-500 hover:text-white transition-all duration-200
                               flex items-center justify-center shadow-2xl border border-slate-200/50 dark:border-slate-700/50"
                    >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                {/if}
                {#if onRetag}
                    <button
                        onclick={handleRetagClick}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                e.stopPropagation();
                                handleRetagClick(e as any);
                            }
                        }}
                        aria-label="{$_('detection.retag', { values: { species: primaryName } })}"
                        class="w-9 h-9 rounded-xl bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200
                               hover:bg-amber-500 hover:text-white transition-all duration-200
                               flex items-center justify-center shadow-2xl border border-slate-200/50 dark:border-slate-700/50"
                    >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                    </button>
                {/if}
            </div>
        {/if}
    </div>
    <div class="p-5 flex-1 flex flex-col gap-4">
        <div>
            <div class="flex items-center justify-between gap-2">
                <h3 class="text-xl font-black text-slate-900 dark:text-white truncate tracking-tight leading-tight" title={primaryName}>
                    {primaryName}
                </h3>
            </div>
            {#if subName}
                <p class="text-xs italic text-slate-500 dark:text-slate-400 font-medium mt-0.5 truncate opacity-80">
                    {subName}
                </p>
            {/if}
        </div>
        {#if hasAudioSignal}
            <div class="p-3 rounded-2xl bg-teal-500/5 dark:bg-teal-500/10 border border-teal-500/10 dark:border-teal-500/20 flex items-center gap-3 group/audio">
                <div class="w-8 h-8 rounded-xl bg-teal-500/20 flex items-center justify-center flex-shrink-0">
                    <svg class="w-4 h-4 text-teal-600 dark:text-teal-400 {detection.audio_confirmed ? 'animate-pulse-slow' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                </div>
                <div class="min-w-0">
                    <p class="text-[10px] font-black uppercase tracking-widest text-teal-600/70 dark:text-teal-400/70 mb-0.5">
                        {detection.audio_confirmed
                            ? $_('detection.audio_match')
                            : (audioNearbySummary
                                ? $_('detection.audio_possible_nearby', { default: 'Possible Nearby Audio Match' })
                                : $_('detection.audio_no_direct_match', { default: 'No Direct Audio Confirmation' }))}
                    </p>
                    <p class="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">
                        {detection.audio_confirmed
                            ? (detection.audio_species || $_('detection.birdnet_confirmed'))
                            : (audioNearbySummary
                                ? $_('detection.audio_nearby', { values: { species: audioNearbySummary }, default: 'Nearby audio: {species}' })
                                : $_('detection.audio_no_match_desc', { default: 'No nearby BirdNET species in the matching window' }))}
                        {#if detection.audio_score && detection.audio_confirmed}
                            <span class="ml-1 opacity-60">({(detection.audio_score * 100).toFixed(0)}%)</span>
                        {/if}
                    </p>
                </div>
            </div>
        {/if}
        {#if hasWeather}
            <div class="rounded-2xl bg-sky-50/80 dark:bg-slate-900/40 border border-sky-100/80 dark:border-slate-700/60 px-3 py-2">
                <div class="space-y-2">
                {#if hasWeatherCondition || hasTemperature}
                    <div class="rounded-xl border border-white/70 dark:border-slate-700/70 bg-white/60 dark:bg-slate-950/35 p-2">
                        <div class="flex items-center justify-between gap-3">
                            <div class="min-w-0 flex items-center gap-2 text-[10px] font-semibold text-slate-500 dark:text-slate-300">
                                {#if hasWeatherCondition}
                                    <div class="min-w-0 inline-flex items-center gap-1.5">
                                        <svg class="w-4 h-4 {cloudColor(detection.weather_cloud_cover)} shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label={$_('detection.weather_title')}>
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                        </svg>
                                        <span class="truncate" title={detection.weather_condition || ''}>
                                            {weatherConditionSummary}
                                        </span>
                                    </div>
                                {/if}
                                {#if hasIcy}
                                    <span class="inline-flex items-center justify-center rounded-full bg-sky-100/80 dark:bg-sky-900/40 p-1 shrink-0" title={$_('detection.weather_icy')} aria-label={$_('detection.weather_icy')}>
                                        <svg class="w-3.5 h-3.5 text-sky-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v18m4-10l-4 4-4-4" />
                                        </svg>
                                    </span>
                                {/if}
                            </div>
                            {#if hasTemperature}
                                <div class="shrink-0 whitespace-nowrap text-xs font-black text-slate-700 dark:text-slate-200">
                                    {formatTemperature(detection.temperature, temperatureUnit)}
                                </div>
                            {/if}
                        </div>
                    </div>
                {/if}

                {#if hasRain || hasSnow || hasCloud || hasWind}
                    <div class="rounded-xl border border-dashed border-sky-200/90 dark:border-slate-700/80 bg-white/35 dark:bg-slate-950/20 p-2">
                        <div class="mb-1 flex items-center gap-1.5 text-[9px] font-black uppercase tracking-wider text-slate-500/80 dark:text-slate-400/90">
                            <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <span>{$_('detection.weather_details')}</span>
                        </div>
                        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-slate-500 dark:text-slate-300 text-[10px] font-semibold">
                            {#if hasRain}
                                <div class="inline-flex items-center gap-1 whitespace-nowrap">
                                    <svg class="w-4 h-4 {rainColor(rainTotal)}" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label={$_('detection.weather_rain')}>
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 13v4m-4-2v4m-4-2v2m1-8a5 5 0 119.584 1.245A4 4 0 0117 16H7a4 4 0 01-1-7.874" />
                                    </svg>
                                    <span>{formatPrecip(rainTotal)}</span>
                                </div>
                            {/if}
                            {#if hasSnow}
                                <div class="inline-flex items-center gap-1 whitespace-nowrap">
                                    <svg class="w-4 h-4 {snowColor(snowTotal)}" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label={$_('detection.weather_snow')}>
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v18m9-9H3m15.364-6.364l-12.728 12.728m0-12.728l12.728 12.728" />
                                    </svg>
                                    <span>{formatPrecip(snowTotal)}</span>
                                </div>
                            {/if}
                            {#if hasCloud}
                                <div class="inline-flex items-center gap-1 whitespace-nowrap">
                                    <svg class="w-4 h-4 {cloudColor(detection.weather_cloud_cover)}" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label={$_('detection.weather_cloud')}>
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                    </svg>
                                    <span>{Math.round(detection.weather_cloud_cover ?? 0)}%</span>
                                </div>
                            {/if}
                            {#if hasWind}
                                <div class="inline-flex items-center gap-1 whitespace-nowrap">
                                    <svg class="w-4 h-4 {windColor(windSpeed)}" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-label={$_('detection.weather_wind')}>
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h11a3 3 0 100-6M2 12h13a3 3 0 110 6H9" />
                                    </svg>
                                    <span>{formatWindSpeed(windSpeed, weatherUnitSystem, {
                                        metric: $_('common.unit_kmh', { default: 'km/h' }),
                                        imperial: $_('common.unit_mph', { default: 'mph' })
                                    })}</span>
                                </div>
                            {/if}
                        </div>
                    </div>
                {/if}
                </div>
            </div>
        {/if}
        <div class="mt-auto grid grid-cols-2 gap-2">
            <div class="col-span-2 flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200/50 dark:border-slate-700/50">
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                <span class="text-[10px] font-bold text-slate-600 dark:text-slate-400 whitespace-nowrap">
                    {formatDate(detection.detection_time)}
                </span>
            </div>
            <div class="col-span-2 flex items-center gap-2 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-200/50 dark:border-slate-700/50 overflow-hidden">
                <svg class="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                </svg>
                <span class="text-[10px] font-bold text-slate-500 dark:text-slate-400 truncate">
                    {detection.camera_name}
                </span>
                {#if detection.sub_label && detection.sub_label !== detection.display_name && detection.sub_label !== subName}
                    <div class="ml-auto flex items-center gap-1">
                        <div class="w-1 h-1 rounded-full bg-teal-500"></div>
                        <span class="text-[9px] font-black text-teal-600 uppercase tracking-tighter">{$_('detection.frigate_verified')}</span>
                    </div>
                {/if}
            </div>
        </div>
    </div>
    </div>
</div>
