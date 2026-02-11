<script lang="ts">
    import { onDestroy } from 'svelte';
    import { getClipUrl } from '../api';

    interface Props {
        frigateEvent: string;
        onClose: () => void;
    }

    let { frigateEvent, onClose }: Props = $props();

    let videoError = $state(false);
    let videoForbidden = $state(false);
    let retryCount = $state(0);
    let videoElement = $state<HTMLVideoElement | null>(null);
    let duration = $state(0);
    let currentTime = $state(0);
    let timelineTime = $state(0);
    let userScrubbing = $state(false);
    let generatingFrames = $state(false);
    let timelineFrameError = $state<string | null>(null);
    let timelineFrames = $state<Array<{ time: number; dataUrl: string }>>([]);
    let frameGenerationToken = 0;
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

    function formatTime(seconds: number): string {
        if (!Number.isFinite(seconds) || seconds <= 0) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    function handleLoadedMetadata(event: Event & { currentTarget: EventTarget & HTMLVideoElement }) {
        duration = Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0;
        currentTime = 0;
        timelineTime = 0;
    }

    function handleTimeUpdate(event: Event & { currentTarget: EventTarget & HTMLVideoElement }) {
        currentTime = event.currentTarget.currentTime || 0;
        if (!userScrubbing) {
            timelineTime = currentTime;
        }
    }

    function seekTo(value: number) {
        if (!videoElement) return;
        const next = Math.max(0, Math.min(duration || 0, value));
        videoElement.currentTime = next;
        currentTime = next;
        timelineTime = next;
    }

    function handleTimelineInput(event: Event & { currentTarget: EventTarget & HTMLInputElement }) {
        userScrubbing = true;
        timelineTime = Number(event.currentTarget.value);
    }

    function handleTimelineCommit(event: Event & { currentTarget: EventTarget & HTMLInputElement }) {
        const next = Number(event.currentTarget.value);
        seekTo(next);
        userScrubbing = false;
    }

    async function generateTimelineFrames(url: string, token: number) {
        if (!url) return;
        generatingFrames = true;
        timelineFrameError = null;
        timelineFrames = [];

        const sampleVideo = document.createElement('video');
        sampleVideo.preload = 'auto';
        sampleVideo.muted = true;
        sampleVideo.playsInline = true;
        sampleVideo.crossOrigin = 'anonymous';
        sampleVideo.src = url;

        const waitForEvent = (target: EventTarget, eventName: string, timeoutMs = 8000) =>
            new Promise<void>((resolve, reject) => {
                let timer: number | null = null;
                const onDone = () => {
                    target.removeEventListener(eventName, onDone as EventListener);
                    target.removeEventListener('error', onError as EventListener);
                    if (timer) window.clearTimeout(timer);
                    resolve();
                };
                const onError = () => {
                    target.removeEventListener(eventName, onDone as EventListener);
                    target.removeEventListener('error', onError as EventListener);
                    if (timer) window.clearTimeout(timer);
                    reject(new Error(`Failed waiting for ${eventName}`));
                };
                target.addEventListener(eventName, onDone as EventListener, { once: true });
                target.addEventListener('error', onError as EventListener, { once: true });
                timer = window.setTimeout(() => {
                    target.removeEventListener(eventName, onDone as EventListener);
                    target.removeEventListener('error', onError as EventListener);
                    reject(new Error(`Timed out waiting for ${eventName}`));
                }, timeoutMs);
            });

        try {
            await waitForEvent(sampleVideo, 'loadedmetadata');
            const localDuration = Number.isFinite(sampleVideo.duration) ? sampleVideo.duration : 0;
            if (!localDuration) {
                timelineFrameError = 'No clip metadata';
                return;
            }

            const targetFrames = Math.max(6, Math.min(14, Math.floor(localDuration / 3)));
            const canvas = document.createElement('canvas');
            canvas.width = 160;
            canvas.height = 90;
            const ctx = canvas.getContext('2d');
            if (!ctx) {
                timelineFrameError = 'Canvas unavailable';
                return;
            }

            const results: Array<{ time: number; dataUrl: string }> = [];
            for (let i = 0; i < targetFrames; i++) {
                if (token !== frameGenerationToken) return; // stale generation
                const t = targetFrames === 1 ? 0 : (localDuration * i) / (targetFrames - 1);
                sampleVideo.currentTime = Math.max(0, Math.min(localDuration, t));
                await waitForEvent(sampleVideo, 'seeked');
                ctx.drawImage(sampleVideo, 0, 0, canvas.width, canvas.height);
                results.push({
                    time: t,
                    dataUrl: canvas.toDataURL('image/jpeg', 0.7)
                });
            }

            if (token === frameGenerationToken) {
                timelineFrames = results;
            }
        } catch (e) {
            if (token === frameGenerationToken) {
                timelineFrameError = 'Frame preview unavailable';
            }
        } finally {
            if (token === frameGenerationToken) {
                generatingFrames = false;
            }
            sampleVideo.removeAttribute('src');
            sampleVideo.load();
        }
    }

    function retryLoad() {
        if (retryCount < maxRetries) {
            retryCount++;
            videoError = false;
            videoForbidden = false;
            currentTime = 0;
            timelineTime = 0;
            duration = 0;
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

    $effect(() => {
        if (!clipUrl || videoError) return;
        frameGenerationToken += 1;
        void generateTimelineFrames(clipUrl, frameGenerationToken);
    });

    onDestroy(() => {
        frameGenerationToken += 1;
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
                    bind:this={videoElement}
                    onloadedmetadata={(e) => handleLoadedMetadata(e as any)}
                    ontimeupdate={(e) => handleTimeUpdate(e as any)}
                    onerror={(e) => handleError(e as any)}
                >
                    <source src={clipUrl} type="video/mp4" />
                    <track kind="captions" />
                    Your browser does not support video playback.
                </video>
            {/if}
        </div>

        {#if !videoError}
            <div class="rounded-2xl bg-slate-900/70 ring-1 ring-white/10 p-3 sm:p-4">
                <div class="flex items-center justify-between text-[11px] text-slate-300 mb-2">
                    <span>{formatTime(userScrubbing ? timelineTime : currentTime)}</span>
                    <span>{formatTime(duration)}</span>
                </div>
                <input
                    type="range"
                    min="0"
                    max={duration || 0}
                    step="0.1"
                    value={userScrubbing ? timelineTime : currentTime}
                    oninput={(e) => handleTimelineInput(e as any)}
                    onchange={(e) => handleTimelineCommit(e as any)}
                    class="w-full accent-emerald-500"
                    aria-label="Video timeline scrubber"
                    disabled={!duration}
                />

                <div class="mt-3 min-h-[68px]">
                    {#if generatingFrames}
                        <div class="text-xs text-slate-400">Generating frame timeline…</div>
                    {:else if timelineFrameError}
                        <div class="text-xs text-slate-400">{timelineFrameError}</div>
                    {:else if timelineFrames.length}
                        <div class="grid grid-cols-6 sm:grid-cols-8 md:grid-cols-10 gap-1.5">
                            {#each timelineFrames as frame}
                                <button
                                    type="button"
                                    onclick={() => seekTo(frame.time)}
                                    class="relative group overflow-hidden rounded-md border border-white/10 hover:border-emerald-400/70 transition"
                                    title={`Jump to ${formatTime(frame.time)}`}
                                >
                                    <img src={frame.dataUrl} alt={`Frame at ${formatTime(frame.time)}`} class="w-full h-10 object-cover opacity-90 group-hover:opacity-100" />
                                    <span class="absolute bottom-0 right-0 px-1 py-0.5 text-[9px] leading-none bg-black/70 text-white rounded-tl">
                                        {formatTime(frame.time)}
                                    </span>
                                </button>
                            {/each}
                        </div>
                    {/if}
                </div>
            </div>
        {/if}
    </div>
</div>
