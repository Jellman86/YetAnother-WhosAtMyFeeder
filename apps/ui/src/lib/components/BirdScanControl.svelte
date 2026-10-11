<script lang="ts">
    import { untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchBirdScan, startBirdScan } from '../api/media';
    import { createBirdScanController, birdScanMediaVersion, type BirdScanView } from '../utils/bird-scan-controller';
    import { birdScanElapsedSeconds, birdScanProgress } from '../utils/bird-scan-progress';

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
    const progress = $derived(birdScanProgress(view.response));
    const queueAhead = $derived(view.response?.queue_ahead ?? null);
    const stepLabels = $derived([
        $_('detection.bird_scan.step_find', { default: 'Find' }),
        $_('detection.bird_scan.step_name', { default: 'Name' }),
        $_('detection.bird_scan.step_count', { default: 'Count' }),
        $_('detection.bird_scan.step_save', { default: 'Save' })
    ]);
    const runningText = $derived(
        progress.stage === 'detecting'
            ? $_('detection.bird_scan.stage_detecting', { default: 'Looking for birds across the whole frame.' })
            : progress.stage === 'naming'
              ? (view.response?.stage_total ?? 0) > 0
                  ? $_('detection.bird_scan.stage_naming', { values: { done: view.response?.stage_done ?? 0, total: view.response?.stage_total ?? 0 }, default: 'Naming each bird found: {done} of {total}.' })
                  : $_('detection.bird_scan.stage_naming_none', { default: 'No clear birds to name. Checking for faint ones.' })
              : progress.stage === 'counting'
                ? $_('detection.bird_scan.stage_counting', { default: 'Counting the birds and rechecking faint ones.' })
                : progress.stage === 'saving'
                  ? $_('detection.bird_scan.stage_saving', { default: 'Saving what was found.' })
                  : $_('detection.bird_scan.running', { default: 'Finding birds in this whole frame.' })
    );
    // Elapsed time is a clock outside Svelte, so a timer drives it while the scan is live.
    let seenAt = $state(0);
    let now = $state(Date.now());
    $effect(() => {
        if (!active) return;
        seenAt = Date.now();
        now = seenAt;
        const tick = setInterval(() => { now = Date.now(); }, 1000);
        return () => clearInterval(tick);
    });
    const elapsed = $derived(scanStatus === 'running' ? birdScanElapsedSeconds(view.response?.started_at, seenAt, now) : null);
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
            <p>
                {queueAhead !== null && queueAhead > 0
                    ? $_('detection.bird_scan.queued_behind', { values: { count: queueAhead }, default: 'Waiting to scan this whole frame. {count} scans ahead.' })
                    : $_('detection.bird_scan.queued', { default: 'Queued to scan this whole frame.' })}
            </p>
        {:else if scanStatus === 'running'}
            <p>{runningText}</p>
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
    {#if active && !unavailable && !view.readError}
        <!-- The four real steps of a scan. Outside the live region, so a screen reader hears each
             step once from the sentence above rather than a clock every second. -->
        <div class="order-last flex w-full items-start gap-3" data-bird-scan-progress>
            <div
                class="grid flex-1 grid-cols-4 gap-1.5"
                role="progressbar"
                aria-label={$_('detection.bird_scan.progress_label', { default: 'Scan progress' })}
                aria-valuemin={0}
                aria-valuemax={4}
                aria-valuenow={progress.segments.reduce((sum, part) => sum + part, 0)}
                aria-valuetext={scanStatus === 'queued' ? $_('detection.bird_scan.progress_waiting', { default: 'Waiting to start' }) : runningText}
            >
                {#each progress.segments as part, index (index)}
                    {@const current = progress.step === index + 1}
                    <span class="min-w-0">
                        <span class="relative block h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                            {#if part > 0}
                                <span class="absolute inset-y-0 left-0 rounded-full bg-brand-500 transition-[width] duration-500 motion-reduce:transition-none" style="width: {Math.round(part * 100)}%"></span>
                            {:else if current}
                                <!-- The step in hand, with no count to show: a slow pulse says it is live. -->
                                <span class="absolute inset-0 animate-pulse rounded-full bg-brand-500/35 motion-reduce:animate-none"></span>
                            {/if}
                        </span>
                        <span class="mt-1 block truncate text-2xs font-semibold {current ? 'text-brand-700 dark:text-brand-300' : part >= 1 ? 'text-slate-600 dark:text-slate-300' : 'text-slate-400 dark:text-slate-500'}" aria-hidden="true">{stepLabels[index]}</span>
                    </span>
                {/each}
            </div>
            {#if elapsed !== null}
                <span class="shrink-0 pt-px text-2xs font-semibold tabular-nums text-slate-500 dark:text-slate-400" aria-hidden="true">{$_('detection.bird_scan.elapsed', { values: { seconds: elapsed }, default: '{seconds}s' })}</span>
            {/if}
        </div>
    {/if}
    <button type="button" class="btn btn-secondary min-h-11 min-w-11 max-w-full gap-2 px-3 text-sm focus-ring"
        aria-busy={active || view.pending}
        disabled={disabled || view.pending || active || !candidateId || !mediaRevision || !view.response?.available || view.readError}
        onclick={() => { void controller?.start(scanStatus === 'completed' || scanStatus === 'failed'); }}>
        {#if active || (view.pending && view.response !== null)}
            <span class="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" aria-hidden="true"></span>
            {scanStatus === 'queued' ? $_('detection.bird_scan.action_waiting', { default: 'Waiting…' }) : $_('detection.bird_scan.action_scanning', { default: 'Scanning…' })}
        {:else}
            <!-- A viewfinder: look across the whole frame for more. -->
            <svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2M12 9v6M9 12h6" />
            </svg>
            {scanStatus === 'completed' ? $_('detection.bird_scan.again', { default: 'Scan again' }) : $_('detection.bird_scan.action', { default: 'Find more birds' })}
        {/if}
    </button>
</div>
