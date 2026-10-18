<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ClassificationImageSource } from '../../api/settings';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';

    let { value = $bindable('frigate_snapshot'), delay = $bindable(12) }: { value?: ClassificationImageSource; delay?: number } = $props();

    const descriptionId = 'classification-image-source-desc';
    const recordingNoteId = 'classification-image-source-recording-note';
    // A Frigate config key, so it stays literal in every language.
    const CLEAN_COPY_SETTING = 'snapshots.clean_copy';

    // The recording frame costs Frigate work and can silently fall back, so its
    // terms are only shown, and announced with the select, once it is chosen.
    let recordingSelected = $derived(value === 'recording_snapshot');
</script>

<SettingsRow
    labelId="setting-classification-image-source"
    label={$_('settings.frigate.classification_image_source', { default: 'Identify new detections from' })}
    description={$_('settings.frigate.classification_image_source_desc', { default: 'The detection snapshot is faster. A recording frame can show more detail when the recording stream is larger than the detect stream and shows the same view. It does not guarantee a better identification.' })}
    {descriptionId}
    layout="stacked"
>
    <SettingsSelect
        id="classification-image-source"
        {value}
        ariaLabel={$_('settings.frigate.classification_image_source', { default: 'Identify new detections from' })}
        ariaDescribedBy={recordingSelected ? `${descriptionId} ${recordingNoteId}` : descriptionId}
        options={[
            { value: 'frigate_snapshot', label: $_('settings.frigate.classification_image_snapshot', { default: 'Detection snapshot' }) },
            { value: 'recording_snapshot', label: $_('settings.frigate.classification_image_recording', { default: 'Recording frame' }) }
        ]}
        onchange={(next) => (value = next)}
    />

    {#if recordingSelected}
        <div class="mt-3 min-w-0 space-y-2">
            <label id="recording-frame-delay-label" for="recording-frame-delay" class="block text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.frigate.recording_frame_delay', { default: 'Initial identification delay (seconds)' })}</label>
            <p id="recording-frame-delay-desc" class="break-words text-xs leading-relaxed text-slate-600 dark:text-slate-400">{$_('settings.frigate.recording_frame_delay_desc', { default: 'Wait 1 to 120 seconds after the first snapshot moment. Use the latest tracked snapshot metadata received during that wait. Identification and notifications arrive later. This does not wait for every event to end or reclassify saved detections.' })}</p>
            <input id="recording-frame-delay" class="input-base min-w-0" type="number" min="1" max="120" step="any" required bind:value={delay} aria-labelledby="recording-frame-delay-label" aria-describedby="recording-frame-delay-desc" />
        </div>
        <div
            id={recordingNoteId}
            data-recording-frame-note
            class="mt-3 space-y-1.5 break-words text-xs leading-relaxed text-slate-600 dark:text-slate-400"
        >
            <p>{$_('settings.frigate.classification_image_recording_cost', { default: 'Frigate decodes one recording frame for each detection, and YA-WAMF downloads and processes it.' })}</p>
            <p>{$_('settings.frigate.classification_image_recording_fallback', { default: 'Needs retained recordings and the clean snapshot copy in Frigate ({setting}). Recording frames usually become available 10 to 15 seconds later. After the selected delay, unavailable frames are normally retried for up to 18 seconds before using the detection snapshot. Smaller or differently shaped recording frames also use the snapshot.', values: { setting: CLEAN_COPY_SETTING } })}</p>
            <p>{$_('settings.frigate.classification_image_recording_scope', { default: 'Applies to new detections, including past events fetched as missed detections. Saving does not fetch past events or change existing photos; reclassification prefers saved photos.' })}</p>
        </div>
    {/if}
</SettingsRow>
