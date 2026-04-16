<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';

    import { getBirdNames } from '../naming';
    import { formatDate as formatDateValue, formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import {
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
        onFetchFullVisit: _onFetchFullVisit,
        hideProgress = false,
        index = 0,
        selectionMode = false,
        selected = false,
        fullVisitAvailable: _fullVisitAvailable = false,
        fullVisitFetched = false,
        fullVisitFetchState: _fullVisitFetchState = 'idle'
    }: Props = $props();

    // Check if this detection is being reclassified
    let reclassifyProgress = $derived(!hideProgress ? detectionsStore.getReclassificationProgress(detection.frigate_event) : null);
    let analysisActive = $derived(!!reclassifyProgress);

    // Dynamic Naming Logic
    let naming = $derived.by(() => {
        const showCommon = settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false;
        return getBirdNames(detection, showCommon, preferSci);
    });

    let primaryName = $derived(naming.primary);
    let subName = $derived(naming.secondary);

    let isVerified = $derived(detection.audio_confirmed && detection.score > 0.7);
    let hasAudioConfirmed = $derived(!!detection.audio_confirmed);

    let hasWeather = $derived(
        detection.temperature !== undefined && detection.temperature !== null ||
        !!detection.weather_condition
    );
    let hasTemperature = $derived(
        detection.temperature !== undefined && detection.temperature !== null
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

    const weatherConditionSummary = $derived.by(() => summarizeWeatherCondition(detection.weather_condition));
    const hasWeatherCondition = $derived(weatherConditionSummary.length > 0);
    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));
    const canPlayVideo = $derived(!!onPlay && (detection.has_clip || fullVisitFetched));

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

    function weatherIcon(summary: string): string {
        const s = summary.toLowerCase();
        if (s.includes('storm') || s.includes('thunder')) return 'storm';
        if (s.includes('snow') || s.includes('sleet') || s.includes('hail')) return 'snow';
        if (s.includes('rain') || s.includes('drizzle') || s.includes('shower')) return 'rain';
        if (s.includes('fog') || s.includes('mist') || s.includes('haze')) return 'fog';
        if (s.includes('partly')) return 'partly-cloudy';
        if (s.includes('cloud')) return 'cloudy';
        if (s.includes('clear') || s.includes('sunny')) return 'clear';
        return 'cloudy';
    }
</script>

<div class="relative rounded-[2rem] transition-all duration-300 ease-out">
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
               {analysisActive ? 'border-2 border-indigo-400/90 dark:border-indigo-300/90 ring-2 ring-indigo-500/30 dark:ring-indigo-300/25 bg-indigo-50/10 dark:bg-indigo-500/10 shadow-[0_0_0_1px_rgba(99,102,241,0.12)]' : ''}
               {selectionMode && selected && !analysisActive ? 'border-2 border-cyan-300 dark:border-cyan-300/90 ring-2 ring-cyan-500/35 dark:ring-cyan-300/20 bg-cyan-50/20 dark:bg-cyan-500/5' : ''}"
        style="animation-delay: {index * 40}ms"
    >
    <button
        type="button"
        aria-label="{$_('detection.card_label', { values: { species: primaryName, camera: detection.camera_name } })}"
        onclick={onclick}
        class="absolute inset-0 z-10 rounded-3xl focus:outline-none focus:ring-2 focus:ring-teal-500/50"
    ></button>

    <!-- Reclassification Overlay -->
    {#if analysisActive && reclassifyProgress}
        <div class="absolute inset-0 z-50 pointer-events-none rounded-3xl overflow-hidden">
            <ReclassificationOverlay progress={reclassifyProgress} small={true} />
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
        {#if !analysisActive}
            <!-- Top-left: icon-only badges (favorite, verified, audio) -->
            <div class="absolute top-3 left-3 flex items-center gap-1.5">
                {#if detection.is_favorite}
                    <div
                        role="img"
                        class="w-7 h-7 rounded-full bg-amber-500/90 text-white flex items-center justify-center shadow-lg shadow-amber-500/30"
                        title={$_('detection.favorite', { default: 'Favorite' })}
                        aria-label={$_('detection.favorite', { default: 'Favorite' })}
                    >
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M11.05 2.927c.3-.921 1.603-.921 1.902 0l2.02 6.217a1 1 0 00.95.69h6.54c.969 0 1.371 1.24.588 1.81l-5.29 3.844a1 1 0 00-.364 1.118l2.02 6.217c.3.921-.755 1.688-1.539 1.118l-5.29-3.844a1 1 0 00-1.175 0l-5.29 3.844c-.783.57-1.838-.197-1.539-1.118l2.02-6.217a1 1 0 00-.364-1.118L.98 11.644c-.783-.57-.38-1.81.588-1.81h6.54a1 1 0 00.95-.69l2.02-6.217z" />
                        </svg>
                    </div>
                {/if}
                {#if isVerified}
                    <div
                        role="img"
                        class="w-7 h-7 rounded-full bg-emerald-500/90 text-white flex items-center justify-center shadow-lg shadow-emerald-500/40"
                        title={$_('detection.verified')}
                        aria-label={$_('detection.verified')}
                    >
                        <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                            <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                        </svg>
                    </div>
                {/if}
                {#if hasAudioConfirmed && !isVerified}
                    <div
                        role="img"
                        class="w-7 h-7 rounded-full bg-teal-500/90 text-white flex items-center justify-center shadow-lg shadow-teal-500/30"
                        title={$_('detection.audio_match')}
                        aria-label={$_('detection.audio_match')}
                    >
                        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
                        </svg>
                    </div>
                {/if}
            </div>

            <!-- Top-right: confidence only -->
            <div class="absolute top-3 right-3">
                <div class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-2xl bg-white/95 dark:bg-slate-900/95 shadow-xl backdrop-blur-md border {getConfidenceBg(detection.score)}">
                    <span class="w-2 h-2 rounded-full {detection.score >= 0.9 ? 'bg-emerald-500 animate-pulse' : detection.score >= 0.7 ? 'bg-amber-500' : 'bg-red-500'}"></span>
                    <span class="text-xs font-black {getConfidenceColor(detection.score)} leading-none">{(detection.score * 100).toFixed(0)}%</span>
                </div>
            </div>

            <!-- Bottom-left: time + play inline -->
            <div class="absolute bottom-3 left-3 z-20 flex items-center gap-2">
                <div class="px-2.5 py-1.5 rounded-xl bg-black/60 text-white text-[10px] font-bold backdrop-blur-md border border-white/10 flex items-center gap-1.5">
                    <svg class="w-3 h-3 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {formatTime(detection.detection_time)}
                </div>
                {#if canPlayVideo}
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
                        class="inline-flex h-7 w-7 items-center justify-center rounded-xl border border-white/25 bg-black/55 text-white shadow-2xl backdrop-blur-sm transition-all duration-200 hover:bg-teal-500/90"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    </button>
                    {#if fullVisitFetched}
                        <div
                            class="inline-flex h-5 w-5 items-center justify-center rounded-full bg-teal-500/90 text-white shadow-md"
                            title={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                            aria-label={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                        >
                            <svg class="h-2.5 w-2.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                <path d="M7 3H5a2 2 0 00-2 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                                <path d="M13 3h2a2 2 0 012 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                                <path d="M17 13v2a2 2 0 01-2 2h-2" stroke-linecap="round" stroke-linejoin="round"></path>
                                <path d="M7 17H5a2 2 0 01-2-2v-2" stroke-linecap="round" stroke-linejoin="round"></path>
                            </svg>
                        </div>
                    {/if}
                {/if}
            </div>
        {/if}
        {#if (onReclassify || onRetag) && !analysisActive}
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

    <!-- Body -->
    <div class="p-4 flex-1 flex flex-col gap-2.5">
        <!-- Species name -->
        <div>
            <h3 class="text-lg font-black text-slate-900 dark:text-white truncate tracking-tight leading-tight" title={primaryName}>
                {primaryName}
            </h3>
            {#if subName}
                <p class="text-[11px] italic text-slate-500 dark:text-slate-400 font-medium mt-0.5 truncate opacity-80">
                    {subName}
                </p>
            {/if}
        </div>

        <!-- Compact weather: icon + condition + temp -->
        {#if hasWeather && (hasWeatherCondition || hasTemperature)}
            <div class="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                {#if hasWeatherCondition}
                    {@const icon = weatherIcon(weatherConditionSummary)}
                    {#if icon === 'clear'}
                        <svg class="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                    {:else if icon === 'rain' || icon === 'storm'}
                        <svg class="w-4 h-4 text-blue-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 13v4m-4-2v4m-4-2v2m1-8a5 5 0 119.584 1.245A4 4 0 0117 16H7a4 4 0 01-1-7.874" />
                        </svg>
                    {:else if icon === 'snow'}
                        <svg class="w-4 h-4 text-indigo-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v18m9-9H3m15.364-6.364l-12.728 12.728m0-12.728l12.728 12.728" />
                        </svg>
                    {:else if icon === 'fog'}
                        <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h16M4 12h12M4 16h16" />
                        </svg>
                    {:else if icon === 'partly-cloudy'}
                        <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m4.22 1.78l.7-.7M20 12h1m-3.78 4.22l.7.7M12 20v1m-4.22-1.78l-.7.7M4 12H3m3.78-4.22l-.7-.7" />
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 15a4 4 0 004 4h5a3 3 0 100-6h-.5a4 4 0 00-7.5-1.5" />
                        </svg>
                    {:else}
                        <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                        </svg>
                    {/if}
                    <span class="font-semibold">{weatherConditionSummary}</span>
                {/if}
                {#if hasTemperature}
                    <span class="font-bold text-slate-700 dark:text-slate-200">{formatTemperature(detection.temperature, temperatureUnit)}</span>
                {/if}
            </div>
        {/if}

        <!-- Compact metadata line: date + camera -->
        <div class="mt-auto flex items-center gap-1.5 text-[11px] text-slate-500 dark:text-slate-400 font-medium truncate">
            <span>{formatDate(detection.detection_time)}</span>
            <span class="text-slate-300 dark:text-slate-600">&middot;</span>
            <span class="truncate">{detection.camera_name}</span>
        </div>
    </div>
    {#if selectionMode && selected && !analysisActive}
        <div class="absolute inset-0 z-40 overflow-hidden rounded-3xl pointer-events-none">
            <div class="absolute inset-0 bg-cyan-500/24 backdrop-blur-sm"></div>
            <div class="absolute inset-0 bg-gradient-to-br from-cyan-300/22 via-sky-400/14 to-blue-500/22"></div>
            <div class="absolute inset-0 bg-slate-950/10 dark:bg-slate-950/22"></div>
            <div class="absolute inset-0 z-50 flex items-center justify-center">
                <svg class="h-16 w-16 text-white drop-shadow-[0_6px_18px_rgba(8,47,73,0.45)]" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
                    <path d="M5 10.5l3.2 3.2L15 7" stroke-linecap="round" stroke-linejoin="round"></path>
                </svg>
            </div>
        </div>
    {/if}
    </div>
</div>
