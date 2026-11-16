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
        /** What stops the first automatic check, from Garden's setup state; null when nothing does. */
        blockedBy?: 'model' | 'camera' | null;
    }

    let { service, blockedBy = null }: Props = $props();

    const savedEnabled = $derived(settingsStore.settings?.beta_garden_animals === true);
    const identification = $derived(service.identification);
    const motion = $derived(service.motion);
    const facts = $derived(gardenCollectionFacts(identification, motion));
    const listLocale = $derived($locale ?? 'en');

    function deviceSentence(fact: GardenDeviceFact): string | null {
        if (fact.kind === 'not_used') return null;
        const device = EXECUTION_DEVICE_LABEL[fact.provider];
        if (fact.kind === 'preferred_used') return $_('settings.beta.garden_sentence_device_checked', { default: 'Automatic checks run on {device}, which matched the CPU before its first use.', values: { device } });
        if (fact.kind === 'preferred_unused') return $_('settings.beta.garden_sentence_device_unused', { default: 'Automatic checks will try {device} first. It has not run a check yet.', values: { device } });
        return $_('settings.beta.garden_sentence_device_ran', { default: 'Automatic checks ran on {device}.', values: { device } });
    }

    function lastCheckSentence(): string {
        const check = facts.lastCheck;
        if (check) {
            const values = { device: EXECUTION_DEVICE_LABEL[check.provider], time: formatDateTime(check.checkedAt) };
            return check.fallback
                ? $_('settings.beta.garden_sentence_last_check_fallback', { default: 'Last check {time} on {device}, because the preferred device failed.', values })
                : $_('settings.beta.garden_sentence_last_check', { default: 'Last check {time} on {device}.', values });
        }
        if (blockedBy === 'model') return $_('settings.beta.garden_sentence_blocked_model', { default: 'No check yet: the Garden model is not downloaded.' });
        if (blockedBy === 'camera') return $_('settings.beta.garden_sentence_blocked_camera', { default: 'No check yet: no camera watches for Garden animals.' });
        return $_('settings.beta.garden_sentence_no_check', { default: 'No check has run yet.' });
    }

    const motionSentence = $derived(
        facts.motionCameras === null
            ? $_('settings.beta.garden_sentence_motion_unread', { default: 'Motion photo status could not be read. Refresh to try again.' })
            : facts.motionCameras.length > 0
                ? $_('settings.beta.garden_sentence_motion_on', { default: 'Motion photos are collected on {cameras}.', values: { cameras: formatCameraList(facts.motionCameras, listLocale) } })
                : $_('settings.beta.garden_sentence_motion_off', { default: 'Motion photos are off.' })
    );
</script>

{#if savedEnabled}
    {#if service.loading && !identification && !motion}
        <p class="text-xs text-slate-600 dark:text-slate-400" role="status">{$_('settings.beta.garden_status_loading', { default: 'Checking Garden status…' })}</p>
    {:else}
        <div class="border-t border-line-soft pt-4 space-y-2 text-slate-700 dark:text-slate-300" role="group" aria-labelledby="garden-collection-status" data-garden-collection-status>
            <h4 id="garden-collection-status" class="text-sm font-medium text-slate-900 dark:text-white">{$_('settings.beta.garden_status_title', { default: 'Collection status' })}</h4>
            <div class="space-y-1 text-sm leading-relaxed">
                {#if identification}
                    {@const device = deviceSentence(facts.device)}
                    <p class="wrap-break-word" data-garden-fact="last_check">{lastCheckSentence()}</p>
                    {#if device}
                        <p class="wrap-break-word" data-garden-fact="device">{device}</p>
                    {/if}
                    {#if identification.automatic_message && !blockedBy}
                        <!-- The service words this itself and reports no count, so it is shown as sent. -->
                        <p class="wrap-break-word" data-garden-fact="automatic" data-garden-automatic-status>{identification.automatic_message}</p>
                    {/if}
                {/if}
                <p class="wrap-break-word" data-garden-fact="motion">{motionSentence}</p>
                {#if identification?.saved_crops}
                    <p class="wrap-break-word" data-garden-crop-storage>{$_('settings.beta.garden_sentence_saved_crops', { default: '{count, plural, one {# crop} other {# crops}} saved of {limit, number} allowed.', values: { count: identification.saved_crops.count, limit: identification.saved_crops.limit } })}</p>
                {/if}
            </div>
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
