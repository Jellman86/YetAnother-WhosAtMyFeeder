<script lang="ts">
    import DetectionCardAnalysisOverlay from '../src/lib/components/DetectionCardAnalysisOverlay.svelte';
    import FrameScanRibbon from '../src/lib/components/FrameScanRibbon.svelte';
    import type { ReclassificationProgress } from '../src/lib/stores/detections.svelte';

    const SCORES = [0.42, 0.66, 0.91, 0.88, 0.12, 0.73, 0.95, 0.58, 0.81, 0.34, 0.69, 0.9];
    const LABELS = ['Eurasian Blue Tit', 'Great Tit', 'Background'];

    let total = $state(12);
    let read = $state(0);

    let progress = $derived<ReclassificationProgress>({
        eventId: 'fixture-event',
        strategy: 'video',
        currentFrame: read,
        totalFrames: total,
        frameIndex: read,
        clipTotal: total,
        frameResults: Array.from({ length: read }, (_, index) => ({
            score: SCORES[index % SCORES.length],
            label: SCORES[index % SCORES.length] < 0.2 ? LABELS[2] : LABELS[index % 2]
        })),
        status: read >= total ? 'completed' : 'running',
        startedAt: 0,
        lastUpdateAt: 0
    });
</script>

<div class="flex flex-wrap gap-2">
    <button type="button" class="btn btn-secondary" onclick={() => { read = Math.min(total, read + 1); }}>Read next frame</button>
    <button type="button" class="btn btn-secondary" onclick={() => { read = Math.min(total, read + 4); }}>Read four frames</button>
    <button type="button" class="btn btn-secondary" onclick={() => { total = 240; read = 0; }}>Long clip</button>
</div>

<section data-fixture="card" class="relative aspect-[4/3] w-72 overflow-hidden rounded-2xl bg-slate-300">
    <DetectionCardAnalysisOverlay {progress} />
</section>

{#each ['compact', 'detail', 'overlay'] as const as variant (variant)}
    <section data-fixture={variant} class="w-full max-w-md">
        <FrameScanRibbon {progress} {variant} />
    </section>
{/each}
