<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ReclassificationProgress } from '../stores/detections.svelte';
    import { frameScan, type FrameScanBar, type FrameScanTone } from '../utils/frame-scan';

    /**
     * A clip scan drawn like the audio sonograms: one bar per sampled frame, its height the
     * model's confidence, a playhead on the frame being read. Every frame keeps its place from the
     * first update, so nothing slides and the layout never moves as results arrive.
     *
     * `backdrop` fills whatever it is placed in and is drawn behind text, so it is decorative:
     * the surface that uses it states the progress in words.
     */
    type RibbonVariant = 'backdrop' | 'card' | 'compact' | 'detail' | 'overlay';

    let { progress, variant = 'overlay' }: { progress: ReclassificationProgress; variant?: RibbonVariant } = $props();

    let scan = $derived(frameScan(progress));
    let roomy = $derived(variant === 'detail' || variant === 'overlay');
    let decorative = $derived(variant === 'backdrop');
    let barsHeightClass = $derived(
        decorative ? 'h-full' : roomy ? 'h-20' : variant === 'compact' ? 'h-12' : 'h-10'
    );
    let panelClass = $derived(
        variant === 'backdrop'
            ? 'h-full'
            : variant === 'card'
            ? ''
            : variant === 'compact'
                ? 'rounded-lg border border-line-soft bg-surface/90 p-2'
                : 'rounded-xl border border-line-soft bg-surface/90 p-3'
    );
    let playheadLeft = $derived(
        scan.nextPosition === null ? null : ((scan.nextPosition - 0.5) / scan.total) * 100
    );
    let valueText = $derived(
        scan.complete
            ? $_('detection.frame_scan.complete', { values: { total: scan.total }, default: 'All {total} frames read' })
            : $_('detection.frame_scan.value_text', {
                  values: { read: scan.readCount, total: scan.total },
                  default: '{read} of {total} frames read'
              })
    );

    const TONE_CLASS: Record<FrameScanTone, string> = {
        strong: 'bg-success-500',
        moderate: 'bg-success-300 dark:bg-success-700',
        weak: 'bg-slate-400 dark:bg-slate-500',
        pending: 'h-1 bg-slate-300 dark:bg-slate-600'
    };

    function barTitle(bar: FrameScanBar): string {
        if (bar.label === null || bar.scorePercent === null) {
            return $_('detection.frame_scan.bar_waiting', {
                values: { position: bar.position },
                default: 'Frame {position}: not read yet'
            });
        }
        return $_('detection.frame_scan.bar_read', {
            values: { position: bar.position, label: bar.label, score: bar.scorePercent },
            default: 'Frame {position}: {label} {score}%'
        });
    }
</script>

<div class="frame-scan-ribbon w-full {panelClass}" data-frame-scan-variant={variant} aria-hidden={decorative ? 'true' : undefined}>
    <div
        class={decorative ? 'h-full' : undefined}
        role={decorative ? undefined : 'progressbar'}
        aria-label={decorative ? undefined : $_('detection.frame_scan.title', { default: 'Video frames read' })}
        aria-valuemin={decorative ? undefined : 0}
        aria-valuemax={decorative ? undefined : scan.total}
        aria-valuenow={decorative ? undefined : scan.readCount}
        aria-valuetext={decorative ? undefined : valueText}
    >
        <div class="relative flex {barsHeightClass} items-end gap-px {decorative ? '' : 'border-b border-line'}" aria-hidden="true">
            {#each scan.bars as bar (bar.position)}
                <div class="flex h-full min-w-0 flex-1 items-end" title={barTitle(bar)}>
                    <div
                        class="frame-scan-bar w-full rounded-t-sm transition-[height] duration-300 ease-out motion-reduce:transition-none {TONE_CLASS[bar.tone]}"
                        data-frame-scan-tone={bar.tone}
                        style:height={bar.tone === 'pending' ? null : `${bar.heightPercent}%`}
                    ></div>
                </div>
            {/each}
            {#if playheadLeft !== null}
                <div
                    class="frame-scan-playhead pointer-events-none absolute -bottom-1 -top-1 w-0.5 -translate-x-1/2 rounded-full bg-slate-700 transition-[left] duration-300 ease-out motion-reduce:transition-none dark:bg-slate-200"
                    style:left={`${playheadLeft}%`}
                ></div>
            {/if}
        </div>
    </div>

    {#if roomy}
        <div class="mt-3 flex items-center gap-3">
            <div class="relative aspect-[4/3] w-24 shrink-0 overflow-hidden rounded-md bg-surface-raised">
                {#if scan.latest?.thumb}
                    <img
                        src={`data:image/jpeg;base64,${scan.latest.thumb}`}
                        alt=""
                        class="absolute inset-0 h-full w-full object-cover"
                    />
                {/if}
            </div>
            <div class="min-w-0 flex-1 space-y-0.5">
                <p class="text-3xs font-semibold text-slate-500 tabular-nums dark:text-slate-400">{valueText}</p>
                {#if scan.latest}
                    <p class="flex items-baseline justify-between gap-3">
                        <span class="min-w-0 truncate text-sm font-semibold text-slate-900 dark:text-white">{scan.latest.label}</span>
                        <span class="shrink-0 text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-200">{scan.latest.scorePercent}%</span>
                    </p>
                {:else}
                    <p class="text-sm text-slate-600 dark:text-slate-300">
                        {$_('detection.frame_scan.waiting', { default: 'Waiting for the first frame' })}
                    </p>
                {/if}
                {#if scan.best}
                    <p class="truncate text-2xs text-slate-500 dark:text-slate-400">
                        {$_('detection.frame_scan.best', {
                            values: { position: scan.best.position, label: scan.best.label, score: scan.best.scorePercent },
                            default: 'Clearest so far: frame {position}, {label} {score}%'
                        })}
                    </p>
                {/if}
            </div>
        </div>

        <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-3xs text-slate-500 dark:text-slate-400">
            <li class="flex items-center gap-1.5">
                <span class="h-2.5 w-2.5 rounded-sm bg-success-500" aria-hidden="true"></span>
                {$_('detection.frame_scan.legend_strong', { default: '80% and over' })}
            </li>
            <li class="flex items-center gap-1.5">
                <span class="h-2.5 w-2.5 rounded-sm bg-success-300 dark:bg-success-700" aria-hidden="true"></span>
                {$_('detection.frame_scan.legend_moderate', { default: '50 to 79%' })}
            </li>
            <li class="flex items-center gap-1.5">
                <span class="h-2.5 w-2.5 rounded-sm bg-slate-400 dark:bg-slate-500" aria-hidden="true"></span>
                {$_('detection.frame_scan.legend_weak', { default: 'Under 50%' })}
            </li>
        </ul>
    {/if}
</div>
