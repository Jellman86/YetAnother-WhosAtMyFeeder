<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSlider from './_primitives/SettingsSlider.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import StatusChip from '../ui/StatusChip.svelte';
    import { thresholdPercentText } from '../../utils/garden-threshold';

    // How sure a name must be: the birds' naming threshold and floor, learning from corrections,
    // and while the Garden beta is on, its own naming threshold for animals, in one card.
    let {
        threshold = $bindable(0.7),
        minConfidence = $bindable(0.4),
        personalizedRerankEnabled = $bindable(false),
        gardenEnabled = false,
        automaticNaming = $bindable(true),
        namingThreshold = $bindable(0.8)
    }: {
        threshold: number;
        minConfidence: number;
        personalizedRerankEnabled: boolean;
        gardenEnabled?: boolean;
        automaticNaming: boolean;
        namingThreshold: number;
    } = $props();
</script>

<SettingsCard
    title={$_('settings.naming.title', { default: 'Naming threshold' })}
    description={$_('settings.detection.acceptance_desc', { default: 'How sure the identification model must be before a visit is saved under a species name.' })}
>
    <div class="space-y-4">
        <SettingsSlider
            id="confidence-threshold-slider"
            label={$_('settings.detection.confidence_threshold')}
            description={$_('settings.detection.threshold_help', { default: 'At or above this score, a visit is saved under the species name.' })}
            bind:value={threshold}
            min={0}
            max={1}
            step={0.05}
            display={(value) => `${Math.round(value * 100)}%`}
            lowLabel={$_('settings.detection.threshold_loose')}
            highLabel={$_('settings.detection.threshold_strict')}
        />

        <SettingsSlider
            id="min-confidence-slider"
            label={$_('settings.detection.min_confidence_floor')}
            description={$_('settings.detection.floor_help')}
            bind:value={minConfidence}
            min={0}
            max={1}
            step={0.05}
            display={(value) => `${Math.round(value * 100)}%`}
            lowLabel={$_('settings.detection.floor_capture_all')}
            highLabel={$_('settings.detection.floor_reject_unsure')}
        />
    </div>
    <div class="space-y-4">
        <SettingsRow
            labelId="setting-personalized-rerank"
            label={$_('settings.detection.personalized_rerank', { default: 'Learn from my corrections' })}
            description={$_('settings.detection.personalized_rerank_desc', { default: "Uses the species you corrected to adjust scores for each camera and model. Off uses the model's own scores." })}
        >
            <SettingsToggle
                checked={personalizedRerankEnabled}
                labelledBy="setting-personalized-rerank"
                srLabel={$_('settings.detection.personalized_rerank', { default: 'Learn from my corrections' })}
                onchange={(v) => (personalizedRerankEnabled = v)}
            />
        </SettingsRow>
    </div>
    <!-- Garden names animals with a second threshold of its own; while the beta is on it sits here,
         beside the birds' one, so both are set in one place. -->
    {#if gardenEnabled}
        <section class="space-y-3" aria-labelledby="naming-garden-title" data-naming-garden>
            <div class="flex flex-wrap items-center gap-2">
                <h3 id="naming-garden-title" class="text-sm font-semibold text-strong">{$_('settings.naming.garden_title', { default: 'Garden animals' })}</h3>
                <StatusChip tone="neutral" label={$_('settings.beta.chip', { default: 'Beta' })} />
            </div>
            <div class="space-y-3" data-garden-naming>
                <SettingsRow
                    labelId="setting-garden-naming"
                    label={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                    description={$_('settings.beta.garden_naming_help', { default: 'Animals that reach the naming threshold are confirmed and named. Photos below it go to Dismissed, where you can restore them.' })}
                >
                    <SettingsToggle
                        checked={automaticNaming}
                        labelledBy="setting-garden-naming"
                        srLabel={$_('settings.beta.garden_naming', { default: 'Name animals automatically' })}
                        onchange={(value) => (automaticNaming = value)}
                    />
                </SettingsRow>
                {#if automaticNaming}
                    <SettingsSlider
                        id="garden-naming-threshold"
                        field="garden_naming_threshold"
                        label={$_('settings.beta.garden_naming_threshold', { default: 'Name an animal when this sure which one it is' })}
                        description={$_('settings.beta.garden_naming_threshold_help', { default: 'This is a second check, on which animal it is. At or above it, the animal is confirmed and named for you. Below it, its photo goes to Dismissed, where you can restore it.' })}
                        bind:value={namingThreshold}
                        min={0.7}
                        max={0.99}
                        step={0.01}
                        display={(value) => `${thresholdPercentText(value)}%`}
                        lowLabel={$_('garden.naming_low', { default: 'Names more' })}
                        highLabel={$_('garden.naming_high', { default: 'Names fewer' })}
                    />
                {:else}
                    <p class="text-sm text-muted">{$_('settings.beta.garden_naming_off', { default: 'Every animal waits in Needs review for you to confirm and name it.' })}</p>
                {/if}
            </div>
        </section>
    {/if}
</SettingsCard>
