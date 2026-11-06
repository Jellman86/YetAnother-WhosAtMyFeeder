<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Detection } from '../api';

    let { evidence }: { evidence: Detection['classification_input'] } = $props();
    const wholeView = $derived(evidence?.is_cropped === false && evidence.source !== 'frigate_sublabel');
</script>

<p class="mt-1 text-xs text-slate-500 dark:text-slate-400" data-classification-source>
    {#if evidence?.source === 'owner_species_choice'}
        {$_('detection.named_from.owner', { default: 'Named by you' })}
    {:else if evidence?.source === 'frigate_sublabel'}
        {$_('detection.named_from.frigate', { default: "Named from Frigate’s sub-label" })}
    {:else if wholeView}
        {$_('detection.named_from.whole_view', { default: 'Named from the whole camera view, so it may not refer to one bird' })}
    {:else if (evidence?.supporting_frames ?? 0) > 1}
        {$_('detection.named_from.video', { default: 'Named from video analysis, {frames} frames', values: { frames: evidence?.supporting_frames ?? 0 } })}
    {:else if evidence?.source === 'recording_snapshot_frigate_hint_crop'}
        {$_('detection.named_from.recording', { default: 'Named from Frigate’s tracked bird in the recording frame' })}
    {:else if evidence?.source === 'snapshot_frigate_hint_crop' || evidence?.source === 'frigate_snapshot_cropped'}
        {$_('detection.named_from.snapshot', { default: 'Named from Frigate’s tracked bird in the snapshot' })}
    {:else if evidence?.is_cropped}
        {$_('detection.named_from.crop', { default: 'Named from a bird crop' })}
    {:else}
        {$_('detection.named_from.unknown', { default: 'The identification source was not recorded' })}
    {/if}
</p>
