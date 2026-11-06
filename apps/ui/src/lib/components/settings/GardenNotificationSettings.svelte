<script lang="ts">
    /**
     * Garden alerts, set up with the channels they use. By default they follow the bird channels
     * switched on above; an explicit choice uses saved credentials while the bird switch stays off.
     * Bird filters, mode and cooldown are bird rules and do not apply here.
     */
    import { _, locale } from 'svelte-i18n';
    import { fetchGardenNotifications, type GardenNotificationChannel, type GardenNotificationStatus } from '../../api/garden';
    import { gardenChannelsMissingCredentials, gardenDeliveryChannels } from '../../settings/garden-notifications';
    import { formatChannelList, type PolicyChannel } from '../../settings/notification-policy';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    interface Props {
        enabled?: boolean;
        useBirdChannels?: boolean;
        channels?: GardenNotificationChannel[];
        includePhoto?: boolean;
        /** The bird channels as the page holds them now, saved or not. */
        birdChannels: PolicyChannel[];
        /** Whether the saved settings have Garden on, so its delivery status can be read. */
        statusAvailable: boolean;
    }

    let {
        enabled = $bindable(false),
        useBirdChannels = $bindable(true),
        channels = $bindable<GardenNotificationChannel[]>([]),
        includePhoto = $bindable(true),
        birdChannels,
        statusAvailable
    }: Props = $props();

    let status = $state.raw<GardenNotificationStatus | null>(null);
    let loading = $state(false);
    let error = $state<string | null>(null);

    const delivery = $derived(gardenDeliveryChannels(useBirdChannels, channels, birdChannels));
    const missingCredentials = $derived(useBirdChannels ? [] : gardenChannelsMissingCredentials(channels, birdChannels));
    const labelFor = (id: GardenNotificationChannel): string => birdChannels.find((channel) => channel.id === id)?.label ?? id;
    const deliveryNames = $derived(formatChannelList(delivery.map(labelFor), $locale ?? 'en'));
    const missingNames = $derived(formatChannelList(missingCredentials.map(labelFor), $locale ?? 'en'));
    const modes = $derived([
        {
            value: true,
            label: $_('settings.notifications.garden.use_bird', { default: 'Use my bird channels' }),
            help: $_('settings.notifications.garden.use_bird_help', { default: 'The channels above that are switched on and configured.' })
        },
        {
            value: false,
            label: $_('settings.notifications.garden.choose', { default: 'Choose channels' }),
            help: $_('settings.notifications.garden.choose_help', { default: 'Uses saved credentials; their bird switches can stay off.' })
        }
    ]);

    async function refresh(signal?: AbortSignal): Promise<void> {
        loading = true;
        error = null;
        try {
            status = await fetchGardenNotifications(signal);
        } catch (failure) {
            if (!signal?.aborted) error = failure instanceof Error ? failure.message : $_('common.error');
        } finally {
            loading = false;
        }
    }

    // Reads the saved attempt counts from the server; it never sends anything.
    $effect(() => {
        if (!enabled || !statusAvailable) return;
        const controller = new AbortController();
        void refresh(controller.signal);
        return () => controller.abort();
    });

    function toggle(channel: GardenNotificationChannel): void {
        channels = channels.includes(channel) ? channels.filter((value) => value !== channel) : [...channels, channel];
    }
</script>

{#snippet gardenIcon()}
    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 20h10M12 20v-7m0 0c-3 0-5-2-5-5 3 0 5 2 5 5Zm0 0c0-3 2-5 5-5 0 3-2 5-5 5Z" /></svg>
{/snippet}

<SettingsCard
    iconSnippet={gardenIcon}
    title={$_('settings.notifications.garden.title', { default: 'Garden animals' })}
    description={$_('settings.notifications.garden.desc', { default: 'Alerts when a Garden animal is named, separate from bird alerts.' })}
>
    <div class="space-y-4 break-words" data-garden-notifications>
        <SettingsRow
            labelId="garden-notifications"
            label={$_('settings.notifications.garden.enabled', { default: 'Send Garden alerts' })}
            description={$_('settings.notifications.garden.enabled_help', { default: 'One alert per visit when an animal is named automatically or you accept its species. Apply Settings to save.' })}
        >
            <SettingsToggle
                checked={enabled}
                labelledBy="garden-notifications"
                srLabel={$_('settings.notifications.garden.enabled', { default: 'Send Garden alerts' })}
                onchange={(value) => (enabled = value)}
            />
        </SettingsRow>

        {#if enabled}
            <!-- A fieldset is as wide as its content unless told otherwise; min-w-0 lets it wrap. -->
            <fieldset class="min-w-0 space-y-2">
                <legend class="mb-2 text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.notifications.garden.send_to', { default: 'Send Garden alerts to' })}</legend>
                <div class="grid grid-cols-1 gap-3 md:grid-cols-2">
                    {#each modes as option (option.value)}
                        <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border px-4 py-3 focus-within:ring-2 focus-within:ring-brand-500 focus-within:ring-offset-2 dark:focus-within:ring-offset-slate-950 {useBirdChannels === option.value ? 'border-brand-400 bg-brand-100/70 dark:bg-brand-900/30' : 'border-slate-200 bg-white/70 dark:border-slate-700 dark:bg-slate-900/40'}">
                            <input class="mt-0.5 h-4 w-4 flex-shrink-0 accent-brand-600" type="radio" name="garden-notification-channel-mode"
                                checked={useBirdChannels === option.value} onchange={() => (useBirdChannels = option.value)} />
                            <span class="min-w-0">
                                <span class="block text-sm font-semibold text-slate-900 dark:text-white">{option.label}</span>
                                <span class="mt-0.5 block text-xs leading-snug text-slate-600 dark:text-slate-400">{option.help}</span>
                            </span>
                        </label>
                    {/each}
                </div>
            </fieldset>

            {#if useBirdChannels}
                {#if delivery.length > 0}
                    <p class="text-xs text-slate-700 dark:text-slate-300" data-garden-delivery>{$_('settings.notifications.garden.bird_uses', { default: 'Sends to {channels}.', values: { channels: deliveryNames } })}</p>
                {:else}
                    <p class="text-xs text-amber-800 dark:text-amber-200" data-garden-delivery>{$_('settings.notifications.garden.bird_none', { default: 'No bird channel is switched on and configured, so no Garden alert can be sent. Switch one on above, or choose channels.' })}</p>
                {/if}
            {:else}
                <div class="flex flex-wrap gap-2" role="group" aria-label={$_('settings.notifications.garden.channels_label', { default: 'Garden delivery channels' })}>
                    {#each birdChannels as channel (channel.id)}
                        <button type="button" class="btn btn-secondary min-h-11 whitespace-normal" aria-pressed={channels.includes(channel.id)}
                            aria-label={$_('settings.notifications.garden.channel', { default: 'Garden alerts via {channel}', values: { channel: channel.label } })}
                            onclick={() => toggle(channel.id)}>{channel.label}<span aria-hidden="true">{channels.includes(channel.id) ? '✓' : '+'}</span></button>
                    {/each}
                </div>
                {#if channels.length === 0}
                    <p class="text-xs text-amber-800 dark:text-amber-200" data-garden-delivery>{$_('settings.notifications.garden.choose_one', { default: 'Choose at least one channel to deliver Garden alerts.' })}</p>
                {:else if missingCredentials.length > 0}
                    <p class="text-xs text-amber-800 dark:text-amber-200" data-garden-delivery>{$_('settings.notifications.garden.credentials', { default: 'No saved credentials for {channels}, so Garden alerts there will fail. Add them in the channel cards above.', values: { channels: missingNames } })}</p>
                {/if}
            {/if}

            <SettingsRow
                labelId="garden-notification-photo"
                label={$_('settings.notifications.garden.include_photo', { default: 'Include the photo' })}
                description={$_('settings.notifications.garden.include_photo_help', { default: 'Attaches the saved animal crop, or the capture photo when there is no crop. Only confirmed animals are sent, so it is a photo you or the automatic check accepted. Text only if no photo can be read.' })}
            >
                <SettingsToggle
                    checked={includePhoto}
                    labelledBy="garden-notification-photo"
                    srLabel={$_('settings.notifications.garden.include_photo', { default: 'Include the photo' })}
                    onchange={(value) => (includePhoto = value)}
                />
            </SettingsRow>

            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.garden.privacy', { default: 'Sends the animal name, camera, sighting time and, if chosen, the photo to these services. The link opens this capture here; a visitor can open it only while public access shares it.' })}</p>
            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.garden.rules', { default: 'Sent within five minutes of the name being decided, for sightings up to two hours old, so turning alerts on never replays history. One attempt per channel per visit; failed or uncertain sends are not retried.' })}</p>

            <div class="space-y-2 text-xs" aria-busy={loading} data-garden-notification-status>
                {#if !statusAvailable}
                    <p class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.garden.status_after_apply', { default: 'Delivery status appears once Apply Settings has switched Garden on.' })}</p>
                {:else}
                    {#if status}
                        <p>{$_('settings.notifications.garden.status', { default: 'Saved delivery attempts. Accepted by channel: {sent}. Failed: {failed}. Unconfirmed: {unknown}. Skipped: {skipped}.', values: {
                            sent: status.attempts.sent ?? 0, failed: status.attempts.failed ?? 0,
                            unknown: status.attempts.attempted ?? 0, skipped: status.attempts.skipped ?? 0
                        } })}</p>
                    {/if}
                    {#if error}<p role="alert" class="text-red-700 dark:text-red-300">{error}</p>{/if}
                    <button type="button" class="btn btn-secondary min-h-11" disabled={loading} onclick={() => void refresh()}>
                        {loading ? $_('common.loading') : $_('settings.notifications.garden.refresh', { default: 'Refresh delivery status' })}
                    </button>
                {/if}
            </div>
        {/if}
    </div>
</SettingsCard>
