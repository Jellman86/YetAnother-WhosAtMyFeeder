<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type NotificationSettingsView from '../NotificationSettings.svelte';
    import { loadNotificationSettings } from './part-loaders';

    // Alerts: when you hear about a visit, and where the message goes. Holds what was the
    // Notifications tab.
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
        discordEnabled = $bindable(),
        discordWebhook = $bindable(),
        discordWebhookSaved = $bindable(),
        discordBotName = $bindable(),
        pushoverEnabled = $bindable(),
        pushoverUserKey = $bindable(),
        pushoverUserSaved = $bindable(),
        pushoverApiToken = $bindable(),
        pushoverTokenSaved = $bindable(),
        pushoverPriority = $bindable(),
        pushoverDevice = $bindable(),
        telegramEnabled = $bindable(),
        telegramBotToken = $bindable(),
        telegramTokenSaved = $bindable(),
        telegramChatId = $bindable(),
        telegramChatIdSaved = $bindable(),
        notificationLanguage = $bindable(),
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
        instanceUrl = $bindable(),
        linkTarget = $bindable(),
        frigateExternalUrl,
        onOpenConnection,
        gardenBeta,
        onOpenGarden,
        sendTestEmail,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        onActionFeedback
    }: ComponentProps<typeof NotificationSettingsView> = $props();
</script>

<div class="space-y-8" data-settings-section="alerts">
    <div class="space-y-8" data-settings-part="notifications">
        <LazyRoute loader={loadNotificationSettings} label={$_('settings.tabs.notifications')}>
        {#snippet content(NotificationSettings)}
        <NotificationSettings
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
            bind:discordEnabled
            bind:discordWebhook
            bind:discordWebhookSaved
            bind:discordBotName
            bind:pushoverEnabled
            bind:pushoverUserKey
            bind:pushoverUserSaved
            bind:pushoverApiToken
            bind:pushoverTokenSaved
            bind:pushoverPriority
            bind:pushoverDevice
            bind:telegramEnabled
            bind:telegramBotToken
            bind:telegramTokenSaved
            bind:telegramChatId
            bind:telegramChatIdSaved
            bind:notificationLanguage
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
            bind:instanceUrl
            bind:linkTarget
            {frigateExternalUrl}
            {onOpenConnection}
            {gardenBeta}
            {onOpenGarden}
            {sendTestEmail}
            {initiateGmailOAuth}
            {initiateOutlookOAuth}
            {disconnectEmailOAuth}
            {onActionFeedback}
        />
        {/snippet}
        </LazyRoute>
    </div>
</div>
