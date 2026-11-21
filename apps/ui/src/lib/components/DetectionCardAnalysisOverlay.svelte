<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ReclassificationProgress } from '../stores/detections.svelte';
    import FrameScanRibbon from './FrameScanRibbon.svelte';

    let { progress }: {
        progress: ReclassificationProgress;
    } = $props();

    type FrameResult = ReclassificationProgress['frameResults'][number];
    function hasFrameResult(frame: FrameResult | undefined): frame is FrameResult {
        return Boolean(frame);
    }

    let latestFrame = $derived(progress.frameResults.findLast(hasFrameResult));
    let finalTopResult = $derived(
        Array.isArray(progress.results) && progress.results.length > 0 ? progress.results[0] : null
    );
    let safeCurrentFrame = $derived(Number.isFinite(progress.currentFrame) ? Math.max(0, Math.floor(progress.currentFrame)) : 0);
    let safeTotalFrames = $derived(
        Number.isFinite(progress.totalFrames)
            ? Math.max(1, Math.floor(progress.totalFrames))
            : 1
    );
    let isComplete = $derived(progress.status === 'completed' || safeCurrentFrame >= safeTotalFrames);
    let progressPercent = $derived(Math.max(0, Math.min(100, Math.round((safeCurrentFrame / safeTotalFrames) * 100))));
    let displayFrameIndex = $derived(progress.frameIndex || safeCurrentFrame);
    let displayClipTotal = $derived(progress.clipTotal || safeTotalFrames);
    let progressStrategy = $derived((progress.strategy || '').toLowerCase());
    let isAutoVideoReclassification = $derived(progressStrategy === 'auto_video');
    let hasFallenBackToSnapshot = $derived((progress.fallbackFrom ?? '').toLowerCase() === 'video');
    let displayLabel = $derived(
        isComplete && finalTopResult?.label ? finalTopResult.label : latestFrame?.label
    );
    let displayScorePercent = $derived(
        isComplete && typeof finalTopResult?.score === 'number'
            ? Math.round(finalTopResult.score * 100)
            : (typeof latestFrame?.score === 'number' ? Math.round(latestFrame.score * 100) : null)
    );
    let statusLabel = $derived(
        isComplete
            ? $_('detection.card_analysis.finalizing', { default: 'Finalizing result' })
            : hasFallenBackToSnapshot
                ? $_('detection.reclassification.snapshot_fallback_title', { default: 'Classifying from snapshot' })
                : $_('detection.card_analysis.title', { default: 'Analysing this capture' })
    );
    let statusSubtitle = $derived(
        isComplete
            ? $_('detection.card_analysis.finalizing_subtitle', { default: 'Applying the best match' })
            : hasFallenBackToSnapshot
                ? $_('detection.card_analysis.snapshot_subtitle', { default: 'Using the best available snapshot' })
                : $_('detection.card_analysis.video_subtitle', { default: 'Scanning video frames' })
    );
    let closeIndicatorLabel = $derived($_('detection.card_analysis.closing_soon'));
</script>

<div class="detection-card-analysis-overlay absolute inset-0 z-20 flex flex-col justify-between rounded-2xl border border-accent-line bg-surface p-4 text-strong">

    <div class="relative flex items-start justify-between gap-3">
        <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-1.5">
                <span class="inline-flex h-2 w-2 rounded-full bg-status-info-line {isComplete ? '' : 'animate-pulse'}"></span>
                <span class="text-3xs font-bold text-accent-ink">
                    {statusLabel}
                </span>
            </div>
            <p class="mt-1 text-2xs font-semibold text-ink">
                {statusSubtitle}
            </p>
        </div>

        <div class="flex shrink-0 items-center gap-2">
            {#if isComplete}
                <div
                    class="card-analysis-close-indicator grid h-8 w-8 place-items-center rounded-full border border-line bg-surface-raised text-ink"
                    role="img"
                    aria-label={closeIndicatorLabel}
                    title={closeIndicatorLabel}
                >
                    <svg class="card-analysis-close-ring h-5 w-5" viewBox="0 0 20 20" aria-hidden="true">
                        <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-opacity="0.22" stroke-width="2"></circle>
                        <circle class="card-analysis-close-countdown" cx="10" cy="10" r="7" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="2"></circle>
                        <path d="M10 5.8v4.2l2.7 1.7" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.4"></path>
                    </svg>
                </div>
            {/if}
            <div class="rounded-xl border border-line-soft bg-surface-raised px-2 py-1.5 text-right shadow-xs ">
                <p class="text-base font-bold leading-none text-strong">{progressPercent}%</p>
                <p class="mt-0.5 text-3xs font-bold text-muted">
                    {$_('detection.reclassification.analysis', { default: 'Analysis' })}
                </p>
            </div>
        </div>
    </div>

    <div class="relative space-y-3">
        {#if hasFallenBackToSnapshot}
            <!-- On a track, so how far it has come reads against how far it has to go. -->
            <div class="overflow-hidden rounded-full bg-track">
                <div
                    class="h-2 rounded-full bg-status-info-line transition-all duration-500 motion-reduce:transition-none"
                    style={`width: ${progressPercent}%`}
                ></div>
            </div>
        {:else}
            <FrameScanRibbon {progress} variant="card" />
        {/if}

        <div class="rounded-xl border border-line-soft p-2.5">
            <div class="flex items-center justify-between gap-3 text-3xs font-bold text-muted">
                <span>{$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}</span>
                {#if isAutoVideoReclassification}
                    <span class="rounded-md border border-line bg-surface-raised px-1.5 py-0.5 text-ink">
                        {$_('detection.reclassification.auto_video_source', { default: 'Auto Video' })}
                    </span>
                {/if}
            </div>
            {#if displayLabel}
                <div class="mt-2 flex items-center justify-between gap-3">
                    <p class="min-w-0 truncate text-sm font-bold text-strong">{displayLabel}</p>
                    {#if displayScorePercent !== null}
                        <span class="shrink-0 text-xs font-bold text-accent-ink">{displayScorePercent}%</span>
                    {/if}
                </div>
            {/if}
        </div>
    </div>
</div>

<style>
    .card-analysis-close-ring {
        transform: rotate(-90deg);
    }

    .card-analysis-close-countdown {
        stroke-dasharray: 44;
        stroke-dashoffset: 0;
        animation: card-analysis-close-countdown 35s linear forwards;
    }

    @keyframes card-analysis-close-countdown {
        to {
            stroke-dashoffset: 44;
        }
    }

    @media (prefers-reduced-motion: reduce) {
        .card-analysis-close-countdown {
            animation: none;
            stroke-dashoffset: 22;
        }
    }
</style>
