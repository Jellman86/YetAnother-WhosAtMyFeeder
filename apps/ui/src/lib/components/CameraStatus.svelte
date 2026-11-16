<script lang="ts">
    import DialogCloseButton from './DialogCloseButton.svelte';
    import { _ } from 'svelte-i18n';
    import { onMount, onDestroy } from 'svelte';
    import { startVisiblePoll } from '../app/visible-poll';
    import { settingsStore } from '../stores/settings.svelte';
    import { systemStatusStore } from '../stores/system_status.svelte';
    import type { SystemStatus } from '../api/status';
    import { fetchEventFilters } from '../api/events';
    import {
        readCameraStatuses,
        fetchLatestCameraSnapshot,
        type CameraStatusResponse
    } from '../api/media';
    import { viewerCameraNames } from '../utils/camera-viewer';

    type CameraHealth = CameraStatusResponse['cameras'][number];
    type HealthState = CameraHealth['status'];
    type FrameState = { url: string | null; loading: boolean; error: boolean };
    type OverallTone = 'ok' | 'mixed' | 'down' | 'checking' | 'idle';

    const FRAME_REFRESH_MS = 15_000;

    let cameras = $state<string[]>([]);
    let monitorAllCameras = $state(false);
    let cameraHealth = $state<Record<string, CameraHealth>>({});
    let frames = $state<Record<string, FrameState>>({});
    let healthChecked = $state(false);
    let healthLoading = $state(true);
    let healthUnavailable = $state(false);
    let popoverOpen = $state(false);
    let selectedIndex = $state(0);
    let rootEl: HTMLDivElement | null = $state(null);
    let triggerEl: HTMLButtonElement | null = $state(null);
    let viewerEl: HTMLDivElement | null = $state(null);
    // Camera health arrives with the pushed status; this stops following it.
    let stopFollowingStatus: (() => void) | null = null;
    // The mount bootstrap awaits several reads; a poll started after destroy would never stop.
    let destroyed = false;
    let stopFramePoll: (() => void) | null = null;
    let healthController: AbortController | null = null;
    let frameController: AbortController | null = null;
    let healthPromise: Promise<void> | null = null;
    let menuId = 'camera-status-viewer';
    let statusDescriptionId = 'camera-status-description';

    let selectedCamera = $derived(cameras[selectedIndex] ?? '');
    let selectedFrame = $derived(selectedCamera ? frames[selectedCamera] : undefined);
    let selectedHealth = $derived(selectedCamera ? cameraHealth[selectedCamera] : undefined);
    let selectedHealthState = $derived<HealthState>(selectedHealth?.status ?? 'unknown');
    let onlineCount = $derived(cameras.reduce((count, camera) => count + (cameraHealth[camera]?.status === 'online' ? 1 : 0), 0));
    let offlineCount = $derived(cameras.reduce((count, camera) => count + (cameraHealth[camera]?.status === 'offline' ? 1 : 0), 0));

    let statusTone = $derived.by<OverallTone>(() => {
        if (cameras.length === 0) return 'idle';
        if (!healthChecked || healthLoading) return 'checking';
        if (onlineCount === cameras.length) return 'ok';
        if (offlineCount === cameras.length) return 'down';
        if (onlineCount > 0 || offlineCount > 0) return 'mixed';
        return 'checking';
    });

    let toneDotClass = $derived.by(() => {
        switch (statusTone) {
            case 'ok': return 'bg-status-ok-line ring-status-ok-line/35';
            case 'mixed': return 'bg-status-attention-line ring-status-attention-line/35';
            case 'down': return 'bg-status-fail-line ring-status-fail-line/35';
            default: return 'bg-status-neutral-line ring-status-neutral-line/35';
        }
    });

    let selectedDotClass = $derived.by(() => {
        switch (selectedHealthState) {
            case 'online': return 'bg-success-400';
            case 'offline': return 'bg-rose-400';
            default: return 'bg-slate-400';
        }
    });

    function replaceCameraList(nextCameras: string[]): void {
        const unique = [...new Set(nextCameras.filter((camera) => camera.trim().length > 0))];
        const previouslySelected = cameras[selectedIndex];
        const removed = cameras.filter((camera) => !unique.includes(camera));
        for (const camera of removed) {
            const url = frames[camera]?.url;
            if (url) URL.revokeObjectURL(url);
        }

        cameras = unique;
        frames = Object.fromEntries(
            unique.map((camera) => [camera, frames[camera] ?? { url: null, loading: false, error: false }])
        );
        const previousIndex = previouslySelected ? unique.indexOf(previouslySelected) : -1;
        selectedIndex = previousIndex >= 0 ? previousIndex : Math.min(selectedIndex, Math.max(unique.length - 1, 0));
    }

    function cameraNames(value: unknown): string[] {
        return Array.isArray(value)
            ? value.filter((camera: unknown): camera is string => typeof camera === 'string' && camera.length > 0)
            : [];
    }

    async function loadCameras(): Promise<void> {
        try {
            const settings = await settingsStore.read();
            const configured = viewerCameraNames({
                cameras: cameraNames(settings.cameras),
                garden_cameras: cameraNames(settings.garden_cameras),
                beta_garden_animals: settings.beta_garden_animals
            });
            monitorAllCameras = configured.length === 0;
            replaceCameraList(configured);
        } catch {
            monitorAllCameras = true;
            replaceCameraList([]);
        }
    }

    async function loadFallbackCameras(): Promise<void> {
        if (cameras.length > 0) return;
        try {
            const filters = await fetchEventFilters();
            replaceCameraList((filters.cameras ?? []).filter((camera): camera is string => typeof camera === 'string' && camera.length > 0));
        } catch {
            // Keep the empty state. The next health refresh can still discover Frigate cameras.
        }
    }

    function applyCameraHealth(reading: CameraStatusResponse | null): void {
        if (!reading) {
            // Frigate did not answer the last stats request: say so rather than show old health.
            cameraHealth = {};
            healthUnavailable = true;
            healthChecked = true;
            healthLoading = false;
            return;
        }
        cameraHealth = Object.fromEntries(reading.cameras.map((camera) => [camera.camera, camera]));
        if (monitorAllCameras && reading.cameras.length > 0) {
            replaceCameraList(reading.cameras.map((camera) => camera.camera));
        }
        healthUnavailable = false;
        healthChecked = true;
        healthLoading = false;
    }

    function applyStatus(snapshot: SystemStatus): void {
        applyCameraHealth(snapshot.cameras ?? null);
    }

    /** One direct reading, for the first paint before any status and when the viewer opens. */
    async function refreshHealth(): Promise<void> {
        if (healthPromise || document.hidden) return healthPromise ?? Promise.resolve();
        const controller = new AbortController();
        healthController = controller;
        healthLoading = !healthChecked;

        const currentRefresh = (async () => {
            try {
                const response = await readCameraStatuses(controller.signal);
                if (controller.signal.aborted) return;
                applyCameraHealth(response);
            } catch (error) {
                if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) return;
                cameraHealth = {};
                healthUnavailable = true;
                healthChecked = true;
            } finally {
                if (healthController === controller) healthController = null;
                healthLoading = false;
            }
        })();

        healthPromise = currentRefresh;
        try {
            await currentRefresh;
        } finally {
            if (healthPromise === currentRefresh) healthPromise = null;
        }
    }

    async function refreshSelectedFrame(): Promise<void> {
        const camera = selectedCamera;
        if (!camera || document.hidden) return;

        frameController?.abort();
        const controller = new AbortController();
        frameController = controller;
        const previous = frames[camera] ?? { url: null, loading: false, error: false };
        frames = { ...frames, [camera]: { ...previous, loading: true, error: false } };

        try {
            const blob = await fetchLatestCameraSnapshot(camera, controller.signal);
            if (controller.signal.aborted) return;
            const url = URL.createObjectURL(blob);
            const previousUrl = frames[camera]?.url;
            if (previousUrl) URL.revokeObjectURL(previousUrl);
            frames = { ...frames, [camera]: { url, loading: false, error: false } };
        } catch (error) {
            if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) return;
            frames = {
                ...frames,
                [camera]: { ...(frames[camera] ?? previous), loading: false, error: true }
            };
        } finally {
            if (frameController === controller) frameController = null;
        }
    }

    /** Health follows the pushed status from here on, so the shell makes no camera requests while idle. */
    function followStatus(): void {
        if (destroyed) return;
        stopFollowingStatus ??= systemStatusStore.subscribe(applyStatus);
    }

    function stopHealthRefresh(): void {
        stopFollowingStatus?.();
        stopFollowingStatus = null;
        healthController?.abort();
        healthController = null;
    }

    function startFrameRefresh(): void {
        if (destroyed) return;
        stopFramePoll ??= startVisiblePoll({ read: refreshSelectedFrame, delayMs: () => FRAME_REFRESH_MS });
    }

    function stopFrameRefresh(): void {
        stopFramePoll?.();
        stopFramePoll = null;
        frameController?.abort();
        frameController = null;
    }

    function open(): void {
        if (popoverOpen) return;
        popoverOpen = true;
        void refreshHealth();
        startFrameRefresh();
        requestAnimationFrame(() => viewerEl?.focus());
    }

    function close(restoreFocus = false): void {
        if (!popoverOpen) return;
        popoverOpen = false;
        stopFrameRefresh();
        if (restoreFocus) requestAnimationFrame(() => triggerEl?.focus());
    }

    function toggle(): void {
        popoverOpen ? close() : open();
    }

    function selectOffset(offset: number): void {
        if (cameras.length < 2) return;
        selectedIndex = (selectedIndex + offset + cameras.length) % cameras.length;
        void refreshSelectedFrame();
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (!popoverOpen) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            close(true);
        } else if (event.key === 'ArrowLeft') {
            event.preventDefault();
            selectOffset(-1);
        } else if (event.key === 'ArrowRight') {
            event.preventDefault();
            selectOffset(1);
        }
    }

    function handleOutsidePointer(event: PointerEvent): void {
        if (popoverOpen && rootEl && event.target instanceof Node && !rootEl.contains(event.target)) close();
    }

    function handleVisibilityChange(): void {
        if (document.hidden) {
            healthController?.abort();
            frameController?.abort();
        }
    }

    onMount(() => {
        void (async () => {
            await loadCameras();
            const pushed = systemStatusStore.snapshot;
            // An owner's status carries camera health and is already on its way; only a page
            // without it asks Frigate's stats directly. Until it lands the widget says "checking".
            if (pushed) applyStatus(pushed);
            else if (!systemStatusStore.following) await refreshHealth();
            await loadFallbackCameras();
            followStatus();
        })();
    });

    onDestroy(() => {
        destroyed = true;
        stopHealthRefresh();
        stopFrameRefresh();
        for (const entry of Object.values(frames)) {
            if (entry.url) URL.revokeObjectURL(entry.url);
        }
    });
</script>

<svelte:window
    onkeydown={handleKeydown}
    onpointerdown={handleOutsidePointer}
    onvisibilitychange={handleVisibilityChange}
/>

<div class="relative" bind:this={rootEl}>
    <button
        type="button"
        bind:this={triggerEl}
        onclick={toggle}
        class="relative p-2.5 rounded-xl hover:bg-surface-raised text-muted transition-colors duration-200 motion-reduce:transition-none focus-ring"
        aria-haspopup="dialog"
        aria-expanded={popoverOpen}
        aria-controls={menuId}
        aria-describedby={statusDescriptionId}
        aria-label={$_('header.cameras_label', { default: 'Camera status', values: { online: onlineCount, total: cameras.length } })}
        title={statusTone === 'ok'
            ? $_('header.cameras_all_online', { default: 'All cameras online', values: { total: cameras.length } })
            : statusTone === 'mixed'
                ? $_('header.cameras_some_online', { default: 'Some cameras need attention', values: { online: onlineCount, total: cameras.length } })
                : statusTone === 'down'
                    ? $_('header.cameras_all_offline', { default: 'All cameras offline' })
                    : healthUnavailable
                        ? $_('header.cameras_status_unavailable', { default: 'Camera status unavailable' })
                        : cameras.length === 0
                            ? $_('header.cameras_none', { default: 'No cameras configured' })
                            : $_('header.cameras_checking', { default: 'Checking cameras…' })}
    >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
        </svg>
        {#if cameras.length > 0}
            <span class="absolute bottom-1 right-1 h-2.5 w-2.5 rounded-full ring-2 ring-white dark:ring-slate-950 {toneDotClass}" aria-hidden="true"></span>
        {/if}
    </button>
    <span id={statusDescriptionId} class="sr-only" aria-live="polite">
        {statusTone === 'ok'
            ? $_('header.cameras_all_online', { default: 'All cameras online', values: { total: cameras.length } })
            : statusTone === 'mixed'
                ? $_('header.cameras_some_online', { default: 'Some cameras need attention', values: { online: onlineCount, total: cameras.length } })
                : statusTone === 'down'
                    ? $_('header.cameras_all_offline', { default: 'All cameras offline' })
                    : healthUnavailable
                        ? $_('header.cameras_status_unavailable', { default: 'Camera status unavailable' })
                        : cameras.length === 0
                            ? $_('header.cameras_none', { default: 'No cameras configured' })
                            : $_('header.cameras_checking', { default: 'Checking cameras…' })}
    </span>

    {#if popoverOpen}
        <div
            bind:this={viewerEl}
            class="group/viewer fixed inset-x-4 top-35 w-auto overflow-hidden rounded-2xl border border-line bg-slate-950 shadow-2xl shadow-slate-950/25 z-60 animate-in fade-in zoom-in-95 md:absolute md:left-auto md:right-0 md:top-full md:mt-2 md:w-[min(34rem,calc(100vw-2rem))]"
            id={menuId}
            role="dialog"
            aria-modal="false"
            aria-label={$_('header.cameras_viewer', { default: 'Live camera viewer' })}
            tabindex="-1"
        >
            {#if cameras.length === 0}
                <div class="flex aspect-video max-h-[calc(100dvh-9.75rem)] flex-col items-center justify-center gap-3 px-6 text-center text-slate-300">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <p class="max-w-sm text-sm font-semibold">
                        {$_('header.cameras_empty', { default: 'No cameras configured. Add cameras in Settings → Connection.' })}
                    </p>
                </div>
            {:else}
                <div class="relative aspect-video max-h-[calc(100dvh-9.75rem)] w-full bg-slate-950">
                    {#if selectedFrame?.url}
                        <img
                            src={selectedFrame.url}
                            alt={$_('header.cameras_frame_alt', { default: 'Latest frame from {camera}', values: { camera: selectedCamera } })}
                            class="absolute inset-0 h-full w-full object-contain"
                        />
                    {:else if selectedFrame?.loading}
                        <div class="absolute inset-0 flex items-center justify-center" aria-label={$_('common.loading')}>
                            <div class="h-7 w-7 animate-spin rounded-full border-2 border-white/30 border-t-white motion-reduce:animate-none"></div>
                        </div>
                    {:else}
                        <div class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-slate-300">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.73 5H5a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-3m0-4l2.553-1.276A1 1 0 0121 9.618v4.764a1 1 0 01-.553.894M15 8v-.999a2 2 0 00-2-2h-1" />
                            </svg>
                            <span class="text-xs font-bold">
                                {selectedFrame?.error
                                    ? $_('header.cameras_frame_unavailable', { default: 'Frame unavailable' })
                                    : $_('header.cameras_no_frame', { default: 'No frame' })}
                            </span>
                            <button
                                type="button"
                                onclick={() => void refreshSelectedFrame()}
                                class="min-h-11 rounded-full border border-white/20 bg-white/10 px-4 text-xs font-bold text-white backdrop-blur-md transition-colors hover:bg-white/20 focus-ring"
                            >
                                {$_('header.cameras_retry', { default: 'Retry' })}
                            </button>
                        </div>
                    {/if}

                    {#if selectedFrame?.url && selectedFrame.loading}
                        <div class="absolute right-16 top-4 h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white motion-reduce:animate-none" aria-label={$_('common.loading')}></div>
                    {/if}

                    <div class="absolute left-3 top-3 flex max-w-[calc(100%-4.5rem)] items-center gap-2 rounded-full border border-white/15 bg-slate-950/70 px-3 py-2 text-white shadow-lg backdrop-blur-md" aria-live="polite">
                        <span class="h-2 w-2 shrink-0 rounded-full {selectedDotClass}" aria-hidden="true"></span>
                        <span class="wrap-break-word text-xs font-bold">{selectedCamera}</span>
                        <span class="text-3xs font-semibold text-slate-300">
                            {selectedHealthState === 'online'
                                ? $_('header.cameras_status_online', { default: 'Online' })
                                : selectedHealthState === 'offline'
                                    ? $_('header.cameras_status_offline', { default: 'Offline' })
                                    : healthUnavailable
                                        ? $_('header.cameras_status_unavailable', { default: 'Status unavailable' })
                                        : $_('header.cameras_checking', { default: 'Checking…' })}
                        </span>
                    </div>

                    <DialogCloseButton tone="media" class="absolute right-2 top-2" onclick={() => close(true)} />

                    {#if cameras.length > 1}
                        <button
                            type="button"
                            onclick={() => selectOffset(-1)}
                            class="absolute left-2 top-1/2 flex min-h-11 min-w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-slate-950/45 text-white opacity-80 shadow-lg backdrop-blur-md transition-all hover:bg-slate-950/75 hover:opacity-100 focus:opacity-100 focus-ring motion-reduce:transition-none"
                            aria-label={$_('header.cameras_previous', { default: 'Previous camera' })}
                            title={$_('header.cameras_previous', { default: 'Previous camera' })}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.25" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
                            </svg>
                        </button>
                        <button
                            type="button"
                            onclick={() => selectOffset(1)}
                            class="absolute right-2 top-1/2 flex min-h-11 min-w-11 -translate-y-1/2 items-center justify-center rounded-full border border-white/15 bg-slate-950/45 text-white opacity-80 shadow-lg backdrop-blur-md transition-all hover:bg-slate-950/75 hover:opacity-100 focus:opacity-100 focus-ring motion-reduce:transition-none"
                            aria-label={$_('header.cameras_next', { default: 'Next camera' })}
                            title={$_('header.cameras_next', { default: 'Next camera' })}
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.25" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                            </svg>
                        </button>
                    {/if}

                    <div class="absolute bottom-3 right-3 rounded-full border border-white/10 bg-slate-950/65 px-2.5 py-1 text-3xs font-bold tabular-nums text-slate-200 backdrop-blur-md">
                        {selectedIndex + 1} / {cameras.length}
                    </div>
                </div>
            {/if}
        </div>
    {/if}
</div>
