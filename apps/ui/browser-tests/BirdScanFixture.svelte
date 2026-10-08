<script lang="ts">
    import BirdScanControl from '../src/lib/components/BirdScanControl.svelte';
    let candidate = $state<string | null>('scene-1');
    let completions = $state(0);
    let revision = $state<string | null>('old-revision');
</script>
<h1>Find additional birds</h1>
<BirdScanControl eventId="fixture-event" candidateId={candidate} imageVersion={candidate ? `${candidate}.jpg${revision ? `?v=${revision}` : ''}` : null} oncompleted={() => { completions += 1; }} />
<p data-scan-completions>{completions}</p>
<button type="button" onclick={() => { candidate = 'scene-2'; }}>Next photograph</button>
<button type="button" onclick={() => { candidate = null; }}>No whole frame</button>

<button type="button" onclick={() => { revision = 'new-revision'; }}>Refresh photograph</button>
<button type="button" onclick={() => { revision = null; }}>No image revision</button>
