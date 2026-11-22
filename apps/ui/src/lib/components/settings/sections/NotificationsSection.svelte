<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import StatusChip from '../../ui/StatusChip.svelte';
    import SectionMore from './SectionMore.svelte';
    import type NotificationSettingsView from '../NotificationSettings.svelte';
    import type NotificationChannelsSettingsView from '../NotificationChannelsSettings.svelte';
    import type GardenNotificationSettingsView from '../GardenNotificationSettings.svelte';
    import { policyChannels } from '../../../settings/notification-policy';
    import { settingsStore } from '../../../stores/settings.svelte';
    import { settingsSectionName } from '../../../settings/settings-place';
    import { loadGardenNotificationSettings, loadNotificationChannelsSettings, loadNotificationSettings } from './part-loaders';

    // Notifications: every way YA-WAMF tells you something. When you hear about a visit, with the
    // custom rules, then each channel and, while Garden animals is on, Garden's own alerts, which
    // send through those channels; the cooldown, language, link and species filter under More options.
    type Props = Omit<ComponentProps<typeof NotificationSettingsView>, 'channels' | 'region'>
        & ComponentProps<typeof NotificationChannelsSettingsView>
        & {
            gardenBeta: boolean;
            gardenNotificationsEnabled: boolean;
            gardenNotificationsUseBirdChannels: boolean;
            gardenNotificationChannels: ComponentProps<typeof GardenNotificationSettingsView>['channels'];
            gardenNotificationsIncludePhoto: boolean;
        };

    let {
        notifyMinConfidence = $bindable(),
        notifyAudioOnly = $bindable(),
        filterSpeciesMode = $bindable(),
        filterSpeciesEntries = $bindable(),
        legacySpeciesWhitelist = $bindable(),
        notifyMode = $bindable(),
        notifyOnInsert = $bindable(),
        notifyOnUpdate = $bindable(),
        notifyDelayUntilVideo = $bindable(),
        notifyVideoFallbackTimeout = $bindable(),
        notifyCooldownMinutes = $bindable(),
        notificationLanguage = $bindable(),
        instanceUrl = $bindable(),
        linkTarget = $bindable(),
        frigateExternalUrl,
        onOpenConnection,
        discordEnabled = $bindable(),
        discordWebhook = $bindable(),
        discordWebhookSaved = $bindable(),
        discordBotName = $bindable(),
        discordIncludeSnapshot = $bindable(),
        pushoverEnabled = $bindable(),
        pushoverUserKey = $bindable(),
        pushoverUserSaved = $bindable(),
        pushoverApiToken = $bindable(),
        pushoverTokenSaved = $bindable(),
        pushoverPriority = $bindable(),
        pushoverDevice = $bindable(),
        pushoverIncludeSnapshot = $bindable(),
        telegramEnabled = $bindable(),
        telegramBotToken = $bindable(),
        telegramTokenSaved = $bindable(),
        telegramChatId = $bindable(),
        telegramChatIdSaved = $bindable(),
        telegramIncludeSnapshot = $bindable(),
        emailEnabled = $bindable(),
        emailUseOAuth = $bindable(),
        emailConnectedEmail = $bindable(),
        emailOAuthProvider = $bindable(),
        emailGmailClientId = $bindable(),
        emailGmailClientSecret = $bindable(),
        emailGmailClientSecretSaved = $bindable(),
        emailOutlookClientId = $bindable(),
        emailOutlookClientSecret = $bindable(),
        emailOutlookClientSecretSaved = $bindable(),
        emailOnlyOnEnd = $bindable(),
        emailSmtpHost = $bindable(),
        emailSmtpPort = $bindable(),
        emailSmtpUseTls = $bindable(),
        emailSmtpUsername = $bindable(),
        emailSmtpPassword = $bindable(),
        emailSmtpPasswordSaved = $bindable(),
        emailFromEmail = $bindable(),
        emailToEmail = $bindable(),
        emailIncludeSnapshot = $bindable(),
        sendTestEmail,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        onActionFeedback,
        gardenBeta,
        gardenNotificationsEnabled = $bindable(),
        gardenNotificationsUseBirdChannels = $bindable(),
        gardenNotificationChannels = $bindable(),
        gardenNotificationsIncludePhoto = $bindable()
    }: Props = $props();

    // The channels set up, as the delivery sentence and Garden's alerts name them.
    const channels = $derived(
        policyChannels(
            {
                discord: { enabled: discordEnabled, webhook: discordWebhook, webhookSaved: discordWebhookSaved },
                pushover: { enabled: pushoverEnabled, user: pushoverUserKey, userSaved: pushoverUserSaved, token: pushoverApiToken, tokenSaved: pushoverTokenSaved },
                telegram: { enabled: telegramEnabled, token: telegramBotToken, tokenSaved: telegramTokenSaved, chatId: telegramChatId, chatIdSaved: telegramChatIdSaved },
                email: { enabled: emailEnabled, useOAuth: emailUseOAuth, connectedEmail: emailConnectedEmail, smtpHost: emailSmtpHost, toEmail: emailToEmail }
            },
            (id) => $_(`settings.notifications.sentence.channel_${id}`)
        )
    );
    // Garden's alert status is read only once the switch that turns Garden on has been saved.
    const gardenSaved = $derived(settingsStore.settings?.beta_garden_animals === true);
</script>

<div class="space-y-8" data-settings-section="notifications">
    <div class="space-y-8" data-settings-part="rules">
        <LazyRoute loader={loadNotificationSettings} label={$_('settings.tabs.rules', { default: 'When to notify' })}>
        {#snippet content(NotificationSettings)}
        <NotificationSettings
            region="main"
            bind:notifyMinConfidence
            bind:notifyAudioOnly
            bind:filterSpeciesMode
            bind:filterSpeciesEntries
            bind:legacySpeciesWhitelist
            bind:notifyMode
            bind:notifyOnInsert
            bind:notifyOnUpdate
            bind:notifyDelayUntilVideo
            bind:notifyVideoFallbackTimeout
            bind:notifyCooldownMinutes
            bind:notificationLanguage
            bind:instanceUrl
            bind:linkTarget
            {frigateExternalUrl}
            {onOpenConnection}
            {channels}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <div class="space-y-8" data-settings-part="channels">
        <LazyRoute loader={loadNotificationChannelsSettings} label={$_('settings.notifications.channels_title', { default: 'Channels' })}>
        {#snippet content(NotificationChannelsSettings)}
        <NotificationChannelsSettings
            bind:discordEnabled
            bind:discordWebhook
            bind:discordWebhookSaved
            bind:discordBotName
            bind:discordIncludeSnapshot
            bind:pushoverEnabled
            bind:pushoverUserKey
            bind:pushoverUserSaved
            bind:pushoverApiToken
            bind:pushoverTokenSaved
            bind:pushoverPriority
            bind:pushoverDevice
            bind:pushoverIncludeSnapshot
            bind:telegramEnabled
            bind:telegramBotToken
            bind:telegramTokenSaved
            bind:telegramChatId
            bind:telegramChatIdSaved
            bind:telegramIncludeSnapshot
            bind:emailEnabled
            bind:emailUseOAuth
            bind:emailConnectedEmail
            bind:emailOAuthProvider
            bind:emailGmailClientId
            bind:emailGmailClientSecret
            bind:emailGmailClientSecretSaved
            bind:emailOutlookClientId
            bind:emailOutlookClientSecret
            bind:emailOutlookClientSecretSaved
            bind:emailOnlyOnEnd
            bind:emailSmtpHost
            bind:emailSmtpPort
            bind:emailSmtpUseTls
            bind:emailSmtpUsername
            bind:emailSmtpPassword
            bind:emailSmtpPasswordSaved
            bind:emailFromEmail
            bind:emailToEmail
            bind:emailIncludeSnapshot
            {sendTestEmail}
            {initiateGmailOAuth}
            {initiateOutlookOAuth}
            {disconnectEmailOAuth}
            {onActionFeedback}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <!-- Garden's alerts send through the channels above, so they are set here, marked Beta. -->
    {#if gardenBeta}
        <section id="garden-section-alerts" class="scroll-mt-24 space-y-3" aria-labelledby="garden-alerts-title" data-settings-part="garden-alerts" data-garden-alerts>
            <div class="flex flex-wrap items-center gap-2">
                <h3 id="garden-alerts-title" class="font-display text-xl font-semibold text-strong">{$_('settings.notifications.garden_title', { default: 'Garden animal alerts' })}</h3>
                <StatusChip tone="neutral" label={$_('settings.beta.chip', { default: 'Beta' })} />
            </div>
            <div class="card-base settings-section-body">
                <LazyRoute loader={loadGardenNotificationSettings} label={$_('settings.notifications.garden_title', { default: 'Garden animal alerts' })}>
                {#snippet content(GardenNotificationSettings)}
                <GardenNotificationSettings
                    bind:enabled={gardenNotificationsEnabled}
                    bind:useBirdChannels={gardenNotificationsUseBirdChannels}
                    bind:channels={gardenNotificationChannels}
                    bind:includePhoto={gardenNotificationsIncludePhoto}
                    birdChannels={channels}
                    statusAvailable={gardenSaved}
                />
                {/snippet}
                </LazyRoute>
            </div>
        </section>
    {:else}
        <!-- Said in words while Garden animals is off, so the alerts are never looked for in vain. -->
        <p class="max-w-prose text-sm leading-relaxed text-muted" data-settings-part="garden-alerts" data-garden-alerts-off>
            {$_('settings.notifications.garden_off', { values: { section: settingsSectionName('identification', $_) }, default: 'Garden animal alerts are set here once Garden animals is turned on, under Beta features in {section}.' })}
        </p>
    {/if}

    <SectionMore section="notifications" summary={$_('settings.more.notifications', { default: 'Cooldown, language, the link and the species filter' })}>
        <LazyRoute loader={loadNotificationSettings} label={$_('settings.tabs.rules', { default: 'When to notify' })}>
        {#snippet content(NotificationSettings)}
        <NotificationSettings
            region="more"
            bind:notifyMinConfidence
            bind:notifyAudioOnly
            bind:filterSpeciesMode
            bind:filterSpeciesEntries
            bind:legacySpeciesWhitelist
            bind:notifyMode
            bind:notifyOnInsert
            bind:notifyOnUpdate
            bind:notifyDelayUntilVideo
            bind:notifyVideoFallbackTimeout
            bind:notifyCooldownMinutes
            bind:notificationLanguage
            bind:instanceUrl
            bind:linkTarget
            {frigateExternalUrl}
            {onOpenConnection}
            {channels}
        />
        {/snippet}
        </LazyRoute>
    </SectionMore>
</div>
