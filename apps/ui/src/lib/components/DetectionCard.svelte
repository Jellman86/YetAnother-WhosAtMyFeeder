<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';

    interface Props {
        detection: Detection;
        onclick?: () => void;
    }

    let { detection, onclick }: Props = $props();

    let imageError = $state(false);
    let imageLoaded = $state(false);
    let cardElement = $state<HTMLElement | null>(null);
    let isVisible = $state(false);

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
    bind:this={cardElement}
    {onclick}
    class="group bg-white dark:bg-slate-800/80 rounded-2xl shadow-card dark:shadow-card-dark
           hover:shadow-lg hover:shadow-teal-500/10 dark:hover:shadow-teal-400/5
           border border-slate-200/80 dark:border-slate-700/50
           overflow-hidden transition-all duration-300 ease-out
           hover:-translate-y-1.5 hover:border-teal-300 dark:hover:border-teal-600
           text-left w-full cursor-pointer backdrop-blur-sm
           focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900"
>
    <!-- Image Container -->
    <div class="relative aspect-[4/3] bg-slate-100 dark:bg-slate-700 overflow-hidden">
        {#if !imageError && isVisible}
            <!-- Skeleton while loading -->
            {#if !imageLoaded}
                <div class="absolute inset-0 bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200
                            dark:from-slate-700 dark:via-slate-600 dark:to-slate-700 animate-shimmer"
                     style="background-size: 200% 100%"></div>
            {/if}
            <img
                src={getThumbnailUrl(detection.frigate_event)}
                alt={detection.display_name}
                class="w-full h-full object-cover transition-all duration-500
                       group-hover:scale-110 group-hover:brightness-105
                       {imageLoaded ? 'opacity-100' : 'opacity-0'}"
                onload={() => imageLoaded = true}
                onerror={() => imageError = true}
            />
        {:else if imageError}
            <div class="absolute inset-0 flex items-center justify-center text-4xl bg-slate-50 dark:bg-slate-700">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 text-slate-300 dark:text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        {:else}
            <!-- Placeholder before visible -->
            <div class="absolute inset-0 bg-slate-100 dark:bg-slate-700"></div>
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