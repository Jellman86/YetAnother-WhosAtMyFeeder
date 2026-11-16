<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import type { components } from '../../api/generated/openapi';
    import ModelExecutionEvidence from '../../components/ModelExecutionEvidence.svelte';
    import SettingsRow from '../../components/settings/_primitives/SettingsRow.svelte';
    import SettingsSelect from '../../components/settings/_primitives/SettingsSelect.svelte';
    import { finderDeviceOptions, finderNeedsAttention, finderRunsOn, type BirdFinderProvider, type FinderDeviceCheck } from '../../settings/bird-finder';
    import { formatDate } from '../../utils/datetime';

    interface Props {
        modelId: string;
        /** The finder's own short name, e.g. "RF-DETR Nano". */
        shortName: string;
        installed: boolean;
        /** The finder's current passing checks on this host, fastest first. */
        evidence: readonly string[];
        /** Graphics and NPU devices this host offers the finder. */
        accelerators: readonly string[];
        hostProviders: readonly string[];
        check: FinderDeviceCheck | null | undefined;
        /** The device the running finder was saved with; the select below holds the staged one. */
        savedProvider: string;
        /** The chosen finder is the saved one, so its saved device can be kept as it is. */
        finderSaved: boolean;
        provider: BirdFinderProvider;
        checkRunning: boolean;
        downloading: boolean;
        execution: components['schemas']['InferenceExecution'] | null | undefined;
        /** The backend's device for the running finder's next frame. */
        planned: { model_id?: string | null; provider?: string | null } | null;
        oncheck?: () => void;
        ondownload: () => void;
    }

    let {
        modelId,
        shortName,
        installed,
        evidence,
        accelerators,
        hostProviders,
        check,
        savedProvider,
        finderSaved,
        provider = $bindable<BirdFinderProvider>('auto'),
        checkRunning,
        downloading,
        execution,
        planned,
        oncheck,
        ondownload
    }: Props = $props();

    // Short names: this card says "Intel NPU" in a sentence, where the long form would repeat "(OpenVINO)".
    function deviceName(device: string): string {
        switch (device) {
            case 'cpu':
                return $_('settings.detection.model_manager_provider_cpu', { default: 'CPU' });
            case 'intel_cpu':
                return $_('settings.detection.model_manager_provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' });
            case 'intel_gpu':
                return $_('settings.detection.intel_gpu_status', { default: 'Intel GPU' });
            case 'intel_npu':
                return $_('settings.detection.intel_npu_status', { default: 'Intel NPU' });
            case 'cuda':
                return $_('settings.detection.model_manager_provider_cuda', { default: 'NVIDIA CUDA' });
            default:
                return device;
        }
    }

    function deviceNames(devices: readonly string[]): string {
        const names = devices.map(deviceName);
        try {
            return new Intl.ListFormat($locale ?? 'en', { style: 'long', type: 'conjunction' }).format(names);
        } catch {
            return names.join(', ');
        }
    }

    const runsOn = $derived(finderRunsOn({ installed, evidence, accelerators, savedProvider, check, modelId, checkRunning, execution, planned }));

    // The measured fact, in words. Every sentence names the device first, so the row reads the same way in each state.
    const runsOnText = $derived.by((): string => {
        switch (runsOn.kind) {
            case 'not_downloaded':
                return $_('settings.detection.bird_finder_runs_not_downloaded', { default: 'Nowhere yet · this finder is not downloaded' });
            case 'checking':
                return runsOn.devices.length > 0
                    ? $_('settings.detection.bird_finder_runs_checking', { default: 'Checking {devices}…', values: { devices: deviceNames(runsOn.devices) } })
                    : $_('settings.detection.bird_finder_checking_devices', { default: 'Checking…' });
            case 'active':
                return $_('settings.detection.bird_finder_runs_active', { default: '{provider} · last confirmed use on {date}', values: { provider: deviceName(runsOn.provider), date: formatDate(runsOn.checkedAt) } });
            case 'passed':
                return runsOn.checkedAt
                    ? $_('settings.detection.bird_finder_runs_passed_dated', { default: '{provider} · passed its device check on {date}', values: { provider: deviceName(runsOn.provider), date: formatDate(runsOn.checkedAt) } })
                    : $_('settings.detection.bird_finder_runs_passed', { default: '{provider} · passed its device check on this host', values: { provider: deviceName(runsOn.provider) } });
            case 'cpu_chosen':
                return $_('settings.detection.bird_finder_runs_cpu_chosen', { default: 'CPU · the saved device' });
            case 'failed': {
                const devices = deviceNames(runsOn.devices);
                const fact = runsOn.checkedAt
                    ? $_('settings.detection.bird_finder_runs_failed_dated', { default: 'CPU · {devices} failed the device check on {date}', values: { devices, date: formatDate(runsOn.checkedAt) } })
                    : $_('settings.detection.bird_finder_runs_failed', { default: 'CPU · {devices} failed the device check', values: { devices } });
                if (runsOn.cause === 'mismatch') {
                    return $_('settings.detection.bird_finder_runs_cause_mismatch', { default: "{fact} (the boxes did not match the CPU's)", values: { fact } });
                }
                if (runsOn.cause === 'unfinished') {
                    return $_('settings.detection.bird_finder_runs_cause_unfinished', { default: '{fact} (the check could not finish)', values: { fact } });
                }
                return fact;
            }
            case 'interrupted':
                return $_('settings.detection.bird_finder_runs_interrupted', { default: 'CPU · the last check of {devices} was interrupted', values: { devices: deviceNames(runsOn.devices) } });
            case 'waiting':
                return $_('settings.detection.bird_finder_runs_waiting', { default: 'CPU · waiting for saved bird photos to check {devices}', values: { devices: deviceNames(runsOn.devices) } });
            case 'waiting_full_frames':
                return $_('settings.detection.bird_finder_runs_waiting_full_frames', { default: 'CPU · waiting for full camera frames to check {devices}. The saved bird photos are close crops, and a finder cannot be checked on those.', values: { devices: deviceNames(runsOn.devices) } });
            case 'never_checked':
                return $_('settings.detection.bird_finder_runs_never', { default: 'CPU · no accelerator has passed a check on this host yet' });
            case 'cpu_only':
                return $_('settings.detection.bird_finder_runs_cpu_only', { default: 'CPU · this host offers the finder no accelerator' });
        }
    });
    // A fallback the owner did not choose is work for a person; the words say so, the colour only agrees.
    const needsAttention = $derived(finderNeedsAttention(runsOn, accelerators, savedProvider));

    // The server keeps an unchanged saved device and refuses a newly chosen one that has not passed.
    const keepable = $derived(finderSaved ? savedProvider : null);
    const deviceOptions = $derived([
        { value: 'auto', label: modelId === 'bird_crop_detector_accurate_rfdetr_nano'
            ? $_('settings.detection.bird_finder_device_auto_rfdetr', { default: 'Automatic (NPU, then GPU, then CPU)' })
            : $_('settings.detection.bird_finder_device_auto', { default: 'Automatic (fastest device that passed)' }) },
        { value: 'cpu', label: deviceName('cpu') },
        ...finderDeviceOptions({ evidence, accelerators, hostProviders, chosen: provider, keepable }).map((option) => ({
            value: option.value,
            disabled: !option.selectable,
            label: option.passed
                ? deviceName(option.value)
                : $_('settings.detection.bird_finder_device_not_passed', { default: '{provider} · not passed on this host', values: { provider: deviceName(option.value) } })
        }))
    ] satisfies Array<{ value: string; label: string; disabled?: boolean }>);
    const chosenUnpassed = $derived(installed && provider !== 'auto' && provider !== 'cpu' && !evidence.includes(provider));
    const lastRun = $derived(execution?.model_id === modelId ? execution : null);
</script>

<div class="settings-subrows" data-finder-device-panel>
    <SettingsRow labelId="bird-finder-runs-on-label" label={$_('settings.detection.bird_finder_runs_on', { default: 'Runs on' })}>
        <div class="space-y-1" role="status" aria-labelledby="bird-finder-runs-on-label" data-finder-runs-on={runsOn.kind}>
            <p class="flex items-start gap-2 text-sm leading-snug {needsAttention ? 'text-attention-800 dark:text-attention-300' : 'text-slate-900 dark:text-white'}">
                {#if needsAttention}
                    <span class="mt-1.5 h-2 w-2 shrink-0 rotate-45 bg-attention-600 dark:bg-attention-400" aria-hidden="true"></span>
                {/if}
                <span class="min-w-0 wrap-break-word">{runsOnText}</span>
            </p>
            {#if lastRun}
                <ModelExecutionEvidence execution={lastRun} />
            {/if}
        </div>
    </SettingsRow>

    <SettingsRow labelId="bird-finder-device-label" label={$_('settings.detection.bird_finder_device', { default: 'Device' })}>
        <div class="space-y-2">
            <SettingsSelect
                id="bird-finder-device"
                value={provider}
                options={deviceOptions}
                ariaLabel={$_('settings.detection.bird_finder_device', { default: 'Device' })}
                ariaDescribedBy={chosenUnpassed ? 'bird-finder-device-note' : undefined}
                onchange={(next) => (provider = next as BirdFinderProvider)}
            />
            {#if chosenUnpassed}
                <p id="bird-finder-device-note" class="text-sm leading-snug text-slate-600 dark:text-slate-400" role="status" data-finder-device-note>
                    {provider === keepable
                        ? modelId === 'bird_crop_detector_accurate_rfdetr_nano'
                        ? $_('settings.detection.bird_finder_device_unpassed_saved_recovery', { default: 'Saved: {provider}. See Runs on above for the device currently used, or Check devices.', values: { provider: deviceName(provider) } })
                        : $_('settings.detection.bird_finder_device_unpassed_saved', { default: 'Saved: {provider}. It runs on CPU until {provider} passes a check. Check devices, or choose Automatic.', values: { provider: deviceName(provider) } })
                        : $_('settings.detection.bird_finder_device_unpassed_chosen', { default: '{provider} has not passed a check for this finder on this host, so it cannot be saved yet. Check devices, or choose Automatic.', values: { provider: deviceName(provider) } })}
                </p>
            {/if}
        </div>
    </SettingsRow>

    <div class="space-y-2" data-finder-actions>
        {#if !installed}
            <button type="button" onclick={ondownload} disabled={downloading} class="btn btn-secondary min-h-11 px-4">
                {$_('settings.detection.bird_finder_download', { default: 'Download {name}', values: { name: shortName } })}
            </button>
        {:else if oncheck}
            <button type="button" onclick={oncheck} disabled={runsOn.kind === 'checking'} aria-describedby="bird-finder-check-hint" class="btn btn-secondary min-h-11 px-4">
                {runsOn.kind === 'checking'
                    ? $_('settings.detection.bird_finder_checking_devices', { default: 'Checking…' })
                    : $_('settings.detection.bird_finder_check_devices', { default: 'Check devices for the bird finder' })}
            </button>
            <p id="bird-finder-check-hint" class="max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">
                {modelId === 'bird_crop_detector_accurate_rfdetr_nano'
                    ? $_('settings.detection.bird_finder_check_devices_hint_rfdetr', { default: 'Compares the finder on each device with the CPU on your saved bird photos, then prefers a passing NPU, followed by GPU, before CPU. The identification model is not changed.' })
                    : $_('settings.detection.bird_finder_check_devices_hint', { default: 'Compares the finder on each device with the CPU on your saved bird photos, then uses the fastest that matches. The identification model is not changed.' })}
            </p>
        {/if}
    </div>

    <!-- The two quiet disclosures share one row, so repair and background never outweigh the main flow. -->
    <div class="space-y-1" data-finder-more>
        {#if installed}
            <details class="group" data-finder-repair>
                <summary class="focus-ring inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-md text-sm font-medium text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200">
                    <span>{$_('settings.detection.bird_finder_repair', { default: 'Repair' })}</span>
                    <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" />
                    </svg>
                </summary>
                <div class="mt-2 space-y-2">
                    <p class="max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">
                        {$_('settings.detection.bird_finder_repair_desc', { default: "Download the finder's files again if they are missing or damaged." })}
                    </p>
                    <button type="button" onclick={ondownload} disabled={downloading} class="btn btn-ghost min-h-11 px-4">
                        {$_('settings.detection.bird_finder_redownload', { default: 'Re-download {name}', values: { name: shortName } })}
                    </button>
                </div>
            </details>
        {/if}
        <details class="group" data-finder-how>
            <summary class="focus-ring inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-md text-sm font-medium text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200">
                <span>{$_('settings.detection.bird_finder_how_title', { default: 'How the finder works' })}</span>
                <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="m6 9 6 6 6-6" />
                </svg>
            </summary>
            <div class="mt-2 max-w-prose space-y-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                <p>{$_('settings.detection.bird_finder_backup', { default: 'If it cannot find a usable bird, YA-WAMF also tries the fast fallback finder and Frigate\'s tracking box, and uses the full frame only when none of them gives a reliable crop.' })}</p>
                <p>{$_('settings.detection.bird_finder_how_save', { default: 'A change of finder or device takes effect when you save. If the device becomes unavailable, a verified recovery device or CPU is used. The fast fallback finder picks its device automatically.' })}</p>
            </div>
        </details>
    </div>
</div>
