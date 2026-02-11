<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import Plyr from 'plyr';
    import { _ } from 'svelte-i18n';
    import 'plyr/dist/plyr.css';
    import { getClipPreviewTrackUrl, getClipUrl } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { logger } from '../utils/logger';

    interface Props {
        frigateEvent: string;
        onClose: () => void;
    }

    type ProbeCache = {
        status: number | null;
        expiresAt: number;
    };
    type PreviewState = 'checking' | 'enabled' | 'disabled' | 'unavailable' | 'deferred';

    const HEAD_CACHE_TTL_MS = 5 * 60 * 1000;
    const PROBE_TIMEOUT_MS = 5000;
    const clipHeadCache = new Map<string, ProbeCache>();
    const previewHeadCache = new Map<string, ProbeCache>();

    let { frigateEvent, onClose }: Props = $props();

    let videoElement = $state<HTMLVideoElement | null>(null);
    let modalElement = $state<HTMLDivElement | null>(null);
    let closeButton = $state<HTMLButtonElement | null>(null);
    let restoreFocusElement = $state<HTMLElement | null>(null);

    let player = $state<Plyr | null>(null);
    let initializing = $state(false);
    let videoError = $state(false);
    let videoForbidden = $state(false);
    let retryCount = $state(0);
    let thumbnailTrackUrl = $state<string | null>(null);
    let previewState = $state<PreviewState>('checking');

    let clipUrlBase = $derived(getClipUrl(frigateEvent));
    let clipUrl = $state('');
    let clipDownloadUrl = $derived(clipUrl ? `${clipUrl}${clipUrl.includes('?') ? '&' : '?'}download=1` : '');
    let canDownloadClip = $derived(!authStore.isGuest || authStore.publicAccessAllowClipDownloads);

    let mounted = false;
    let configureToken = 0;
    let initWatchdogTimer: ReturnType<typeof setTimeout> | null = null;
    let controlsProbeTimer: ReturnType<typeof setTimeout> | null = null;
    let lastConfiguredKey = '';
    let useNativeControls = $state(false);

    const maxRetries = 2;

    function sanitizedUrl(url: string): string {
        try {
            const parsed = new URL(url, window.location.origin);
            return `${parsed.pathname}${parsed.search ? '?...' : ''}`;
        } catch {
            return url;
        }
    }

    $effect(() => {
        if (retryCount > 0) {
            const separator = clipUrlBase.includes('?') ? '&' : '?';
            clipUrl = `${clipUrlBase}${separator}retry=${retryCount}`;
        } else {
            clipUrl = clipUrlBase;
        }
    });

    function cacheRead(cache: Map<string, ProbeCache>, key: string): ProbeCache | null {
        const hit = cache.get(key);
        if (!hit) return null;
        if (Date.now() >= hit.expiresAt) {
            cache.delete(key);
            return null;
        }
        return hit;
    }

    function cacheWrite(cache: Map<string, ProbeCache>, key: string, status: number | null): void {
        cache.set(key, {
            status,
            expiresAt: Date.now() + HEAD_CACHE_TTL_MS,
        });
    }

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

    function hasVisiblePlyrControls(): boolean {
        if (!modalElement) return false;
        const controls = modalElement.querySelector('.plyr__controls') as HTMLElement | null;
        if (!controls) return false;
        return controls.offsetParent !== null;
    }

    function switchToNativeFallback(reason: string): void {
        logger.warn('video_player_native_fallback', { frigateEvent, reason, clipUrl: sanitizedUrl(clipUrl) });
        if (controlsProbeTimer) {
            clearTimeout(controlsProbeTimer);
            controlsProbeTimer = null;
        }
        destroyPlayer();
        useNativeControls = true;
        previewState = 'unavailable';
        initializing = false;
    }

    async function probeUrl(
        url: string,
        cache: Map<string, ProbeCache>,
        method: 'HEAD' | 'GET' = 'HEAD'
    ): Promise<number | null> {
        const cached = cacheRead(cache, url);
        if (cached) {
            return cached.status;
        }

        const started = performance.now();
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
        try {
            let response = await fetch(url, { method, signal: controller.signal });
            // Some proxy endpoints only expose GET and return 405 for HEAD.
            // Fallback to GET to trigger preview generation and report real availability.
            if (response.status === 405 || response.status === 501) {
                logger.warn('video_player_probe_method_not_allowed', {
                    frigateEvent,
                    url: sanitizedUrl(url),
                    method,
                    status: response.status
                });
                response = await fetch(url, { method: 'GET', signal: controller.signal });
            }
            cacheWrite(cache, url, response.status);
            logger.info('video_player_probe_complete', {
                frigateEvent,
                url: sanitizedUrl(url),
                method,
                status: response.status,
                duration_ms: Number((performance.now() - started).toFixed(2))
            });
            return response.status;
        } catch (error) {
            logger.warn('video_player_probe_failed', { url: sanitizedUrl(url), method, error });
            cacheWrite(cache, url, null);
            return null;
        } finally {
            clearTimeout(timeoutId);
        }
    }

    async function resolveThumbnailTrackUrl(eventId: string): Promise<string | null> {
        previewState = 'checking';
        const trackUrl = getClipPreviewTrackUrl(eventId);
        // Use GET directly for preview track probes to avoid noisy HEAD 405 logs.
        const status = await probeUrl(trackUrl, previewHeadCache, 'GET');
        if (status && status >= 200 && status < 300) {
            thumbnailTrackUrl = trackUrl;
            previewState = 'enabled';
            logger.info('video_player_preview_state', { frigateEvent: eventId, previewState, status });
            return trackUrl;
        }
        if (status === 503) {
            previewState = 'disabled';
        } else {
            previewState = 'unavailable';
        }
        thumbnailTrackUrl = null;
        logger.info('video_player_preview_state', { frigateEvent: eventId, previewState, status });
        return null;
    }

    function createPlyr(previewSrc: string | null): boolean {
        if (!videoElement) return false;

        destroyPlayer();
        logger.info('video_player_create_plyr', {
            frigateEvent,
            clipUrl: sanitizedUrl(clipUrl),
            previewEnabled: !!previewSrc
        });
        try {
            player = new Plyr(videoElement, {
                autoplay: true,
                clickToPlay: true,
                hideControls: false,
                iconUrl: '/plyr.svg',
                blankVideo: '/plyr-blank.mp4',
                loadSprite: true,
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
                    'settings',
                    'pip',
                    'airplay',
                    'fullscreen'
                ],
                settings: ['speed', 'loop'],
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
                logger.info('video_player_ready', { frigateEvent, clipUrl: sanitizedUrl(clipUrl) });
            });

            player.on('error', (event: unknown) => {
                logger.error('video_player_runtime_error', event, { frigateEvent, clipUrl });
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
                void playResult.catch((error) => {
                    logger.info('video_player_autoplay_blocked', { frigateEvent, error });
                });
            }
            return true;
        } catch (error) {
            logger.error('video_player_create_failed', error, { frigateEvent, clipUrl: sanitizedUrl(clipUrl) });
            player = null;
            return false;
        }
    }

    async function applyPreviewWhenAvailable(token: number): Promise<void> {
        if (useNativeControls) return;
        const previewSrc = await resolveThumbnailTrackUrl(frigateEvent);
        if (token !== configureToken || videoError || useNativeControls) return;
        if (previewSrc) {
            // Never restart active playback just to add preview thumbnails.
            // Recreating Plyr can interrupt playback and look like buffering stalls.
            if (videoElement && (!videoElement.paused || videoElement.currentTime > 0.25)) {
                previewState = 'deferred';
                logger.warn('video_player_preview_skipped_active_playback', { frigateEvent });
                return;
            }

            // Only enable preview thumbnails after controls are visible and player is stable.
            if (hasVisiblePlyrControls()) {
                const previewAttached = createPlyr(previewSrc);
                if (!previewAttached) {
                    switchToNativeFallback('preview_attach_failed');
                }
            } else {
                previewState = 'unavailable';
                logger.warn('video_player_preview_skipped_controls_unavailable', { frigateEvent });
            }
        }
    }

    async function configurePlayer() {
        if (!mounted || !videoElement || !clipUrl) return;

        const token = ++configureToken;
        const started = performance.now();
        initializing = true;
        videoError = false;
        videoForbidden = false;
        useNativeControls = false;
        logger.info('video_player_configure_start', {
            frigateEvent,
            token,
            retryCount,
            clipUrl: sanitizedUrl(clipUrl)
        });

        destroyPlayer();

        const clipStatus = await probeUrl(clipUrl, clipHeadCache);
        if (token !== configureToken) return;
        logger.info('video_player_clip_probe', {
            frigateEvent,
            token,
            clipStatus
        });
        if (clipStatus === 403) {
            videoForbidden = true;
            videoError = true;
            initializing = false;
            logger.warn('video_player_clip_forbidden', { frigateEvent });
            return;
        }

        // Do not block player UI on preview probing; render controls immediately.
        const initialized = createPlyr(null);
        if (!initialized) {
            switchToNativeFallback('initial_plyr_create_failed');
            return;
        }

        if (controlsProbeTimer) {
            clearTimeout(controlsProbeTimer);
            controlsProbeTimer = null;
        }
        controlsProbeTimer = setTimeout(() => {
            if (token !== configureToken || videoError || useNativeControls) return;
            if (!hasVisiblePlyrControls()) {
                switchToNativeFallback('controls_not_visible');
            }
        }, 2500);

        void applyPreviewWhenAvailable(token);
        logger.info('video_player_configure_complete', {
            frigateEvent,
            token,
            duration_ms: Number((performance.now() - started).toFixed(2)),
            previewState
        });
    }

    function retryLoad() {
        if (retryCount < maxRetries) {
            retryCount += 1;
            videoError = false;
            videoForbidden = false;
            initializing = true;
            useNativeControls = false;
            previewState = 'checking';
            clipHeadCache.delete(clipUrl);
            if (thumbnailTrackUrl) {
                previewHeadCache.delete(thumbnailTrackUrl);
            }
        }
    }

    onMount(() => {
        mounted = true;
        logger.info('video_player_modal_open', { frigateEvent });
        restoreFocusElement = (document.activeElement as HTMLElement | null) ?? null;
        queueMicrotask(() => {
            closeButton?.focus();
        });
    });

    $effect(() => {
        if (!mounted || !clipUrl) return;
        if (!videoElement) {
            logger.debug('video_player_waiting_for_video_element', { frigateEvent });
            return;
        }
        const configureKey = `${frigateEvent}|${clipUrl}`;
        if (configureKey === lastConfiguredKey) return;
        lastConfiguredKey = configureKey;
        void configurePlayer();
    });

    onDestroy(() => {
        configureToken += 1;
        lastConfiguredKey = '';
        if (initWatchdogTimer) {
            clearTimeout(initWatchdogTimer);
            initWatchdogTimer = null;
        }
        if (controlsProbeTimer) {
            clearTimeout(controlsProbeTimer);
            controlsProbeTimer = null;
        }
        destroyPlayer();
        logger.info('video_player_modal_close', { frigateEvent });
        restoreFocusElement?.focus?.();
    });

    $effect(() => {
        if (initWatchdogTimer) {
            clearTimeout(initWatchdogTimer);
            initWatchdogTimer = null;
        }
        if (initializing) {
            initWatchdogTimer = setTimeout(() => {
                logger.warn('video_player_initialization_still_pending', {
                    frigateEvent,
                    previewState,
                    retryCount,
                    clipUrl: sanitizedUrl(clipUrl)
                });
                // Fail fast to avoid long-running UI lockups if player initialization deadlocks.
                if (initializing) {
                    switchToNativeFallback('initialization_watchdog_timeout');
                }
            }, 15000);
        }
    });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div
    bind:this={modalElement}
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
            bind:this={closeButton}
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
                        <h3 class="text-xl font-semibold text-white mb-2">{$_('video_player.clip_fetching_disabled', { default: 'Clip Fetching Disabled' })}</h3>
                        <p class="text-slate-400 max-w-sm">
                            {$_('video_player.clip_fetching_disabled_hint', { default: 'Enable "Fetch Video Clips" in Settings to view this recording.' })}
                        </p>
                    {:else}
                        <h3 class="text-xl font-semibold text-white mb-2">{$_('video_player.video_unavailable', { default: 'Video Unavailable' })}</h3>
                        <p class="text-slate-400 max-w-sm mb-6">
                            {$_('video_player.video_unavailable_hint', { default: 'The recording could not be loaded from Frigate. It may have been deleted or is not yet available.' })}
                        </p>
                        {#if retryCount < maxRetries}
                            <button
                                type="button"
                                onclick={retryLoad}
                                class="px-6 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-full transition-all duration-200"
                            >
                                {$_('common.retry', { default: 'Retry' })}
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
                        preload="auto"
                        class="w-full h-full"
                    >
                        <source src={clipUrl} type="video/mp4" />
                        Your browser does not support video playback.
                    </video>

                    {#if initializing}
                        <div class="absolute inset-0 grid place-items-center bg-black/45 text-slate-200 text-sm">
                            {$_('video_player.preparing', { default: 'Preparing player...' })}
                        </div>
                    {/if}
                </div>
            {/if}
        </div>

        {#if !videoError}
            <div class="mt-2 text-[11px] text-slate-300 px-1 flex items-center justify-between gap-2">
                <span>{$_('video_player.shortcuts', { default: 'Shortcuts: space/K play/pause, arrows seek' })}</span>
                <div class="flex items-center gap-2">
                    <span>{#if useNativeControls}
                        {$_('video_player.previews_unavailable', { default: 'Timeline previews unavailable for this clip' })}
                    {:else if previewState === 'enabled'}
                        {$_('video_player.previews_enabled', { default: 'Timeline previews enabled' })}
                    {:else if previewState === 'disabled'}
                        {$_('video_player.previews_disabled', { default: 'Timeline previews disabled (media cache off)' })}
                    {:else if previewState === 'checking'}
                        {$_('video_player.previews_generating', { default: 'Generating timeline previews...' })}
                    {:else if previewState === 'deferred'}
                        {$_('video_player.previews_deferred', { default: 'Timeline previews deferred while video is playing' })}
                    {:else}
                        {$_('video_player.previews_unavailable', { default: 'Timeline previews unavailable for this clip' })}
                    {/if}</span>
                    {#if canDownloadClip}
                        <a
                            href={clipDownloadUrl}
                            download={`${frigateEvent}.mp4`}
                            class="inline-flex items-center rounded-md bg-slate-700/80 px-2 py-1 text-[11px] font-semibold text-slate-100 hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-emerald-400/60"
                        >
                            {$_('video_player.download', { default: 'Download clip' })}
                        </a>
                    {/if}
                </div>
            </div>
            {#if previewState === 'checking' && !useNativeControls}
                <div class="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-700/70" aria-label="Generating timeline previews">
                    <div class="h-full w-1/3 bg-emerald-400/90 animate-[previewLoad_1.15s_ease-in-out_infinite]"></div>
                </div>
            {/if}
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

    @keyframes previewLoad {
        0% { transform: translateX(-130%); }
        100% { transform: translateX(330%); }
    }
</style>
