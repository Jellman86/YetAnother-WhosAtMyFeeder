<script lang="ts">
    import { tick } from 'svelte';
    import { useDisclosure } from '../../settings/disclosures.svelte';
    import { RUNTIME_DISCLOSURES } from '../../settings/runtime-problem';
    import { settingsMoreId } from '../../settings/settings-more';
    import { _ } from 'svelte-i18n';
    import ModelManager from '../../pages/models/ModelManager.svelte';
    import type { ClassifierStatus } from '../../api';
    import { BIRD_MODEL_REGION_OVERRIDE_VALUES, type BirdModelRegionOverride } from '../../settings/bird-model-region-override';
    import type { BirdFinder, BirdFinderProvider } from '../../settings/bird-finder';
    import type { DeviceCheck } from '../../settings/device-check.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import IdentificationStatusLine from '../IdentificationStatusLine.svelte';
    import { classifierRuntimeState } from '../../utils/classifier-runtime-state';
    import { settingsScrollBehaviour } from '../../settings/scroll-behaviour';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import NativeProfileRevalidation from './NativeProfileRevalidation.svelte';

    // What names birds now and the models that do it. Hardware, with the runtime report, is under
    // the section's More options; the device check both start is shared through `deviceCheck`.
    let {
        autoVideoClassification = false,
        birdModelRegionOverride = $bindable<BirdModelRegionOverride>('auto'),
        birdFinder = $bindable<BirdFinder>('yolox_tiny'),
        birdFinderProvider = $bindable<BirdFinderProvider>('auto'),
        imageExecutionMode = 'subprocess',
        classifierStatus = null,
        modelsListed = $bindable(false),
        deviceCheck,
        onrefreshclassifierstatus,
        onopenlocationsettings,
        onopenmodelevaluation
    }: {
        /** Shown in the status line; switched in Detection, with the other video checks. */
        autoVideoClassification?: boolean;
        birdModelRegionOverride: BirdModelRegionOverride;
        birdFinder: BirdFinder;
        birdFinderProvider?: BirdFinderProvider;
        imageExecutionMode?: 'in_process' | 'subprocess' | string;
        classifierStatus: ClassifierStatus | null;
        /** True once the model list has its first answer, so Hardware's height moves nothing. */
        modelsListed?: boolean;
        deviceCheck: DeviceCheck;
        /** Re-reads the live runtime only; resolves false when it could not be read. */
        onrefreshclassifierstatus?: () => Promise<boolean>;
        onopenlocationsettings?: () => void;
        onopenmodelevaluation?: () => void;
    } = $props();

    const RUNTIME_REPORT_ID = 'detection-runtime-report';
    const RUNTIME_REPORT_SECTION_ID = RUNTIME_DISCLOSURES[0];
    const FIELD_WAIT_FRAMES = 60;

    const healthIssueCount = $derived(
        (classifierStatus?.fallback_reason ? 1 : 0) +
            (classifierStatus?.model_config_warnings?.length ?? 0) +
            (classifierStatus?.openvino_model_compile_ok === false ? 1 : 0) +
            (classifierStatus?.image_flavor_warning ? 1 : 0) +
            (classifierStatus?.cuda_probe_error ? 1 : 0)
    );
    const runtimeState = $derived(classifierRuntimeState(classifierStatus, imageExecutionMode));

    // The report is in Hardware, under More options: the link opens both, then waits for the
    // report to be drawn before scrolling to it.
    const runtimeReport = useDisclosure(() => ({ id: RUNTIME_REPORT_SECTION_ID }));
    const more = useDisclosure(() => ({ id: settingsMoreId('identification') }));
    async function openRuntimeReport(): Promise<void> {
        more.open = true;
        runtimeReport.open = true;
        for (let frame = 0; frame < FIELD_WAIT_FRAMES; frame += 1) {
            await tick();
            const report = document.getElementById(RUNTIME_REPORT_ID);
            if (report) {
                report.scrollIntoView({ block: 'start', behavior: settingsScrollBehaviour() });
                return;
            }
            await new Promise((resolve) => requestAnimationFrame(resolve));
        }
    }

    // Scoped to one finder, so the run never swaps the active identification model.
    function checkFinderDevices(modelId: string): Promise<void> {
        return deviceCheck.run([modelId]);
    }
</script>

<!-- At the narrowest widths with enlarged text a long word may break, rather than push the page sideways. -->
<div class="space-y-6 wrap-anywhere">

    <NativeProfileRevalidation />

    <!-- One sentence of what names birds right now; trouble adds a line that says where to look. -->
    <div class="min-h-14 space-y-2" data-models-status>
        <IdentificationStatusLine {classifierStatus} />
        <!-- The report it opens is in Hardware, under More options, which shows once the model list has loaded. -->
        {#if healthIssueCount > 0 && modelsListed}
            <button
                type="button"
                onclick={openRuntimeReport}
                class="focus-ring inline-flex min-h-11 items-center rounded-md text-left text-sm font-medium text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200"
                data-models-report-link
            >
                {$_('settings.models.status_report_link', { values: { count: healthIssueCount }, default: '{count, plural, one {# thing to check in the runtime report} other {# things to check in the runtime report}}' })}
            </button>
        {/if}
        {#if runtimeState.restartRecommended}
            <p class="text-sm text-attention-800 dark:text-attention-200" role="status">
                {runtimeState.recovering
                    ? $_('settings.detection.band_native_recovering', { default: 'Waiting for isolated workers to resume classification.' })
                    : $_('settings.detection.band_native_recovered', { default: 'Classification resumed in isolated workers.' })}
                {$_('settings.detection.band_native_restart', { default: 'Restart the container to release the stalled runtime.' })}
            </p>
        {/if}
    </div>

    <SettingsCard
        title={$_('settings.detection.models_card_title', { default: 'Models' })}
        description={$_('settings.detection.models_card_desc', { default: 'Two models work in turn. The bird finder locates each bird in the camera frame; the identification model names its species.' })}
    >
        <div class="space-y-4">
                <SettingsRow
                    labelId="setting-region-override"
                    label={$_('settings.detection.region_override_title', { default: 'Bird model region' })}
                    description={$_('settings.detection.region_override_desc', { default: 'Auto uses your configured country. Manual override always wins.' })}
                    layout="stacked"
                >
                    <SettingsSelect
                        id="bird-model-region-override"
                        value={birdModelRegionOverride}
                        ariaLabel={$_('settings.detection.region_override_title', { default: 'Bird model region' })}
                        options={BIRD_MODEL_REGION_OVERRIDE_VALUES.map((option) => ({
                            value: option,
                            label: option === 'auto'
                                ? $_('settings.detection.region_override_auto', { default: 'Auto' })
                                : option === 'eu'
                                    ? $_('settings.detection.region_override_eu', { default: 'Europe' })
                                    : $_('settings.detection.region_override_na', { default: 'North America' })
                        }))}
                        onchange={(v) => (birdModelRegionOverride = v as BirdModelRegionOverride)}
                    />
                </SettingsRow>

        </div>
        <div class="scroll-mt-24">
            <ModelManager
                executionMode={imageExecutionMode}
                autoVideoEnabled={autoVideoClassification}
                bind:birdFinder
                bind:birdFinderProvider
                {classifierStatus}
                deviceCheckRunning={deviceCheck.running}
                onruntimechange={onrefreshclassifierstatus}
                oncheckfinderdevices={checkFinderDevices}
                bind:firstLoadSettled={modelsListed}
                {onopenlocationsettings}
            />
        </div>
        {#if onopenmodelevaluation && modelsListed}
            <SettingsRow
                labelId="setting-model-evaluation"
                label={$_('settings.models.evaluation_row', { default: 'Compare the installed models' })}
                description={$_('settings.models.evaluation_row_desc', { default: 'Model evaluation runs each installed model on reference photos of known species from iNaturalist and Wikimedia Commons, and shows how often it is right and how long it takes.' })}
            >
                <a
                    href="/diagnostics/model-eval"
                    class="btn btn-secondary min-h-11 max-w-full px-4 whitespace-normal"
                    onclick={(event) => { event.preventDefault(); onopenmodelevaluation?.(); }}
                >
                    {$_('settings.models.testing_open', { default: 'Open model evaluation' })}
                </a>
            </SettingsRow>
        {/if}
    </SettingsCard>
</div>
