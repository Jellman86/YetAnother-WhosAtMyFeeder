<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ReclassificationProgress } from '../stores/detections.svelte';

    type FilmReelVariant = 'compact' | 'detail' | 'overlay';

    let {
        progress,
        variant = 'overlay',
        showFooter = variant !== 'compact'
    }: {
        progress: ReclassificationProgress;
        variant?: FilmReelVariant;
        showFooter?: boolean;
    } = $props();

    let safeCurrentFrame = $derived(
        Number.isFinite(progress.currentFrame) ? Math.max(0, Math.floor(progress.currentFrame)) : 0
    );
    let safeTotalFrames = $derived(
        Number.isFinite(progress.totalFrames) ? Math.max(1, Math.floor(progress.totalFrames)) : 1
    );
    let isComplete = $derived(progress.status === 'completed' || safeCurrentFrame >= safeTotalFrames);
    let displayFrameIndex = $derived(progress.frameIndex || safeCurrentFrame);
    let displayClipTotal = $derived(progress.clipTotal || safeTotalFrames);

    let visibleWindowSize = $derived.by(() => {
        switch (variant) {
            case 'compact':
                return 7;
            case 'detail':
                return 9;
            default:
                return 11;
        }
    });
    let renderBuffer = $derived(2);
    let activeIndexZeroBased = $derived(
        Math.min(Math.max((safeCurrentFrame > 0 ? safeCurrentFrame - 1 : 0), 0), safeTotalFrames - 1)
    );
    let visibleStart = $derived.by(() => {
        const centered = Math.max(0, activeIndexZeroBased - Math.floor(visibleWindowSize / 2));
        return Math.min(centered, Math.max(0, safeTotalFrames - visibleWindowSize));
    });
    let renderStart = $derived(Math.max(0, visibleStart - renderBuffer));
    let renderEndExclusive = $derived(Math.min(safeTotalFrames, visibleStart + visibleWindowSize + renderBuffer));
    let visibleIndices = $derived(
        Array.from({ length: Math.max(0, renderEndExclusive - renderStart) }, (_, offset) => renderStart + offset)
    );
    let translatePct = $derived(
        visibleIndices.length > 0
            ? ((visibleStart - renderStart) / visibleIndices.length) * 100
            : 0
    );
    let sprocketCount = $derived(Math.max(visibleIndices.length, 1));
    let frameCellClass = $derived.by(() => {
        if (variant === 'compact') return 'w-[52px]';
        if (variant === 'detail') return 'w-[68px]';
        return 'w-[74px]';
    });
    let frameGapClass = $derived(variant === 'compact' ? 'gap-1.5' : 'gap-2');
    let framePadClass = $derived(variant === 'compact' ? 'p-2' : 'p-3');
    let showFrameScores = $derived(variant !== 'compact');

    function frameTone(frame?: ReclassificationProgress['frameResults'][number]) {
        if (!frame) return 'bg-slate-200/70 dark:bg-white/10';
        if (frame.score >= 0.8) return 'bg-emerald-400/75';
        if (frame.score >= 0.5) return 'bg-teal-400/70';
        return 'bg-amber-400/75';
    }

    function frameScoreTone(frame?: ReclassificationProgress['frameResults'][number]) {
        if (!frame) return 'text-slate-500 dark:text-slate-400';
        if (frame.score >= 0.8) return 'text-emerald-600 dark:text-emerald-300';
        if (frame.score >= 0.5) return 'text-teal-700 dark:text-teal-300';
        return 'text-amber-700 dark:text-amber-300';
    }
</script>

<div class="w-full rounded-2xl bg-white/45 dark:bg-black/35 border border-slate-200/70 dark:border-white/10 backdrop-blur-md shadow-xl {framePadClass}">
    <div class="rounded-xl overflow-hidden border border-slate-200/70 dark:border-white/10 bg-slate-950/90 dark:bg-slate-950/80">
        <div class="px-2 py-1 border-b border-white/10 bg-black/30">
            <div class="flex {frameGapClass}">
                {#each Array(sprocketCount) as _, idx}
                    <div
                        class="h-1 w-2 rounded-full bg-white/30"
                        style={visibleIndices[idx] === undefined ? 'opacity:0' : ''}
                        aria-hidden="true"
                    ></div>
                {/each}
            </div>
        </div>

        <div class="overflow-hidden px-2 py-2">
            <div
                class="flex {frameGapClass} transition-transform duration-300 ease-out motion-reduce:transition-none"
                style={`transform: translateX(-${translatePct}%);`}
            >
                {#each visibleIndices as frameIdx (frameIdx)}
                    {@const frame = progress.frameResults[frameIdx]}
                    {@const isCurrent = !isComplete && frameIdx === activeIndexZeroBased}
                    <div class="shrink-0 {frameCellClass}">
                        <div
                            class="aspect-[4/3] rounded-lg overflow-hidden border border-white/10 relative {frameTone(frame)} {isCurrent ? 'ring-2 ring-teal-300/90 shadow-lg shadow-teal-400/20 motion-safe:animate-pulse' : ''}"
                            title={frame ? `${frame.label} • ${(frame.score * 100).toFixed(0)}%` : $_('detection.video_analysis.in_progress', { default: 'Analyzing video...' })}
                        >
                            {#if frame?.thumb}
                                <div
                                    class="absolute inset-0 bg-cover bg-center"
                                    style={`background-image: url(data:image/jpeg;base64,${frame.thumb})`}
                                ></div>
                                <div class="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent"></div>
                            {:else}
                                <div class="absolute inset-0 bg-gradient-to-br from-white/5 to-white/0"></div>
                            {/if}
                            <div class="absolute left-1 top-1 text-[9px] font-black uppercase tracking-wider px-1 py-0.5 rounded bg-black/55 text-white/90">
                                {frameIdx + 1}
                            </div>
                            {#if isCurrent}
                                <div class="absolute right-1 top-1 h-2 w-2 rounded-full bg-teal-300 shadow shadow-teal-300/70"></div>
                            {/if}
                        </div>
                        {#if showFrameScores}
                            <div class="mt-1 text-center text-[10px] font-black uppercase tracking-widest {frameScoreTone(frame)}">
                                {frame ? `${Math.round(frame.score * 100)}%` : '--'}
                            </div>
                        {/if}
                    </div>
                {/each}
            </div>
        </div>

        <div class="px-2 py-1 border-t border-white/10 bg-black/30">
            <div class="flex {frameGapClass}">
                {#each Array(sprocketCount) as _, idx}
                    <div
                        class="h-1 w-2 rounded-full bg-white/30"
                        style={visibleIndices[idx] === undefined ? 'opacity:0' : ''}
                        aria-hidden="true"
                    ></div>
                {/each}
            </div>
        </div>
    </div>

    {#if showFooter}
        <div class="mt-2 flex items-center justify-between gap-3 px-1">
            <span class="text-[10px] font-black text-slate-500 dark:text-slate-400 uppercase tracking-widest">
                {$_('detection.reclassification.frame_grid')}
            </span>
            <span class="text-[10px] font-black text-teal-600 dark:text-teal-300 uppercase tracking-widest">
                {$_('detection.reclassification.frame_progress', { values: { current: displayFrameIndex, total: displayClipTotal } })}
            </span>
        </div>
    {/if}
</div>
