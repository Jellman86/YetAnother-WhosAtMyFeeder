<script lang="ts">
    import BirdScanControl from '../src/lib/components/BirdScanControl.svelte';
    import { BirdScan } from '../src/lib/utils/bird-scan.svelte';
    let candidate = $state<string | null>('scene-1');
    let completions = $state(0);
    let revision = $state<string | null>('old-revision');
    // As the record does: the host owns the scan and hands it to the row.
    const scan = new BirdScan(
        () => ({ eventId: 'fixture-event', candidateId: candidate, imageVersion: candidate ? `${candidate}.jpg${revision ? `?v=${revision}` : ''}` : null }),
        () => { completions += 1; }
    );
</script>
<h1>Find additional birds</h1>
<BirdScanControl {scan} sceneImageUrl={candidate ? `/fixture-scenes/${candidate}.svg` : null} />
<p data-scan-completions>{completions}</p>
<button type="button" onclick={() => { candidate = 'scene-2'; }}>Next photograph</button>
<button type="button" onclick={() => { candidate = null; }}>No whole frame</button>

<button type="button" onclick={() => { revision = 'new-revision'; }}>Refresh photograph</button>
<button type="button" onclick={() => { revision = null; }}>No image revision</button>
