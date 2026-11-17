<script lang="ts">
    /**
     * Garden alerts, set up with the channels they use. By default they follow the bird channels
     * switched on in Alerts; an explicit choice uses saved credentials while the bird switch stays
     * off. Shown in Alerts under More options, marked Beta, beside the channels they send through.
     * Bird filters, mode and cooldown are bird rules and do not apply here.
     */
    import { _, locale } from 'svelte-i18n';
    import { fetchGardenNotifications, type GardenNotificationChannel, type GardenNotificationStatus } from '../../api/garden';
    import { gardenChannelsMissingCredentials, gardenDeliveryChannels } from '../../settings/garden-notifications';
    import { formatChannelList, type PolicyChannel } from '../../settings/notification-policy';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    interface Props {
        enabled?: boolean;
        useBirdChannels?: boolean;
        channels?: GardenNotificationChannel[];
        includePhoto?: boolean;
        /** The bird channels as the page holds them now, saved or not. */
        birdChannels?: PolicyChannel[];
        /** Whether the saved settings have Garden on, so its delivery status can be read. */
        statusAvailable?: boolean;
    }

    let {
        enabled = $bindable(false),
        useBirdChannels = $bindable(true),
        channels = $bindable<GardenNotificationChannel[]>([]),
        includePhoto = $bindable(true),
        birdChannels = [],
        statusAvailable = false
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
            help: $_('settings.notifications.garden.use_bird_help', { default: 'The Notifications channels that are switched on and set up.' })
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

<!-- Shown inside Garden's Alerts section; the channels themselves are set up in Notifications. -->
<div class="space-y-4 wrap-break-word" data-garden-notifications>
    <SettingsRow
        labelId="garden-notifications"
        label={$_('settings.notifications.garden.enabled', { default: 'Send Garden alerts' })}
        description={$_('settings.notifications.garden.enabled_help', { default: 'One alert per visit when an animal is named automatically or you accept its species. Takes effect when you save changes.' })}
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
            <div class="space-y-1">
                {#each modes as option (option.value)}
                    <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                        <input class="mt-0.5 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="garden-notification-channel-mode"
                            checked={useBirdChannels === option.value} onchange={() => (useBirdChannels = option.value)} />
                        <span class="min-w-0">
                            <span class="block text-sm font-medium text-slate-900 dark:text-white">{option.label}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{option.help}</span>
                        </span>
                    </label>
                {/each}
            </div>
        </fieldset>

        {#if useBirdChannels}
            {#if delivery.length > 0}
                <p class="text-xs text-slate-700 dark:text-slate-300" data-garden-delivery>{$_('settings.notifications.garden.bird_uses', { default: 'Sends to {channels}.', values: { channels: deliveryNames } })}</p>
            {:else}
                <p class="text-xs text-attention-800 dark:text-attention-200" data-garden-delivery>{$_('settings.notifications.garden.bird_none', { default: 'No bird channel is switched on and set up, so no Garden alert can be sent. Switch one on in Notifications, or choose channels here.' })}</p>
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
                <p class="text-xs text-attention-800 dark:text-attention-200" data-garden-delivery>{$_('settings.notifications.garden.choose_one', { default: 'Choose at least one channel to deliver Garden alerts.' })}</p>
            {:else if missingCredentials.length > 0}
                <p class="text-xs text-attention-800 dark:text-attention-200" data-garden-delivery>{$_('settings.notifications.garden.credentials', { default: 'No saved credentials for {channels}, so Garden alerts there will fail. Add them in Notifications.', values: { channels: missingNames } })}</p>
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

        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.garden.privacy', { default: 'Sends the animal name, the camera, the time it was seen and, if chosen, the photo to these services. The link opens this capture here; a guest can open it only while public access shares it.' })}</p>
        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.garden.rules', { default: 'Sent within five minutes of the name being decided, for visits up to two hours old, so turning alerts on never replays history. One attempt per channel per visit; failed or uncertain sends are not retried.' })}</p>

        <div class="space-y-2 text-xs" aria-busy={loading} data-garden-notification-status>
            {#if !statusAvailable}
                <p class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.garden.status_after_apply', { default: 'Delivery status appears once Garden is switched on and saved.' })}</p>
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
