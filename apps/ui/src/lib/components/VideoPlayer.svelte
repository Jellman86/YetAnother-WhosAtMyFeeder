<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import Plyr from 'plyr';
    import { _ } from 'svelte-i18n';
    import 'plyr/dist/plyr.css';
    import { getClipPreviewTrackUrl, getClipUrl } from '../api';
    import { authStore } from '../stores/auth.svelte';
    import { notificationCenter } from '../stores/notification_center.svelte';
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
    type PlaybackState = 'idle' | 'playing' | 'paused' | 'buffering' | 'ended';

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
    let deferredPreviewSrc = $state<string | null>(null);
    let deferredPreviewToken = $state(0);
    let previewState = $state<PreviewState>('checking');
    let playbackState = $state<PlaybackState>('idle');
    let previewNotificationSig = $state('');

    let clipUrlBase = $derived(getClipUrl(frigateEvent));
    let clipUrl = $state('');
    let clipDownloadUrl = $derived(clipUrl ? `${clipUrl}${clipUrl.includes('?') ? '&' : '?'}download=1` : '');
    let canDownloadClip = $derived(!authStore.isGuest || authStore.publicAccessAllowClipDownloads);
    let shortEventId = $derived(frigateEvent.split('-').pop() ?? frigateEvent);
    let previewStatusLabel = $derived.by(() => {
        if (useNativeControls) return $_('video_player.previews_unavailable', { default: 'Timeline previews unavailable for this clip' });
        if (previewState === 'enabled') return $_('video_player.previews_enabled', { default: 'Timeline previews enabled' });
        if (previewState === 'disabled') return $_('video_player.previews_disabled', { default: 'Timeline previews disabled (media cache off)' });
        if (previewState === 'checking') return $_('video_player.previews_generating', { default: 'Generating timeline previews...' });
        if (previewState === 'deferred') return $_('video_player.previews_deferred', { default: 'Timeline previews deferred while video is playing' });
        return $_('video_player.previews_unavailable', { default: 'Timeline previews unavailable for this clip' });
    });
    let playbackLabel = $derived.by(() => {
        if (initializing) return $_('video_player.preparing', { default: 'Preparing player...' });
        if (playbackState === 'playing') return $_('video_player.playing', { default: 'Playing' });
        if (playbackState === 'buffering') return $_('video_player.buffering', { default: 'Buffering' });
        if (playbackState === 'paused') return $_('video_player.paused', { default: 'Paused' });
        if (playbackState === 'ended') return $_('video_player.ended', { default: 'Ended' });
        return $_('video_player.ready', { default: 'Ready' });
    });

    let mounted = false;
    let configureToken = 0;
    let initWatchdogTimer: ReturnType<typeof setTimeout> | null = null;
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

    function switchToNativeFallback(reason: string): void {
        logger.warn('video_player_native_fallback', { frigateEvent, reason, clipUrl: sanitizedUrl(clipUrl) });
        destroyPlayer();
        deferredPreviewSrc = null;
        deferredPreviewToken = 0;
        useNativeControls = true;
        previewState = 'unavailable';
        initializing = false;
        playbackState = 'paused';
    }

    function handleVideoPlay() {
        if (playbackState !== 'buffering') {
            playbackState = 'playing';
        }
    }

    function handleVideoPause() {
        if (videoElement?.ended) {
            playbackState = 'ended';
            return;
        }
        if (playbackState !== 'buffering') {
            playbackState = 'paused';
        }
        void attachDeferredPreviewIfReady('pause');
    }

    function handleVideoWaiting() {
        if (!videoElement?.paused) {
            playbackState = 'buffering';
        }
    }

    function handleVideoCanPlay() {
        if (videoElement?.ended) {
            playbackState = 'ended';
        } else if (videoElement?.paused) {
            playbackState = 'paused';
        } else {
            playbackState = 'playing';
        }
    }

    function handleVideoEnded() {
        playbackState = 'ended';
        void attachDeferredPreviewIfReady('ended');
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

    function createPlyr(previewSrc: string | null, options: { autoplay?: boolean } = {}): boolean {
        if (!videoElement) return false;

        destroyPlayer();
        logger.info('video_player_create_plyr', {
            frigateEvent,
            clipUrl: sanitizedUrl(clipUrl),
            previewEnabled: !!previewSrc
        });
        try {
            player = new Plyr(videoElement, {
                autoplay: options.autoplay ?? true,
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
                playbackState = videoElement?.paused ? 'paused' : 'playing';
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

            if (options.autoplay ?? true) {
                const playResult = player.play();
                if (playResult && typeof playResult.then === 'function') {
                    void playResult.catch((error) => {
                        logger.info('video_player_autoplay_blocked', { frigateEvent, error });
                    });
                }
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
            if (videoElement && !videoElement.paused) {
                previewState = 'deferred';
                deferredPreviewSrc = previewSrc;
                deferredPreviewToken = token;
                logger.warn('video_player_preview_skipped_active_playback', { frigateEvent });
                return;
            }

            const previewAttached = createPlyr(previewSrc, { autoplay: true });
            if (!previewAttached) {
                switchToNativeFallback('preview_attach_failed');
            }
        }
    }

    async function attachDeferredPreviewIfReady(trigger: 'pause' | 'ended'): Promise<void> {
        if (!deferredPreviewSrc || deferredPreviewToken !== configureToken) {
            if (deferredPreviewToken !== configureToken) {
                deferredPreviewSrc = null;
                deferredPreviewToken = 0;
            }
            return;
        }
        if (useNativeControls || videoError || initializing || !videoElement || !videoElement.paused) return;

        const previewSrc = deferredPreviewSrc;
        deferredPreviewSrc = null;
        deferredPreviewToken = 0;
        previewState = 'enabled';
        logger.info('video_player_attach_deferred_preview', { frigateEvent, trigger });
        const previewAttached = createPlyr(previewSrc, { autoplay: false });
        if (!previewAttached) {
            switchToNativeFallback('deferred_preview_attach_failed');
            return;
        }
        playbackState = 'paused';
    }

    async function configurePlayer() {
        if (!mounted || !videoElement || !clipUrl) return;

        const token = ++configureToken;
        const started = performance.now();
        initializing = true;
        playbackState = 'idle';
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
            deferredPreviewSrc = null;
            deferredPreviewToken = 0;
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
        deferredPreviewSrc = null;
        deferredPreviewToken = 0;
        if (previewState === 'checking' || previewState === 'deferred') {
            notificationCenter.remove(`preview:${frigateEvent}`);
        }
        if (initWatchdogTimer) {
            clearTimeout(initWatchdogTimer);
            initWatchdogTimer = null;
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

    $effect(() => {
        if (authStore.isGuest) return;
        const id = `preview:${frigateEvent}`;
        const title = $_('video_player.preview_notification_title', { default: 'Timeline previews' });
        const signature = `${previewState}|${useNativeControls}|${videoError}|${id}`;
        if (signature === previewNotificationSig) return;
        previewNotificationSig = signature;

        if (videoError || useNativeControls || previewState === 'disabled' || previewState === 'unavailable') {
            notificationCenter.upsert({
                id,
                type: 'update',
                title,
                message: previewStatusLabel,
                timestamp: Date.now(),
                read: false,
                meta: { event_id: frigateEvent }
            });
            return;
        }

        if (previewState === 'checking' || previewState === 'deferred') {
            notificationCenter.upsert({
                id,
                type: 'process',
                title,
                message: previewStatusLabel,
                timestamp: Date.now(),
                read: false,
                meta: { event_id: frigateEvent }
            });
            return;
        }

        if (previewState === 'enabled') {
            notificationCenter.upsert({
                id,
                type: 'update',
                title,
                message: previewStatusLabel,
                timestamp: Date.now(),
                read: false,
                meta: { event_id: frigateEvent }
            });
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
            <div class="flex items-center justify-between gap-2 px-3 py-2 bg-slate-900/75 border-b border-slate-700/60">
                <div class="flex items-center gap-2 min-w-0">
                    <span class="inline-flex items-center rounded-full border border-slate-600 bg-slate-800/80 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-200 font-semibold">
                        Clip
                    </span>
                    <span class="text-xs text-slate-300 truncate font-mono">{shortEventId}</span>
                </div>
                <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold border
                    {playbackState === 'playing' ? 'bg-emerald-400/15 text-emerald-200 border-emerald-400/35' :
                     playbackState === 'buffering' ? 'bg-amber-400/15 text-amber-200 border-amber-400/35' :
                     playbackState === 'ended' ? 'bg-slate-400/15 text-slate-200 border-slate-400/35' :
                     'bg-cyan-400/15 text-cyan-100 border-cyan-400/30'}"
                >
                    {playbackLabel}
                </span>
            </div>
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
                        onplay={handleVideoPlay}
                        onpause={handleVideoPause}
                        onwaiting={handleVideoWaiting}
                        onstalled={handleVideoWaiting}
                        onseeking={handleVideoWaiting}
                        oncanplay={handleVideoCanPlay}
                        onplaying={handleVideoCanPlay}
                        onended={handleVideoEnded}
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
            <div class="mt-2 px-1 flex items-center justify-between gap-2 text-[11px]">
                <span
                    class="inline-flex items-center gap-1.5 text-slate-300"
                    aria-label={$_('video_player.shortcuts', { default: 'Shortcuts: space/K play/pause, arrows seek' })}
                    title={$_('video_player.shortcuts', { default: 'Shortcuts: space/K play/pause, arrows seek' })}
                >
                    <span class="inline-flex h-6 items-center rounded-md border border-slate-700/70 bg-slate-800/60 px-1.5 text-slate-200 font-mono">Space</span>
                    <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/70 bg-slate-800/60 text-slate-200 font-mono">K</span>
                    <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/70 bg-slate-800/60 text-slate-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5v14l11-7-11-7z" />
                        </svg>
                    </span>
                    <span class="inline-flex h-6 w-6 items-center justify-center rounded-md border border-slate-700/70 bg-slate-800/60 text-slate-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 6l-6 6 6 6M15 6l6 6-6 6" />
                        </svg>
                    </span>
                    <span class="sr-only">{$_('video_player.shortcuts', { default: 'Shortcuts: space/K play/pause, arrows seek' })}</span>
                </span>
                <div class="flex items-center gap-2">
                    <span
                        class="inline-flex h-8 w-8 items-center justify-center rounded-full border bg-slate-800/60 text-slate-200
                            {(useNativeControls || previewState === 'disabled' || previewState === 'unavailable')
                                ? 'border-slate-700/70 text-slate-300'
                                : previewState === 'checking'
                                    ? 'border-amber-400/40 text-amber-200'
                                    : previewState === 'deferred'
                                        ? 'border-cyan-400/35 text-cyan-200'
                                        : 'border-emerald-400/35 text-emerald-200'}"
                        aria-label={previewStatusLabel}
                        title={previewStatusLabel}
                    >
                        {#if previewState === 'checking'}
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.5 12a7.5 7.5 0 0 1 11.78-6.15m3.22 6.15a7.5 7.5 0 0 1-11.78 6.15M16.5 3.75v2.1m3.75 3.75h-2.1M7.5 20.25v-2.1m-3.75-3.75h2.1" />
                            </svg>
                        {:else if previewState === 'enabled'}
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7.5h18M3 16.5h18M5.25 7.5v9m4.5-9v9m4.5-9v9m4.5-9v9" />
                            </svg>
                        {:else if previewState === 'deferred'}
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6l3.5 2M21 12a9 9 0 1 1-9-9" />
                            </svg>
                        {:else}
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7.5h18M3 16.5h18M5.25 7.5v9m4.5-9v9m4.5-9v9m4.5-9v9M4 4l16 16" />
                            </svg>
                        {/if}
                    </span>
                    {#if canDownloadClip}
                        <a
                            href={clipDownloadUrl}
                            download={`${frigateEvent}.mp4`}
                            class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/15 border border-emerald-400/35 text-emerald-100 hover:bg-emerald-500/25 focus:outline-none focus:ring-2 focus:ring-emerald-400/60"
                            aria-label={$_('video_player.download', { default: 'Download clip' })}
                            title={$_('video_player.download', { default: 'Download clip' })}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v10.5m0 0l-4-4m4 4l4-4M5 15.75v1.5A1.75 1.75 0 0 0 6.75 19h10.5A1.75 1.75 0 0 0 19 17.25v-1.5" />
                            </svg>
                        </a>
                    {/if}
                </div>
            </div>
            {#if playbackState === 'buffering'}
                <div class="mt-1 text-[11px] text-amber-200/90 px-1">
                    {$_('video_player.buffering_hint', { default: 'Buffering video stream...' })}
                </div>
            {/if}
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
