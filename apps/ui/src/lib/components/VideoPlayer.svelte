<script lang="ts">
    import { getClipUrl } from '../api';

    interface Props {
        frigateEvent: string;
        onClose: () => void;
    }

    let { frigateEvent, onClose }: Props = $props();

    let videoError = $state(false);
    let videoForbidden = $state(false);
    let retryCount = $state(0);
    let clipUrlBase = $derived(getClipUrl(frigateEvent));
    let clipUrl = $state("");
    
    $effect(() => {
        if (retryCount > 0) {
            const separator = clipUrlBase.includes('?') ? '&' : '?';
            clipUrl = `${clipUrlBase}${separator}retry=${retryCount}`;
        } else {
            clipUrl = clipUrlBase;
        }
    });

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
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/90 backdrop-blur-md p-4 sm:p-6"
    onclick={handleBackdropClick}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
    aria-label="Video player"
    tabindex="-1"
>
    <div class="relative w-full max-w-5xl mx-auto flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
        <!-- Close Button (Mobile Friendly) -->
        <button
            type="button"
            onclick={onClose}
            class="absolute -top-12 right-0 sm:-right-12 p-2 text-white/70 hover:text-white
                   transition-colors duration-200 focus:outline-none focus:ring-2
                   focus:ring-white/30 rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-sm"
            aria-label="Close video"
        >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>

        <!-- Video Container -->
        <div class="relative bg-black rounded-2xl overflow-hidden shadow-2xl ring-1 ring-white/10 aspect-video flex items-center justify-center">
            {#if videoError}
                <div class="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col items-center justify-center text-center p-8">
                    {#if videoForbidden}
                        <div class="w-20 h-20 bg-amber-500/10 rounded-full flex items-center justify-center mb-6">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                            </svg>
                        </div>
                        <h3 class="text-xl font-semibold text-white mb-2">Clip Fetching Disabled</h3>
                        <p class="text-slate-400 max-w-sm">
                            Enable "Fetch Video Clips" in the Settings menu to view this recording.
                        </p>
                    {:else}
                        <div class="w-20 h-20 bg-red-500/10 rounded-full flex items-center justify-center mb-6">
                            <svg xmlns="http://www.w3.org/2000/svg" class="w-10 h-10 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                        </div>
                        <h3 class="text-xl font-semibold text-white mb-2">Video Unavailable</h3>
                        <p class="text-slate-400 max-w-sm mb-6">
                            The recording could not be loaded from Frigate. It may have been deleted or is not yet available.
                        </p>
                        {#if retryCount < maxRetries}
                            <button
                                onclick={retryLoad}
                                class="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-full
                                    transition-all duration-200 flex items-center gap-2 font-medium group"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 transition-transform group-hover:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                                Try Again
                            </button>
                        {/if}
                    {/if}
                </div>
            {:else}
                <video
                    controls
                    autoplay
                    playsinline
                    class="w-full h-full object-contain"
                    onerror={(e) => handleError(e as any)}
                >
                    <source src={clipUrl} type="video/mp4" />
                    <track kind="captions" />
                    Your browser does not support video playback.
                </video>
            {/if}
        </div>
    </div>
</div>
