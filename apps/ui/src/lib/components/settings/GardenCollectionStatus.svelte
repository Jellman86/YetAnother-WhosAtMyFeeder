<script lang="ts">
    /**
     * What Garden is doing now, as measured by the service: the device its last check ran on, the
     * automatic check queue and the motion collector. Nothing here is a setting, and nothing is
     * shown before Apply has switched Garden on, because only then can the service be asked.
     */
    import { _ } from 'svelte-i18n';
    import ModelExecutionEvidence from '../ModelExecutionEvidence.svelte';
    import { settingsStore } from '../../stores/settings.svelte';
    import { EXECUTION_DEVICE_LABEL } from '../../utils/beta-features';
    import type { GardenServiceStatus } from './garden-service-status.svelte';

    interface Props {
        service: GardenServiceStatus;
    }

    let { service }: Props = $props();

    const savedEnabled = $derived(settingsStore.settings?.beta_garden_animals === true);
    const identification = $derived(service.identification);
    const motion = $derived(service.motion);
</script>

{#if savedEnabled}
    {#if service.loading && !identification && !motion}
        <p class="text-xs text-slate-600 dark:text-slate-400" role="status">{$_('settings.beta.garden_status_loading', { default: 'Checking Garden status…' })}</p>
    {:else}
        <!-- What Garden is doing now, as measured by the service; nothing here is a setting. -->
        <div class="space-y-1 rounded-xl bg-surface-raised/70 p-3 text-slate-700 dark:text-slate-300" role="group" aria-labelledby="garden-collection-status" data-garden-collection-status>
            <h6 id="garden-collection-status" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_status_title', { default: 'Collection status' })}</h6>
            {#if identification}
                {#if identification.preferred_provider}<p class="text-xs">{$_('model_execution.garden_preference', { default: 'Automatic check device preference: {device}. A new accelerator must agree with CPU first.', values: { device: EXECUTION_DEVICE_LABEL[identification.preferred_provider] } })}</p>{/if}
                <ModelExecutionEvidence execution={identification.last_execution} />
                {#if identification.saved_crops}
                    <p class="text-xs" data-garden-crop-storage>{$_('garden.saved_crop_count', { default: 'Saved animal crops: {count} / {limit}. Full photos keep their separate expiry.', values: { count: identification.saved_crops.count, limit: identification.saved_crops.limit } })}</p>
                {/if}
            {/if}
            {#if identification?.automatic_message}<p class="text-xs" data-garden-automatic-status>{identification.automatic_message}</p>{/if}
            {#if !motion}
                <p class="text-xs" role="status">{$_('garden.model_status_unavailable', { default: 'Model status unavailable. Refresh to try again.' })}</p>
            {:else}
                <p class="text-xs" role="status" data-garden-motion-status>{motion.message}</p>
                {#if motion.interval_seconds !== undefined && motion.photo_limit !== undefined && motion.photo_retention_days !== undefined}
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_limits_scoped', { default: 'Motion detector only: CPU · At least {seconds}s between scans · Up to {limit} photos · {days}-day photo retention', values: { seconds: motion.interval_seconds, limit: motion.photo_limit, days: motion.photo_retention_days } })}</p>
                {/if}
                {#if motion.queue_limit !== undefined && motion.catchup_seconds !== undefined}
                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_coverage', { default: 'Up to {limit} short windows queued per camera from the last {minutes} minutes. Birds and camera pressure pause collection; brief visits can be missed.', values: { limit: motion.queue_limit, minutes: motion.catchup_seconds / 60 } })}</p>
                {/if}
                {#if motion.queue_camera && motion.queue_checked_at}
                    <p class="break-words text-xs">{$_('garden.motion_queue', { default: '{camera}: {count, plural, one {# window waiting} other {# windows waiting}} when checked at {time}. More may be available at the queue limit.', values: { camera: motion.queue_camera, count: motion.queued_windows ?? 0, time: new Date(motion.queue_checked_at).toLocaleString() } })}</p>
                {/if}
                {#each motion.unreadable_recordings ?? [] as skipped (skipped.camera)}
                    <p class="break-words text-xs" data-garden-motion-unreadable={skipped.camera}>{$_('garden.motion_unreadable', { default: '{count, plural, one {# recording} other {# recordings}} could not be read on {camera} in the last hour and {count, plural, one {was} other {were}} skipped. No photo was kept.', values: { count: skipped.count, camera: skipped.camera } })}</p>
                {/each}
                {#if motion.last_scan_at}<p class="text-xs">{$_('garden.motion_last_scan', { default: 'Last scan: {time}', values: { time: new Date(motion.last_scan_at).toLocaleString() } })}</p>{/if}
            {/if}
        </div>
    {/if}
{/if}
