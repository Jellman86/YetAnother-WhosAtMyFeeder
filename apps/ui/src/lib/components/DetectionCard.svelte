<script lang="ts">
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import VideoPlayer from './VideoPlayer.svelte';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onReclassify?: (detection: Detection) => void;
        onRetag?: (detection: Detection) => void;
    }

    let { detection, onclick, onReclassify, onRetag }: Props = $props();

    let imageError = $state(false);
    let imageLoaded = $state(false);
    let cardElement = $state<HTMLElement | null>(null);
    let isVisible = $state(false);
    let showVideo = $state(false);

    // Use has_clip from detection response (no individual HEAD requests needed)
    let hasClip = $derived(detection.has_clip ?? false);

    function handleReclassifyClick(event: MouseEvent) {
        event.stopPropagation();
        onReclassify?.(detection);
    }

    function handleRetagClick(event: MouseEvent) {
        event.stopPropagation();
        onRetag?.(detection);
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

    function handlePlayClick(event: MouseEvent) {
        event.stopPropagation();
        showVideo = true;
    }

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
           focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 dark:focus:ring-offset-slate-900
           {detection.is_hidden ? 'opacity-60 hover:opacity-90 border-amber-300 dark:border-amber-700' : ''}"
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

        <!-- Hidden Badge -->
        {#if detection.is_hidden}
            <div class="absolute top-2 left-2 flex items-center gap-1 px-2 py-1 rounded-full
                        bg-amber-500/90 backdrop-blur-sm text-white text-xs font-medium">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
                Hidden
            </div>
        {/if}

        <!-- Camera Badge -->
        <div class="absolute bottom-2 left-2 px-2 py-1 rounded-full
                    bg-black/60 backdrop-blur-sm text-white text-xs">
            📷 {detection.camera_name}
        </div>

        <!-- Play Button (shows when clip is available) -->
        {#if hasClip}
            <button
                type="button"
                onclick={handlePlayClick}
                class="absolute inset-0 flex items-center justify-center
                       bg-black/0 hover:bg-black/40 transition-colors duration-200
                       group/play focus:outline-none"
                aria-label="Play video clip"
            >
                <div class="w-14 h-14 rounded-full bg-white/90 dark:bg-slate-800/90
                            flex items-center justify-center shadow-lg
                            opacity-0 group-hover:opacity-100 group-focus/play:opacity-100
                            transform scale-75 group-hover:scale-100 group-focus/play:scale-100
                            transition-all duration-200">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6 text-teal-600 dark:text-teal-400 ml-1" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M8 5v14l11-7z"/>
                    </svg>
                </div>
            </button>
        {/if}

        <!-- Action Buttons Overlay (bottom-right) -->
        {#if onReclassify || onRetag}
            <div class="absolute bottom-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                {#if onReclassify}
                    <button
                        type="button"
                        onclick={handleReclassifyClick}
                        class="w-8 h-8 rounded-full bg-black/60 backdrop-blur-sm text-white
                               hover:bg-teal-500 transition-colors duration-150
                               flex items-center justify-center shadow-lg"
                        title="Re-run bird classifier"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                {/if}
                {#if onRetag}
                    <button
                        type="button"
                        onclick={handleRetagClick}
                        class="w-8 h-8 rounded-full bg-black/60 backdrop-blur-sm text-white
                               hover:bg-amber-500 transition-colors duration-150
                               flex items-center justify-center shadow-lg"
                        title="Manual retag"
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                    </button>
                {/if}
            </div>
        {/if}
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

<!-- Video Player Modal -->
{#if showVideo}
    <VideoPlayer
        frigateEvent={detection.frigate_event}
        onClose={() => showVideo = false}
    />
{/if}