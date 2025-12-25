<script lang="ts">
    import { getClipUrl } from '../api';

    interface Props {
        frigateEvent: string;
        onClose: () => void;
    }

    let { frigateEvent, onClose }: Props = $props();

    let videoError = $state(false);
    let videoLoaded = $state(false);

    const clipUrl = getClipUrl(frigateEvent);

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
</script>

<svelte:window on:keydown={handleKeydown} />

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
        <div class="relative bg-black rounded-xl overflow-hidden shadow-2xl">
            {#if !videoLoaded && !videoError}
                <!-- Loading spinner -->
                <div class="absolute inset-0 flex items-center justify-center">
                    <div class="w-12 h-12 border-4 border-teal-500/30 border-t-teal-500 rounded-full animate-spin"></div>
                </div>
            {/if}

            {#if videoError}
                <div class="flex flex-col items-center justify-center py-16 text-white/60">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-16 h-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <p class="text-lg">Video unavailable</p>
                    <p class="text-sm mt-1">The clip could not be loaded</p>
                </div>
            {:else}
                <!-- eslint-disable-next-line svelte/valid-compile -->
                <video
                    controls
                    autoplay
                    class="w-full max-h-[80vh] {videoLoaded ? '' : 'opacity-0 absolute'}"
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
