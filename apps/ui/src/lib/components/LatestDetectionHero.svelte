<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { settingsStore } from '../stores/settings';
    import { detectionsStore } from '../stores/detections.svelte';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';

    import { getBirdNames } from '../naming';

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
        const showCommon = $settingsStore?.display_common_names ?? true;
        const preferSci = $settingsStore?.scientific_name_primary ?? false;
        return getBirdNames(detection, showCommon, preferSci);
    });

    let primaryName = $derived(naming.primary);
    let subName = $derived(naming.secondary);

    function formatTime(dateString: string): string {
        try {
            const date = new Date(dateString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }

    function getRelativeTime(dateString: string): string {
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

            if (diffInSeconds < 3600) { // Less than 1 hour
                return 'Just Discovered';
            }
            
            const hours = Math.floor(diffInSeconds / 3600);
            if (hours < 24) {
                return `${hours} hour${hours > 1 ? 's' : ''} ago`;
            }

            const days = Math.floor(diffInSeconds / 86400);
            if (days === 1) return '1 day ago';
            return `${days} days ago`;
        } catch {
            return 'Just Discovered';
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

    <!-- Gradient Overlay -->
    <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent"></div>

    <!-- Content Overlay -->
    <div class="absolute bottom-0 left-0 right-0 p-6 sm:p-8 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-2">
                <span class="px-2 py-0.5 bg-teal-500 text-white text-[10px] font-bold uppercase tracking-widest rounded-md">
                    {getRelativeTime(detection.detection_time)}
                </span>
                {#if detection.audio_confirmed}
                    <span class="px-2 py-0.5 bg-blue-500 text-white text-[10px] font-bold uppercase tracking-widest rounded-md flex items-center gap-1">
                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                        </svg>
                        Audio Confirmed
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
                    Heard: {detection.audio_species}
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
                        🌡️ {detection.temperature?.toFixed(1)}°C
                    </span>
                {/if}
            </div>
        </div>

        <div class="flex items-center gap-3 self-start sm:self-auto shrink-0">
            <div class="flex flex-col items-center justify-center w-16 h-16 rounded-full bg-slate-900/60 border border-white/20 text-white shadow-lg">
                <span class="text-lg font-black">{((detection.score || 0) * 100).toFixed(0)}</span>
                <span class="text-[8px] font-bold uppercase opacity-60">Conf</span>
            </div>
            <div class="px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white text-xs font-bold uppercase tracking-widest rounded-full transition-colors shadow-lg">
                View Details
            </div>
        </div>
    </div>
</div>