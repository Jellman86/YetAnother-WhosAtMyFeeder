<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ReclassificationProgress } from '../stores/detections.svelte';

    type ScannerVariant = 'compact' | 'overlay';

    let {
        progress,
        imageUrl = null,
        variant = 'overlay',
        showFooter = variant !== 'compact'
    }: {
        progress: ReclassificationProgress;
        imageUrl?: string | null;
        variant?: ScannerVariant;
        showFooter?: boolean;
    } = $props();

    type FrameResult = ReclassificationProgress['frameResults'][number];
    function hasFrameResult(frame: FrameResult | undefined): frame is FrameResult {
        return Boolean(frame);
    }

    let safeCurrentFrame = $derived(
        Number.isFinite(progress.currentFrame) ? Math.max(0, Math.floor(progress.currentFrame)) : 0
    );
    let safeTotalFrames = $derived(
        Number.isFinite(progress.totalFrames) ? Math.max(1, Math.floor(progress.totalFrames)) : 1
    );
    let isComplete = $derived(progress.status === 'completed' || safeCurrentFrame >= safeTotalFrames);
    let progressPercent = $derived(Math.max(2, Math.min(100, Math.round((safeCurrentFrame / safeTotalFrames) * 100))));
    let latestFrame = $derived(progress.frameResults.findLast(hasFrameResult));
    let latestLabel = $derived(latestFrame?.label ?? null);
    let latestScore = $derived(
        typeof latestFrame?.score === 'number' ? Math.round(latestFrame.score * 100) : null
    );
    let panelClass = $derived(
        variant === 'compact'
            ? 'rounded-xl p-2'
            : 'rounded-2xl p-3'
    );
    let imageClass = $derived(
        variant === 'compact'
            ? 'aspect-4/3 rounded-lg'
            : 'aspect-16/10 rounded-xl'
    );
</script>

<div class="snapshot-analysis-scanner w-full border border-slate-200/70 bg-white/80 dark:border-slate-700/60 dark:bg-slate-950/80 {panelClass}">
    <div class="relative overflow-hidden border border-white/20 bg-slate-950 {imageClass}">
        {#if imageUrl}
            <div
                class="absolute inset-0 bg-cover bg-center"
                style={`background-image: url(${imageUrl})`}
            ></div>
            <div class="absolute inset-0 bg-linear-to-t/srgb from-black/65 via-black/10 to-transparent"></div>
        {:else}
            <div class="absolute inset-0 bg-slate-900"></div>
        {/if}

        {#if !isComplete}
            <div class="snapshot-analysis-sweep motion-reduce:animate-none absolute inset-x-0 -top-1/3 h-1/3 bg-linear-to-b/srgb from-transparent via-brand-200/55 to-transparent"></div>
            <div class="absolute inset-0 border-y border-brand-200/25"></div>
        {/if}

        <div class="absolute left-2 top-2 inline-flex items-center gap-1.5 rounded-md border border-brand-200/25 bg-black/55 px-2 py-1 text-3xs font-bold text-brand-100">
            <span class="h-1.5 w-1.5 rounded-full bg-brand-300 {isComplete ? '' : 'motion-safe:animate-pulse'}"></span>
            {$_('detection.reclassification.snapshot_scanning', { default: 'Snapshot scan' })}
        </div>

        {#if latestLabel}
            <div class="absolute inset-x-2 bottom-2 rounded-lg border border-white/10 bg-black/55 px-2 py-1.5 text-white">
                <div class="truncate text-2xs font-bold">{latestLabel}</div>
                {#if latestScore !== null}
                    <div class="mt-0.5 text-3xs font-bold text-brand-200">{latestScore}%</div>
                {/if}
            </div>
        {/if}
    </div>

    <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-brand-100/70 dark:bg-white/10">
        <div
            class="h-full rounded-full bg-brand-400 transition-all duration-300 ease-out motion-reduce:transition-none"
            style={`width: ${progressPercent}%`}
        ></div>
    </div>

    {#if showFooter}
        <div class="mt-2 flex items-center justify-between gap-3 px-1">
            <span class="text-3xs font-bold text-slate-600 dark:text-slate-400">
                {$_('detection.reclassification.snapshot_fallback_badge', { default: 'Snapshot fallback' })}
            </span>
            <span class="text-3xs font-bold text-brand-700 dark:text-brand-300">
                {$_('detection.reclassification.frame_progress', {
                    values: {
                        current: Math.min(safeCurrentFrame, safeTotalFrames),
                        total: safeTotalFrames
                    }
                })}
            </span>
        </div>
    {/if}
</div>

<style>
    .snapshot-analysis-sweep {
        animation: snapshot-scan 1.45s ease-in-out infinite;
    }

    @keyframes snapshot-scan {
        0% {
            transform: translateY(-80%);
        }
        50% {
            transform: translateY(260%);
        }
        100% {
            transform: translateY(-80%);
        }
    }
</style>
