<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { VersionInfo } from '../../api';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    // What leaves this installation, and only when switched on. It lives with Data, beside the
    // other choices about what is kept and sent, not with the connection to Frigate.
    let {
        telemetryEnabled = $bindable(false),
        telemetryHealthEnabled = $bindable(false),
        telemetryInstallationId,
        telemetryPlatform,
        telemetryPayloadPreview,
        versionInfo
    }: {
        telemetryEnabled: boolean;
        telemetryHealthEnabled: boolean;
        telemetryInstallationId: string | undefined;
        telemetryPlatform: string | undefined;
        telemetryPayloadPreview: Record<string, unknown> | undefined;
        versionInfo: VersionInfo;
    } = $props();

    function nestedValue(source: Record<string, unknown> | undefined, path: string): unknown {
        return path.split('.').reduce<unknown>((current, key) => {
            if (!current || typeof current !== 'object') return undefined;
            return (current as Record<string, unknown>)[key];
        }, source);
    }

    function formatTelemetryValue(value: unknown): string {
        if (typeof value === 'boolean') return value ? $_('common.yes', { default: 'Yes' }) : $_('common.no', { default: 'No' });
        if (value === null || value === undefined || value === '') return '...';
        return String(value);
    }

    const telemetryRuntimeRows = $derived([
        ['settings.telemetry.payload_model_runtime', 'runtime.model_runtime'],
        ['settings.telemetry.payload_provider_configured', 'runtime.inference_provider_configured'],
        ['settings.telemetry.payload_provider_active', 'runtime.inference_provider_active'],
        ['settings.telemetry.payload_backend_active', 'runtime.inference_backend_active'],
        ['settings.telemetry.payload_execution_mode', 'runtime.image_execution_mode'],
        ['settings.telemetry.payload_crop_tier', 'runtime.bird_crop_detector_tier'],
        ['settings.telemetry.payload_cuda_available', 'hardware.cuda_available'],
        ['settings.telemetry.payload_nvidia_gpu_detected', 'hardware.nvidia_gpu_detected'],
        ['settings.telemetry.payload_openvino_available', 'hardware.openvino_available'],
        ['settings.telemetry.payload_intel_gpu_available', 'hardware.intel_gpu_available'],
        ['settings.telemetry.payload_intel_npu_available', 'hardware.intel_npu_available'],
        ['settings.telemetry.payload_openvino_compile', 'hardware.openvino_gpu_compile_ok'],
        ['settings.telemetry.payload_openvino_device', 'hardware.openvino_gpu_compile_device'],
        ['settings.telemetry.payload_gpu_fallback', 'hardware.openvino_gpu_fallback_active'],
        ['settings.telemetry.payload_deployment_mode', 'deployment.mode'],
        ['settings.telemetry.payload_image_flavor', 'deployment.image_flavor'],
        ['settings.telemetry.payload_image_arch', 'deployment.image_arch']
    ]);
</script>

<SettingsCard title={$_('settings.telemetry.title')} description={$_('settings.telemetry.desc')}>
    <SettingsRow
        labelId="setting-telemetry"
        label={$_('settings.telemetry.title')}
        description={$_('settings.telemetry.appreciation_tooltip')}
    >
        <SettingsToggle
            checked={telemetryEnabled}
            labelledBy="setting-telemetry"
            srLabel={$_('settings.telemetry.title')}
            onchange={(v) => (telemetryEnabled = v)}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-telemetry-health"
        label={$_('settings.telemetry.health_title')}
        description={$_('settings.telemetry.health_desc')}
    >
        <SettingsToggle
            checked={telemetryHealthEnabled}
            labelledBy="setting-telemetry-health"
            srLabel={$_('settings.telemetry.health_title')}
            onchange={(v) => (telemetryHealthEnabled = v)}
        />
    </SettingsRow>

    {#if telemetryEnabled || telemetryHealthEnabled}
        <div class="border-t border-line-soft pt-4 animate-in fade-in slide-in-from-top-2">
            <p class="text-sm font-semibold text-slate-700 mb-3 dark:text-slate-200">{$_('settings.telemetry.transparency')}</p>
            <div class="space-y-2 text-xs font-mono text-slate-600 dark:text-slate-400">
                <div class="flex justify-between"><span>{$_('settings.telemetry.install_id')}:</span><span class="text-slate-900 dark:text-white select-all">{telemetryInstallationId || '...'}</span></div>
                <div class="flex justify-between"><span>{$_('settings.telemetry.version')}:</span><span>{versionInfo.version}</span></div>
                <div class="flex justify-between"><span>{$_('settings.telemetry.platform')}:</span><span>{telemetryPlatform || '...'}</span></div>
                {#if telemetryEnabled}
                    <div class="flex justify-between"><span>{$_('settings.telemetry.includes')}:</span><span>{$_('settings.telemetry.includes_value')}</span></div>
                {/if}
                {#if telemetryHealthEnabled}
                    <div class="flex justify-between"><span>{$_('settings.telemetry.health_includes')}:</span><span>{$_('settings.telemetry.health_includes_value')}</span></div>
                {/if}
                <div class="flex justify-between"><span>{$_('settings.telemetry.geography')}:</span><span>{$_('settings.telemetry.geography_value')}</span></div>
                <div class="flex justify-between"><span>{$_('settings.telemetry.frequency')}:</span><span>{$_('settings.telemetry.frequency_value')}</span></div>
            </div>
            {#if telemetryEnabled}
                <div class="mt-4 pt-4 border-t border-slate-200/70 dark:border-slate-700/70">
                    <p class="text-sm font-semibold text-slate-700 mb-2 dark:text-slate-200">{$_('settings.telemetry.runtime_snapshot')}</p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-xs font-mono text-slate-600 dark:text-slate-400">
                        {#each telemetryRuntimeRows as [labelKey, valuePath]}
                            <div class="flex justify-between gap-3 min-w-0">
                                <span class="truncate">{$_(labelKey)}:</span>
                                <span class="text-right text-slate-900 dark:text-white break-all">{formatTelemetryValue(nestedValue(telemetryPayloadPreview, valuePath))}</span>
                            </div>
                        {/each}
                    </div>
                </div>
            {/if}
            <p class="text-xs text-slate-600 mt-3 italic">{$_('settings.telemetry.privacy_notice')}</p>
            <a
                href="https://yawamf-telemetry.ya-wamf.workers.dev/dashboard"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-1 mt-3 text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline"
            >
                {$_('settings.telemetry.dashboard_link', { default: 'View the public telemetry dashboard' })} →
            </a>
        </div>
    {/if}
</SettingsCard>
