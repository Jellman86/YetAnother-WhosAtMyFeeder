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
            ? 'aspect-[4/3] rounded-lg'
            : 'aspect-[16/10] rounded-xl'
    );
</script>

<div class="snapshot-analysis-scanner w-full border border-amber-300/40 bg-white/65 dark:bg-black/35 backdrop-blur-md shadow-xl {panelClass}">
    <div class="relative overflow-hidden border border-white/20 bg-slate-950 {imageClass}">
        {#if imageUrl}
            <div
                class="absolute inset-0 bg-cover bg-center"
                style={`background-image: url(${imageUrl})`}
            ></div>
            <div class="absolute inset-0 bg-gradient-to-t from-black/65 via-black/10 to-transparent"></div>
        {:else}
            <div class="absolute inset-0 bg-gradient-to-br from-slate-800 via-slate-950 to-black"></div>
            <div class="absolute inset-0 opacity-40" style="background-image: linear-gradient(135deg, rgba(255,255,255,.12) 0 1px, transparent 1px 12px);"></div>
        {/if}

        {#if !isComplete}
            <div class="snapshot-analysis-sweep motion-reduce:animate-none absolute inset-x-0 -top-1/3 h-1/3 bg-gradient-to-b from-transparent via-amber-200/55 to-transparent"></div>
            <div class="absolute inset-0 border-y border-amber-200/25"></div>
        {/if}

        <div class="absolute left-2 top-2 inline-flex items-center gap-1.5 rounded-md border border-amber-200/25 bg-black/55 px-2 py-1 text-[9px] font-black uppercase tracking-widest text-amber-100">
            <span class="h-1.5 w-1.5 rounded-full bg-amber-300 {isComplete ? '' : 'motion-safe:animate-pulse'}"></span>
            {$_('detection.reclassification.snapshot_scanning', { default: 'Snapshot scan' })}
        </div>

        {#if latestLabel}
            <div class="absolute inset-x-2 bottom-2 rounded-lg border border-white/10 bg-black/55 px-2 py-1.5 text-white">
                <div class="truncate text-[11px] font-black">{latestLabel}</div>
                {#if latestScore !== null}
                    <div class="mt-0.5 text-[9px] font-black uppercase tracking-widest text-amber-200">{latestScore}%</div>
                {/if}
            </div>
        {/if}
    </div>

    <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-amber-100/70 dark:bg-white/10">
        <div
            class="h-full rounded-full bg-gradient-to-r from-amber-300 via-teal-300 to-cyan-300 transition-all duration-300 ease-out motion-reduce:transition-none"
            style={`width: ${progressPercent}%`}
        ></div>
    </div>

    {#if showFooter}
        <div class="mt-2 flex items-center justify-between gap-3 px-1">
            <span class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                {$_('detection.reclassification.snapshot_fallback_badge', { default: 'Snapshot fallback' })}
            </span>
            <span class="text-[10px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
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
