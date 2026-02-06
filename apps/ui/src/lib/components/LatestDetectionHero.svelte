<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';

    import { getBirdNames } from '../naming';
    import { formatTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        hideProgress?: boolean;
    }

    let { detection, onclick, hideProgress = false }: Props = $props();

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
    let hasWeather = $derived(
        detection.temperature !== undefined && detection.temperature !== null ||
        !!detection.weather_condition ||
        detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null ||
        detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null ||
        detection.weather_precipitation !== undefined && detection.weather_precipitation !== null ||
        detection.weather_rain !== undefined && detection.weather_rain !== null ||
        detection.weather_snowfall !== undefined && detection.weather_snowfall !== null
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

    function formatPrecip(value?: number | null): string {
        if (value === null || value === undefined || Number.isNaN(value)) return '';
        if (value < 0.1) return `${value.toFixed(2)}mm`;
        if (value < 1) return `${value.toFixed(1)}mm`;
        return `${value.toFixed(0)}mm`;
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

    <!-- Gradient Overlay -->
    <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent"></div>

    <!-- Content Overlay -->
    <div class="absolute bottom-0 left-0 right-0 p-6 sm:p-8 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-2">
                <span class="px-2 py-0.5 bg-teal-600 text-white text-[10px] font-bold uppercase tracking-widest rounded-md">
                    {getRelativeTime(detection.detection_time, $_)}
                </span>
                {#if detection.audio_confirmed || detection.audio_species}
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
            
            {#if detection.audio_species && detection.audio_species !== detection.display_name}
                <div class="mt-3 flex items-center gap-2 text-blue-300 text-xs font-bold uppercase tracking-widest bg-blue-500/10 border border-blue-500/20 px-3 py-1.5 rounded-xl w-fit backdrop-blur-md">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                    </svg>
                    {$_('dashboard.hero.heard', { values: { species: detection.audio_species } })}
                </div>
            {/if}

            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mt-4 text-white/80 text-xs sm:text-sm font-medium">
                <span class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-teal-400"></span>
                    {formatTime(detection.detection_time)}
                </span>
                <span class="flex items-center gap-1.5">
                    📷 {detection.camera_name}
                </span>
                {#if detection.temperature !== undefined && detection.temperature !== null}
                    <span class="flex items-center gap-1.5">
                        🌡️ {formatTemperature(detection.temperature, settingsStore.settings?.location_temperature_unit as any)}
                    </span>
                {/if}
            </div>

            {#if hasWeather}
                <div class="flex flex-wrap items-center gap-2 mt-3">
                    {#if detection.weather_condition}
                        <span class="px-2 py-0.5 bg-slate-800/70 text-white/80 text-[10px] font-bold uppercase tracking-widest rounded-md">
                            {detection.weather_condition}
                        </span>
                    {/if}
                    {#if (detection.weather_rain ?? 0) > 0 || (detection.weather_precipitation ?? 0) > 0}
                        <span class="px-2 py-0.5 bg-blue-500/20 text-blue-200 text-[10px] font-bold uppercase tracking-widest rounded-md">
                            {formatPrecip((detection.weather_rain ?? 0) + (detection.weather_precipitation ?? 0))}
                        </span>
                    {/if}
                    {#if (detection.weather_snowfall ?? 0) > 0}
                        <span class="px-2 py-0.5 bg-indigo-500/20 text-indigo-200 text-[10px] font-bold uppercase tracking-widest rounded-md">
                            {formatPrecip(detection.weather_snowfall)}
                        </span>
                    {/if}
                    {#if detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null}
                        <span class="px-2 py-0.5 bg-slate-700/60 text-slate-200 text-[10px] font-bold uppercase tracking-widest rounded-md">
                            {Math.round(detection.weather_cloud_cover)}% {$_('detection.weather_cloud')}
                        </span>
                    {/if}
                    {#if detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null}
                        <span class="px-2 py-0.5 bg-emerald-500/20 text-emerald-200 text-[10px] font-bold uppercase tracking-widest rounded-md">
                            {Math.round(detection.weather_wind_speed)} km/h {$_('detection.weather_wind')}
                        </span>
                    {/if}
                </div>
            {/if}
        </div>

        <div class="flex items-center gap-3 self-start sm:self-auto shrink-0">
            {#if !detection.manual_tagged}
                <div class="flex flex-col items-center justify-center w-16 h-16 rounded-full bg-slate-900/60 border border-white/20 text-white shadow-lg">
                    <span class="text-lg font-black">{((detection.score || 0) * 100).toFixed(0)}</span>
                    <span class="text-[8px] font-bold uppercase opacity-60">{$_('dashboard.hero.conf')}</span>
                </div>
            {/if}
            <div class="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-xs font-bold uppercase tracking-widest rounded-full transition-colors shadow-lg">
                {$_('dashboard.hero.view_details')}
            </div>
        </div>
    </div>
</div>
