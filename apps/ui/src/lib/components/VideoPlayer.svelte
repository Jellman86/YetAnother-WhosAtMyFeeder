<script lang="ts">
    import { getClipUrl } from '../api';

    interface Props {
        frigateEvent: string;
        onClose: () => void;
    }

    let { frigateEvent, onClose }: Props = $props();

    let videoError = $state(false);
    let videoForbidden = $state(false);
    let videoLoaded = $state(false);
    let retryCount = $state(0);
    let clipUrl = $state(getClipUrl(frigateEvent));
    const maxRetries = 2;

    function handleKeydown(event: KeyboardEvent) {
        if (event.key === 'Escape') {
            onClose();
        }
    }

    function handleBackdropClick(event: MouseEvent) {
        if (event.target === event.currentTarget) {
            onClose();
        }
    }

    function handleError(e: Event & { currentTarget: EventTarget & HTMLVideoElement }) {
        // Check if the error is due to 403 (we can't check status code directly on video error event easily, 
        // but if we fail immediately it's likely. 
        // For a more robust check we would do a HEAD request first, but for now we'll rely on the 
        // fact that 403s usually trigger a quick error).
        // Actually, let's keep it simple: if it errors, we show the error.
        videoError = true;
    }

    function retryLoad() {
        if (retryCount < maxRetries) {
            retryCount++;
            videoError = false;
            videoForbidden = false;
            videoLoaded = false;
            // Add cache buster to force reload
            clipUrl = getClipUrl(frigateEvent) + `?retry=${retryCount}`;
        }
    }
    
    // Check if clip is allowed/exists when mounting
    $effect(() => {
        fetch(clipUrl, { method: 'HEAD' })
            .then(res => {
                if (res.status === 403) {
                    videoForbidden = true;
                    videoError = true;
                }
            })
            .catch(() => { /* ignore, let video tag handle it */ });
    });
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Modal Backdrop -->
<div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
    onclick={handleBackdropClick}
    role="dialog"
    aria-modal="true"
    aria-label="Video player"
>
    <div class="relative w-full max-w-4xl mx-4">
        <!-- Close Button -->
        <button
            type="button"
            onclick={onClose}
            class="absolute -top-12 right-0 p-2 text-white/80 hover:text-white
                   transition-colors duration-200 focus:outline-none focus:ring-2
                   focus:ring-white/50 rounded-lg"
            aria-label="Close video"
        >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>

        <!-- Video Container -->
        <div class="relative bg-black rounded-xl overflow-hidden shadow-2xl min-h-[300px] aspect-video flex items-center justify-center">
            {#if videoError}
                <div class="flex flex-col items-center justify-center py-16 text-white/60">
                    {#if videoForbidden}
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-16 h-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                        </svg>
                        <p class="text-lg">Clip Fetching Disabled</p>
                        <p class="text-sm mt-1">Enable "Fetch Video Clips" in Settings to view this video.</p>
                    {:else}
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-16 h-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                        </svg>
                        <p class="text-lg">Video unavailable</p>
                        <p class="text-sm mt-1">The clip could not be loaded</p>
                        {#if retryCount < maxRetries}
                            <button
                                onclick={retryLoad}
                                class="mt-4 px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg
                                    transition-colors duration-200 flex items-center gap-2"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                                Retry
                            </button>
                        {/if}
                    {/if}
                </div>
            {:else}
                <!-- Loading spinner - shows until video is ready -->
                {#if !videoLoaded}
                    <div class="absolute inset-0 flex items-center justify-center bg-black z-10">
                        <div class="flex flex-col items-center gap-3">
                            <div class="w-12 h-12 border-4 border-teal-500/30 border-t-teal-500 rounded-full animate-spin"></div>
                            <p class="text-white/60 text-sm">Loading video...</p>
                        </div>
                    </div>
                {/if}

                <video
                    controls
                    autoplay
                    playsinline
                    class="w-full h-full object-contain"
                    onloadeddata={() => videoLoaded = true}
                    onerror={() => videoError = true}
                >
                    <source src={clipUrl} type="video/mp4" />
                    <track kind="captions" />
                    Your browser does not support video playback.
                </video>
            {/if}
        </div>

        <!-- Instructions -->
        <p class="text-center text-white/50 text-sm mt-4">
            Press <kbd class="px-2 py-0.5 bg-white/10 rounded">Esc</kbd> or click outside to close
        </p>
    </div>
</div>
