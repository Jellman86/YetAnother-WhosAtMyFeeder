<script lang="ts">
    import { untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchBirdScan, startBirdScan } from '../api/media';
    import { createBirdScanController, birdScanMediaVersion, type BirdScanView } from '../utils/bird-scan-controller';

    let { eventId, candidateId, imageVersion, disabled = false, oncompleted }: {
        eventId: string;
        candidateId: string | null;
        imageVersion: string | null;
        disabled?: boolean;
        oncompleted: (eventId: string, candidateId: string) => void;
    } = $props();
    let view = $state<BirdScanView>({ response: null, pending: false, readError: false, startUnconfirmed: false });
    let controller: ReturnType<typeof createBirdScanController> | null = null;
    const mediaRevision = $derived(birdScanMediaVersion(imageVersion));
    const active = $derived(view.response?.status === 'queued' || view.response?.status === 'running');
    const scanStatus = $derived(view.response?.status ?? null);
    const unavailable = $derived(!candidateId || !mediaRevision ? 'full_scene_unavailable' : view.response?.unavailable_reason);
    const unavailableText = $derived(unavailable === 'media_changed'
        ? $_('detection.bird_scan.media_changed', { default: 'The frame changed during the scan. Try again on the current frame.' })
        : unavailable === 'crop_model_unavailable'
        ? $_('detection.bird_scan.detector_unavailable', { default: 'Install a crop detector to find additional birds.' })
        : unavailable === 'scan_in_progress'
          ? $_('detection.bird_scan.other_running', { default: 'Another frame in this capture is being scanned. Try again when it finishes.' })
          : unavailable === 'reviewed_other_frame'
          ? $_('detection.bird_scan.reviewed_other_frame', { default: 'Birds reviewed on another frame are kept. This frame cannot replace them.' })
          : $_('detection.bird_scan.scene_unavailable', { default: 'The whole frame for this photograph is unavailable.' }));
    const errorText = $derived(view.response?.error === 'media_changed'
        ? $_('detection.bird_scan.media_changed', { default: 'The frame changed during the scan. Try again on the current frame.' })
        : view.response?.error === 'interrupted'
          ? $_('detection.bird_scan.interrupted', { default: 'The scan was interrupted. You can try again.' })
          : $_('detection.bird_scan.failed', { default: 'The scan could not finish. Your existing birds are kept.' }));

    $effect(() => {
        const event = eventId;
        const candidate = candidateId;
        const revision = mediaRevision;
        return untrack(() => {
            view = { response: null, pending: false, readError: false, startUnconfirmed: false };
            if (!candidate || !revision) { controller = null; return; }
            const current = createBirdScanController({
                eventId: event, candidateId: candidate,
                read: (signal) => fetchBirdScan(event, candidate, revision, signal),
                start: (force, signal) => startBirdScan(event, candidate, revision, force, signal),
                onChange: (next) => { view = next; },
                onCompleted: () => oncompleted(event, candidate),
                isVisible: () => !document.hidden
            });
            controller = current;
            const visibility = () => { void current.visibilityChanged(); };
            document.addEventListener('visibilitychange', visibility);
            void current.refresh();
            return () => {
                current.dispose();
                document.removeEventListener('visibilitychange', visibility);
                if (controller === current) controller = null;
            };
        });
    });
</script>

<!-- One quiet row under the photograph: what is known about this frame, then the action. On a
     phone the sentence takes the full width and the action sits beneath it. -->
<div class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-slate-100 px-3 py-2 dark:bg-slate-800/60" data-bird-scan-control>
    <div class="min-w-0 flex-1 basis-56 text-xs leading-5 text-slate-600 dark:text-slate-300" role="status" aria-live="polite" data-bird-scan-state={view.readError ? 'status_unavailable' : unavailable ? 'unavailable' : scanStatus ?? 'loading'}>
        {#if view.readError}
            <p>{view.startUnconfirmed ? $_('detection.bird_scan.start_unconfirmed', { default: 'The scan request could not be confirmed. Checking its status before trying again.' }) : $_('detection.bird_scan.status_unavailable', { default: 'Scan status could not be loaded. Checking again shortly.' })}</p>
            <button type="button" class="btn btn-ghost min-h-11 min-w-11 focus-ring" disabled={view.pending} onclick={() => { void controller?.refresh(); }}>{$_('common.retry', { default: 'Retry' })}</button>
        {:else if unavailable}
            <p>{unavailableText}</p>
        {:else if scanStatus === 'queued'}
            <p>{$_('detection.bird_scan.queued', { default: 'Queued to scan this whole frame.' })}</p>
        {:else if scanStatus === 'running'}
            <p>{$_('detection.bird_scan.running', { default: 'Finding birds in this whole frame.' })}</p>
        {:else if scanStatus === 'failed'}
            <p>{errorText}</p>
        {:else if scanStatus === 'completed'}
            <p>{$_('detection.bird_scan.completed', { values: { count: view.response?.result_count ?? 0 }, default: 'Scan complete. Birds found in this frame: {count}.' })}</p>
            {#if view.response?.retained_previous}<p>{$_('detection.bird_scan.retained', { default: 'The previous bird count and your corrections are kept.' })}</p>{/if}
        {:else if scanStatus === 'not_scanned'}
            <p>{$_('detection.bird_scan.not_scanned', { default: 'This whole frame has not been scanned for additional birds.' })}</p>
        {:else}
            <p>{$_('detection.bird_scan.loading', { default: 'Checking this frame’s scan status…' })}</p>
        {/if}
    </div>
    <button type="button" class="btn btn-secondary min-h-11 min-w-11 shrink-0 gap-2 px-3 text-sm focus-ring"
        disabled={disabled || view.pending || active || !candidateId || !mediaRevision || !view.response?.available || view.readError}
        onclick={() => { void controller?.start(scanStatus === 'completed' || scanStatus === 'failed'); }}>
        <!-- A viewfinder: look across the whole frame for more. -->
        <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2M12 9v6M9 12h6" />
        </svg>
        {scanStatus === 'completed' ? $_('detection.bird_scan.again', { default: 'Scan again' }) : $_('detection.bird_scan.action', { default: 'Find more birds' })}
    </button>
</div>
