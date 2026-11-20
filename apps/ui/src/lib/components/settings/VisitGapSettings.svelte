<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';

    // How captures become visits (#1044): one gap, in seconds, for birds and Garden animals alike.
    // The card says what the gap can and cannot do, and what it does to history, because a shorter
    // gap changes every visit count the owner reads.
    let { visitGapSeconds = $bindable(60) }: { visitGapSeconds: number } = $props();
</script>

<SettingsCard
        id="settings-group-visit-gap"
    title={$_('settings.visit_gap.title', { default: 'Counting visits' })}
    description={$_('settings.visit_gap.desc', { default: 'Captures of one species on one camera no more than the visit gap apart count as one visit. Garden animals are grouped the same way.' })}
>
    <SettingsRow
        labelId="setting-visit-gap"
        label={$_('settings.visit_gap.label', { default: 'Visit gap' })}
        description={$_('settings.visit_gap.range', { default: 'From 5 to 300 seconds. The default is 60.' })}
        descriptionId="setting-visit-gap-range"
    >
        <div class="flex items-center justify-start gap-2 md:justify-end" data-visit-gap>
            <div class="w-28">
                <SettingsInput
                    id="visit-gap-seconds"
                    field="visit_gap_seconds"
                    type="number"
                    min={5}
                    max={300}
                    step={1}
                    value={visitGapSeconds}
                    ariaLabel={$_('settings.visit_gap.label', { default: 'Visit gap' })}
                    describedBy="setting-visit-gap-range visit-gap-unit"
                    oninput={(next) => (visitGapSeconds = Number(next))}
                />
            </div>
            <span id="visit-gap-unit" class="text-sm text-muted">{$_('settings.visit_gap.unit', { default: 'seconds' })}</span>
        </div>
    </SettingsRow>
    <div data-visit-gap-notes>
        <div class="max-w-prose space-y-2 text-sm leading-snug text-muted">
            <p>{$_('settings.visit_gap.limit', { default: 'A shorter gap splits a busy feeder into more, shorter visits. It cannot count individual birds: when one bird leaves as another of the same species lands, any gap still sees one visit.' })}</p>
            <p>{$_('settings.visit_gap.history', { default: 'After you save, every page groups visits with the new gap. Days whose captures the history window has already removed keep the visit counts they were saved with.' })}</p>
        </div>
    </div>
</SettingsCard>
