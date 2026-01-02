<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';

    interface Props {
        detection: Detection;
        onclick?: () => void;
    }

    let { detection, onclick }: Props = $props();

    function formatTime(dateString: string): string {
        try {
            const date = new Date(dateString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }
</script>

<button 
    onclick={onclick}
    class="relative w-full aspect-video sm:aspect-auto sm:h-80 rounded-2xl overflow-hidden group shadow-xl border-4 border-white dark:border-slate-800"
>
    <!-- Background Image -->
    <img 
        src={getThumbnailUrl(detection.frigate_event)} 
        alt={detection.display_name}
        class="w-full h-full object-cover transition-transform duration-1000 group-hover:scale-105"
    />

    <!-- Gradient Overlay -->
    <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent"></div>

    <!-- Content Overlay -->
    <div class="absolute bottom-0 left-0 right-0 p-6 sm:p-8 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
            <div class="flex items-center gap-2 mb-2">
                <span class="px-2 py-0.5 bg-teal-500 text-white text-[10px] font-bold uppercase tracking-widest rounded-md animate-pulse">
                    Just Discovered
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
            <h2 class="text-3xl sm:text-4xl font-black text-white drop-shadow-lg tracking-tight">
                {detection.display_name}
            </h2>
            <div class="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2 text-white/80 text-xs sm:text-sm font-medium">
                <span class="flex items-center gap-1.5">
                    <span class="w-2 h-2 rounded-full bg-teal-400"></span>
                    {formatTime(detection.detection_time)}
                </span>
                <span class="flex items-center gap-1.5">
                    📷 {detection.camera_name}
                </span>
                {#if detection.temperature !== undefined && detection.temperature !== null}
                    <span class="flex items-center gap-1.5">
                        🌡️ {detection.temperature.toFixed(1)}°C
                    </span>
                {/if}
            </div>
        </div>

        <div class="flex items-center gap-3 self-start sm:self-auto">
            <div class="flex flex-col items-center justify-center w-16 h-16 rounded-full bg-white/10 backdrop-blur-md border border-white/20 text-white">
                <span class="text-lg font-black">{(detection.score * 100).toFixed(0)}</span>
                <span class="text-[8px] font-bold uppercase opacity-60">Conf</span>
            </div>
            <div class="px-4 py-2 bg-teal-500 hover:bg-teal-600 text-white text-xs font-bold uppercase tracking-widest rounded-full transition-colors shadow-lg">
                View Details
            </div>
        </div>
    </div>
</button>
