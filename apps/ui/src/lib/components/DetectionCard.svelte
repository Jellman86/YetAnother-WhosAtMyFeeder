<script lang="ts">
    import type { Detection } from '../api';
    import { getSnapshotUrl } from '../api';

    interface Props {
        detection: Detection;
        onclick?: () => void;
    }

    let { detection, onclick }: Props = $props();

    let imageError = $state(false);
    let imageLoaded = $state(false);

    // Reset image loading state when detection changes
    $effect(() => {
        // Access detection.frigate_event to track changes
        const _eventId = detection.frigate_event;
        imageError = false;
        imageLoaded = false;
    });

    // Derive the image URL from the detection
    let imageUrl = $derived(getSnapshotUrl(detection.frigate_event));

    function formatTime(dateString: string): string {
        try {
            const date = new Date(dateString);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    }

    function formatDate(dateString: string): string {
        try {
            const date = new Date(dateString);
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);

            if (date.toDateString() === today.toDateString()) {
                return 'Today';
            } else if (date.toDateString() === yesterday.toDateString()) {
                return 'Yesterday';
            }
            return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
        } catch {
            return '';
        }
    }

    function getConfidenceColor(score: number): string {
        if (score >= 0.9) return 'bg-emerald-500';
        if (score >= 0.7) return 'bg-amber-500';
        return 'bg-red-500';
    }
</script>

<button
    type="button"
    {onclick}
    class="group bg-white dark:bg-slate-800/80 rounded-2xl shadow-card dark:shadow-card-dark
           hover:shadow-card-hover dark:hover:shadow-card-dark-hover
           border border-slate-200/80 dark:border-slate-700/50
           overflow-hidden transition-all duration-300 hover:-translate-y-1 hover:border-brand-300 dark:hover:border-brand-600
           text-left w-full cursor-pointer backdrop-blur-sm"
>
    <!-- Image Container -->
    <div class="relative aspect-[4/3] bg-slate-100 dark:bg-slate-700 overflow-hidden">
        {#if !imageError}
            <img
                src={imageUrl}
                alt={detection.display_name}
                class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105
                       {imageLoaded ? 'opacity-100' : 'opacity-0'}"
                onload={() => imageLoaded = true}
                onerror={() => imageError = true}
            />
        {/if}

        {#if !imageLoaded || imageError}
            <div class="absolute inset-0 flex items-center justify-center text-4xl">
                🐦
            </div>
        {/if}

        <!-- Confidence Badge -->
        <div class="absolute top-2 right-2 flex items-center gap-1.5 px-2 py-1 rounded-full
                    bg-black/60 backdrop-blur-sm text-white text-xs font-medium">
            <span class="w-1.5 h-1.5 rounded-full {getConfidenceColor(detection.score)}"></span>
            {(detection.score * 100).toFixed(0)}%
        </div>

        <!-- Camera Badge -->
        <div class="absolute bottom-2 left-2 px-2 py-1 rounded-full
                    bg-black/60 backdrop-blur-sm text-white text-xs">
            📷 {detection.camera_name}
        </div>
    </div>

    <!-- Content -->
    <div class="p-4">
        <h3 class="text-lg font-semibold text-slate-900 dark:text-white truncate mb-1"
            title={detection.display_name}>
            {detection.display_name}
        </h3>

        <div class="flex items-center justify-between text-sm text-slate-500 dark:text-slate-400">
            <span>{formatDate(detection.detection_time)}</span>
            <span>{formatTime(detection.detection_time)}</span>
        </div>
    </div>
</button>