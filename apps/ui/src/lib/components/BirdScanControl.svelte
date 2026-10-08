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

<div class="space-y-2 rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900" data-bird-scan-control>
    <button type="button" class="btn btn-secondary min-h-11 min-w-11 gap-2 focus-ring"
        disabled={disabled || view.pending || active || !candidateId || !mediaRevision || !view.response?.available || view.readError}
        onclick={() => { void controller?.start(scanStatus === 'completed' || scanStatus === 'failed'); }}>
        <svg class="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 16c1-4 3-6 6-5l2-3 2 2-2 2c1 4-2 7-5 7H3l2-3m9-8c1-3 3-4 5-3l1-2 2 2-2 1c1 3-1 5-4 5h-2l1-3" />
        </svg>
        {scanStatus === 'completed' ? $_('detection.bird_scan.again', { default: 'Scan again' }) : $_('detection.bird_scan.action', { default: 'Find more birds' })}
    </button>
    <div class="text-xs leading-5 text-slate-600 dark:text-slate-300" role="status" aria-live="polite" data-bird-scan-state={view.readError ? 'status_unavailable' : unavailable ? 'unavailable' : scanStatus ?? 'loading'}>
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
</div>
