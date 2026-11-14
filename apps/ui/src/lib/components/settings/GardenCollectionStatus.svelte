<script lang="ts">
    /**
     * What Garden is doing now, as a short list of facts in the owner's words: the device it
     * prefers and whether a check has run on it, the last check, the latest automatic check
     * message, motion photos and saved crops. Every fact is what the service reported; nothing is
     * shown before Apply has switched Garden on, because only then can the service be asked.
     */
    import { _, locale } from 'svelte-i18n';
    import { settingsStore } from '../../stores/settings.svelte';
    import { EXECUTION_DEVICE_LABEL, gardenCollectionFacts, type GardenDeviceFact } from '../../utils/beta-features';
    import { formatCameraList } from '../../utils/camera-watch';
    import { formatDateTime } from '../../utils/datetime';
    import type { GardenServiceStatus } from './garden-service-status.svelte';

    interface Props {
        service: GardenServiceStatus;
    }

    let { service }: Props = $props();

    const savedEnabled = $derived(settingsStore.settings?.beta_garden_animals === true);
    const identification = $derived(service.identification);
    const motion = $derived(service.motion);
    const facts = $derived(gardenCollectionFacts(identification, motion));
    const listLocale = $derived($locale ?? 'en');

    function deviceText(fact: GardenDeviceFact): string {
        if (fact.kind === 'not_used') return $_('settings.beta.garden_fact_not_used', { default: 'Not used yet' });
        const device = EXECUTION_DEVICE_LABEL[fact.provider];
        if (fact.kind === 'preferred_used') return $_('settings.beta.garden_fact_device_checked', { default: '{device} (checked against CPU before first use)', values: { device } });
        if (fact.kind === 'preferred_unused') return $_('settings.beta.garden_fact_device_unused', { default: '{device} preferred, not used yet', values: { device } });
        return device;
    }

    function lastCheckText(check: NonNullable<typeof facts.lastCheck>): string {
        const values = { device: EXECUTION_DEVICE_LABEL[check.provider], time: formatDateTime(check.checkedAt) };
        return check.fallback
            ? $_('settings.beta.garden_fact_last_check_fallback', { default: '{device} · {time} (the preferred device failed, so CPU was used)', values })
            : $_('settings.beta.garden_fact_last_check_value', { default: '{device} · {time}', values });
    }
</script>

{#if savedEnabled}
    {#if service.loading && !identification && !motion}
        <p class="text-xs text-slate-600 dark:text-slate-400" role="status">{$_('settings.beta.garden_status_loading', { default: 'Checking Garden status…' })}</p>
    {:else}
        <div class="border-t border-line-soft pt-4 space-y-2 text-slate-700 dark:text-slate-300" role="group" aria-labelledby="garden-collection-status" data-garden-collection-status>
            <h6 id="garden-collection-status" class="text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_status_title', { default: 'Collection status' })}</h6>
            <dl class="space-y-1 text-xs">
                {#if identification}
                    <div class="flex flex-wrap gap-x-2" data-garden-fact="device">
                        <dt class="font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_fact_device', { default: 'Device' })}</dt>
                        <dd class="min-w-0 wrap-break-word">{deviceText(facts.device)}</dd>
                    </div>
                    <div class="flex flex-wrap gap-x-2" data-garden-fact="last_check">
                        <dt class="font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_fact_last_check', { default: 'Last check' })}</dt>
                        <dd class="min-w-0 wrap-break-word">{facts.lastCheck ? lastCheckText(facts.lastCheck) : $_('settings.beta.garden_fact_none_yet', { default: 'None yet' })}</dd>
                    </div>
                    {#if identification.automatic_message}
                        <!-- The service words this itself and reports no count, so it is shown as sent. -->
                        <div class="flex flex-wrap gap-x-2" data-garden-fact="automatic">
                            <dt class="font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_fact_checks', { default: 'Automatic checks' })}</dt>
                            <dd class="min-w-0 wrap-break-word" data-garden-automatic-status>{identification.automatic_message}</dd>
                        </div>
                    {/if}
                {/if}
                <div class="flex flex-wrap gap-x-2" data-garden-fact="motion">
                    <dt class="font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_fact_motion', { default: 'Motion photos' })}</dt>
                    <dd class="min-w-0 wrap-break-word">
                        {facts.motionCameras === null
                            ? $_('settings.beta.garden_fact_unreadable', { default: 'Could not be read. Refresh to try again.' })
                            : facts.motionCameras.length > 0
                                ? $_('settings.beta.garden_fact_motion_on', { default: 'On for {cameras}', values: { cameras: formatCameraList(facts.motionCameras, listLocale) } })
                                : $_('settings.beta.status_off', { default: 'Off' })}
                    </dd>
                </div>
                {#if identification?.saved_crops}
                    <div class="flex flex-wrap gap-x-2" data-garden-crop-storage>
                        <dt class="font-semibold text-slate-900 dark:text-white">{$_('settings.beta.garden_fact_saved_crops', { default: 'Saved crops' })}</dt>
                        <dd class="min-w-0 wrap-break-word">{$_('settings.beta.garden_fact_saved_crops_value', { default: '{count, plural, one {# crop} other {# crops}} of {limit, number}', values: { count: identification.saved_crops.count, limit: identification.saved_crops.limit } })}</dd>
                    </div>
                {/if}
            </dl>
            {#if motion && motion.cameras.length > 0}
                <div class="space-y-1 border-t border-line-soft pt-2 text-xs text-slate-600 dark:text-slate-400">
                    <p class="text-slate-700 dark:text-slate-300" role="status" data-garden-motion-status>{motion.message}</p>
                    {#if motion.interval_seconds !== undefined && motion.photo_limit !== undefined && motion.photo_retention_days !== undefined}
                        <p>{$_('garden.motion_limits_scoped', { default: 'Motion detector only: CPU · At least {seconds}s between scans · Up to {limit} photos · {days}-day photo retention', values: { seconds: motion.interval_seconds, limit: motion.photo_limit, days: motion.photo_retention_days } })}</p>
                    {/if}
                    {#if motion.queue_limit !== undefined && motion.catchup_seconds !== undefined}
                        <p>{$_('garden.motion_coverage', { default: 'Up to {limit} short windows queued per camera from the last {minutes} minutes. Birds and camera pressure pause collection; brief visits can be missed.', values: { limit: motion.queue_limit, minutes: motion.catchup_seconds / 60 } })}</p>
                    {/if}
                    {#if motion.queue_camera && motion.queue_checked_at}
                        <p class="wrap-break-word">{$_('garden.motion_queue', { default: '{camera}: {count, plural, one {# window waiting} other {# windows waiting}} when checked at {time}. More may be available at the queue limit.', values: { camera: motion.queue_camera, count: motion.queued_windows ?? 0, time: formatDateTime(motion.queue_checked_at) } })}</p>
                    {/if}
                    {#each motion.unreadable_recordings ?? [] as skipped (skipped.camera)}
                        <p class="wrap-break-word" data-garden-motion-unreadable={skipped.camera}>{$_('garden.motion_unreadable', { default: '{count, plural, one {# recording} other {# recordings}} could not be read on {camera} in the last hour and {count, plural, one {was} other {were}} skipped. No photo was kept.', values: { count: skipped.count, camera: skipped.camera } })}</p>
                    {/each}
                    {#if motion.last_scan_at}<p>{$_('garden.motion_last_scan', { default: 'Last scan: {time}', values: { time: formatDateTime(motion.last_scan_at) } })}</p>{/if}
                </div>
            {/if}
        </div>
    {/if}
{/if}
