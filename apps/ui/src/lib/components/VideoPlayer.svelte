<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import Plyr from 'plyr';
    import 'plyr/dist/plyr.css';
    import { getClipPreviewTrackCandidates, getClipUrl } from '../api';

    interface Props {
        frigateEvent: string;
        onClose: () => void;
    }

    let { frigateEvent, onClose }: Props = $props();

    let videoElement = $state<HTMLVideoElement | null>(null);
    let player = $state<Plyr | null>(null);
    let initializing = $state(false);
    let videoError = $state(false);
    let videoForbidden = $state(false);
    let retryCount = $state(0);
    let thumbnailTrackUrl = $state<string | null>(null);
    let thumbnailTrackCheckedFor = $state<string | null>(null);

    let clipUrlBase = $derived(getClipUrl(frigateEvent));
    let clipUrl = $state('');

    let mounted = false;
    let configureToken = 0;

    const maxRetries = 2;

    $effect(() => {
        if (retryCount > 0) {
            const separator = clipUrlBase.includes('?') ? '&' : '?';
            clipUrl = `${clipUrlBase}${separator}retry=${retryCount}`;
        } else {
            clipUrl = clipUrlBase;
        }
    });

    function handleBackdropClick(event: MouseEvent) {
        if (event.target === event.currentTarget) {
            onClose();
        }
    }

    function handleWindowKeydown(event: KeyboardEvent) {
        if (event.key === 'Escape') {
            onClose();
        }
    }

    function destroyPlayer() {
        if (player) {
            player.destroy();
            player = null;
        }
    }

    async function resolveThumbnailTrackUrl(eventId: string): Promise<string | null> {
        if (thumbnailTrackCheckedFor === eventId) {
            return thumbnailTrackUrl;
        }

        thumbnailTrackCheckedFor = eventId;
        thumbnailTrackUrl = null;

        const candidates = getClipPreviewTrackCandidates(eventId);
        for (const candidate of candidates) {
            try {
                const response = await fetch(candidate, { method: 'HEAD' });
                if (response.ok) {
                    thumbnailTrackUrl = candidate;
                    return candidate;
                }
            } catch {
                // Ignore and try next candidate.
            }
        }

        return null;
    }

    function createPlyr(previewSrc: string | null) {
        if (!videoElement) return;

        destroyPlayer();

        player = new Plyr(videoElement, {
            autoplay: true,
            clickToPlay: true,
            hideControls: false,
            keyboard: { focused: true, global: false },
            seekTime: 5,
            controls: [
                'play-large',
                'play',
                'progress',
                'current-time',
                'duration',
                'mute',
                'volume',
                'captions',
                'settings',
                'pip',
                'airplay',
                'fullscreen'
            ],
            settings: ['captions', 'quality', 'speed', 'loop'],
            speed: {
                selected: 1,
                options: [0.5, 0.75, 1, 1.25, 1.5, 2]
            },
            tooltips: {
                controls: true,
                seek: true
            },
            previewThumbnails: previewSrc
                ? {
                    enabled: true,
                    src: previewSrc
                }
                : { enabled: false }
        } as any);

        player.on('ready', () => {
            initializing = false;
        });

        player.on('error', () => {
            videoError = true;
            initializing = false;
        });

        player.source = {
            type: 'video',
            title: 'Detection clip',
            sources: [{ src: clipUrl, type: 'video/mp4' }]
        };

        const playResult = player.play();
        if (playResult && typeof playResult.then === 'function') {
            void playResult.catch(() => {
                // Browser autoplay policies can block this; controls stay usable.
            });
        }
    }

    async function configurePlayer() {
        if (!mounted || !videoElement || !clipUrl) return;

        const token = ++configureToken;
        initializing = true;
        videoError = false;
        videoForbidden = false;

        destroyPlayer();

        try {
            const response = await fetch(clipUrl, { method: 'HEAD' });
            if (token !== configureToken) return;
            if (response.status === 403) {
                videoForbidden = true;
                videoError = true;
                initializing = false;
                return;
            }
        } catch {
            // Continue and let Plyr/video element emit a concrete error if unavailable.
        }

        const previewSrc = await resolveThumbnailTrackUrl(frigateEvent);
        if (token !== configureToken) return;

        createPlyr(previewSrc);
    }

    function retryLoad() {
        if (retryCount < maxRetries) {
            retryCount += 1;
            videoError = false;
            videoForbidden = false;
            initializing = true;
        }
    }

    onMount(() => {
        mounted = true;
        void configurePlayer();
    });

    $effect(() => {
        if (!mounted) return;
        clipUrl;
        frigateEvent;
        void configurePlayer();
    });

    onDestroy(() => {
        configureToken += 1;
        destroyPlayer();
    });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/90 backdrop-blur-md p-4 sm:p-6"
    onclick={handleBackdropClick}
    onkeydown={(event) => event.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
    aria-label="Video player"
    tabindex="-1"
>
    <div class="relative w-full max-w-4xl mx-auto animate-in fade-in zoom-in-95 duration-200">
        <button
            type="button"
            onclick={onClose}
            class="absolute top-3 right-3 z-20 p-2 text-white/80 hover:text-white transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-white/40 rounded-full bg-black/35 hover:bg-black/50"
            aria-label="Close video"
        >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>

        <div class="rounded-2xl overflow-hidden ring-1 ring-white/10 bg-black shadow-2xl">
            {#if videoError}
                <div class="aspect-video bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex flex-col items-center justify-center text-center p-8">
                    {#if videoForbidden}
                        <h3 class="text-xl font-semibold text-white mb-2">Clip Fetching Disabled</h3>
                        <p class="text-slate-400 max-w-sm">
                            Enable "Fetch Video Clips" in Settings to view this recording.
                        </p>
                    {:else}
                        <h3 class="text-xl font-semibold text-white mb-2">Video Unavailable</h3>
                        <p class="text-slate-400 max-w-sm mb-6">
                            The recording could not be loaded from Frigate. It may have been deleted or is not yet available.
                        </p>
                        {#if retryCount < maxRetries}
                            <button
                                type="button"
                                onclick={retryLoad}
                                class="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-full transition-all duration-200"
                            >
                                Try Again
                            </button>
                        {/if}
                    {/if}
                </div>
            {:else}
                <div class="relative aspect-video bg-black">
                    <video
                        bind:this={videoElement}
                        controls
                        autoplay
                        playsinline
                        preload="metadata"
                        class="w-full h-full"
                    >
                        <source src={clipUrl} type="video/mp4" />
                        <track kind="captions" />
                        Your browser does not support video playback.
                    </video>

                    {#if initializing}
                        <div class="absolute inset-0 grid place-items-center bg-black/45 text-slate-200 text-sm">
                            Preparing player...
                        </div>
                    {/if}
                </div>
            {/if}
        </div>

        {#if !videoError}
            <div class="mt-2 text-[11px] text-slate-300 px-1 flex items-center justify-between gap-2">
                <span>Shortcuts: space/K play/pause, arrows seek</span>
                <span>{thumbnailTrackUrl ? 'Timeline previews enabled' : 'Timeline previews unavailable for this clip'}</span>
            </div>
        {/if}
    </div>
</div>

<style>
    :global(.plyr) {
        --plyr-color-main: #14b8a6;
        --plyr-control-radius: 10px;
        --plyr-control-icon-size: 14px;
        --plyr-tooltip-background: rgba(15, 23, 42, 0.95);
        --plyr-tooltip-color: #f8fafc;
        --plyr-video-control-color: #e2e8f0;
        --plyr-video-controls-background: linear-gradient(to top, rgba(2, 6, 23, 0.9), rgba(2, 6, 23, 0.35));
    }

    :global(.plyr--video .plyr__controls) {
        padding: 8px;
        gap: 4px;
    }

    :global(.plyr--full-ui input[type='range']) {
        color: #14b8a6;
    }
</style>
