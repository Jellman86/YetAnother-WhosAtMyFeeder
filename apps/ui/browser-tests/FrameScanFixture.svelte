<script lang="ts">
    import DetectionCardAnalysisOverlay from '../src/lib/components/DetectionCardAnalysisOverlay.svelte';
    import DetectionCard from '../src/lib/components/DetectionCard.svelte';
    import DetectionRow from '../src/lib/components/DetectionRow.svelte';
    import FrameScanRibbon from '../src/lib/components/FrameScanRibbon.svelte';
    import { detectionsStore, type ReclassificationProgress } from '../src/lib/stores/detections.svelte';
    import type { Detection } from '../src/lib/api';

    const SCORES = [0.42, 0.66, 0.91, 0.88, 0.12, 0.73, 0.95, 0.58, 0.81, 0.34, 0.69, 0.9];
    const LABELS = ['Eurasian Blue Tit', 'Great Tit', 'Background'];

    let total = $state(12);
    let read = $state(0);

    // The list row reads the live store, as it does in the Explorer, so the fixture feeds the
    // same frames through it.
    function row(id: string, name: string): Detection {
        return { frigate_event: id, display_name: name, common_name: name, camera_name: 'birdcam', detection_time: '2026-10-01T12:00:00Z', score: 0.94, has_clip: true };
    }
    let opened = $state('none');
    let played = $state('none');
    const scanningRow = row('row-scan', 'Great Tit');
    const quietRow = row('row-quiet', 'House Sparrow');
    const lastRow = row('row-last', 'Blue Tit');

    function scoreAt(index: number): number {
        return SCORES[index % SCORES.length];
    }

    function labelAt(index: number): string {
        return scoreAt(index) < 0.2 ? LABELS[2] : LABELS[index % 2];
    }

    function feedRow(): void {
        detectionsStore.startReclassification(scanningRow.frigate_event, total, 'video');
        for (let frame = 1; frame <= read; frame += 1) {
            detectionsStore.updateReclassificationProgress(scanningRow.frigate_event, frame, total, scoreAt(frame - 1), labelAt(frame - 1));
        }
        if (read >= total) detectionsStore.completeReclassification(scanningRow.frigate_event, [], 'success');
    }

    function advance(frames: number): void {
        read = Math.min(total, read + frames);
        feedRow();
    }

    feedRow();

    let progress = $derived<ReclassificationProgress>({
        eventId: 'fixture-event',
        strategy: 'video',
        currentFrame: read,
        totalFrames: total,
        frameIndex: read,
        clipTotal: total,
        frameResults: Array.from({ length: read }, (_, index) => ({ score: scoreAt(index), label: labelAt(index) })),
        status: read >= total ? 'completed' : 'running',
        startedAt: 0,
        lastUpdateAt: 0
    });
</script>

<div class="flex flex-wrap gap-2">
    <button type="button" class="btn btn-secondary" onclick={() => advance(1)}>Read next frame</button>
    <button type="button" class="btn btn-secondary" onclick={() => advance(4)}>Read four frames</button>
    <button type="button" class="btn btn-secondary" onclick={() => { total = 240; read = 0; feedRow(); }}>Long clip</button>
</div>

<section data-fixture="card" class="relative aspect-4/3 w-72 overflow-hidden rounded-2xl bg-slate-300">
    <DetectionCardAnalysisOverlay {progress} />
</section>

<!-- Real Explorer cards: one under analysis, one idle, so a test can see what the keyboard reaches. -->
<div class="flex flex-wrap gap-4" data-fixture="real-cards">
    <div class="w-72" data-fixture="card-analysing">
        <DetectionCard detection={scanningRow} onclick={() => (opened = 'analysing')} onPlay={() => (played = 'analysing')} />
    </div>
    <div class="w-72" data-fixture="card-idle">
        <DetectionCard detection={quietRow} onclick={() => (opened = 'idle')} onPlay={() => (played = 'idle')} />
    </div>
</div>
<p data-fixture-opened={opened} data-fixture-played={played}>Opened {opened}, played {played}</p>

<section data-fixture="row" class="overflow-hidden rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
    <DetectionRow detection={quietRow} />
    <DetectionRow detection={scanningRow} />
    <DetectionRow detection={lastRow} />
</section>

{#each ['compact', 'detail', 'overlay'] as const as variant (variant)}
    <section data-fixture={variant} class="w-full max-w-md">
        <FrameScanRibbon {progress} {variant} />
    </section>
{/each}
