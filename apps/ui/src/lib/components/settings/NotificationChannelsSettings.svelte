<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { TestEmailRequest, TestEmailResponse, OAuthAuthorizeResponse } from '../../api';
    import SecretInput from './_primitives/SecretInput.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticResult } from '../../utils/diagnostic-runner';
    import { testNotification } from '../../api/maintenance';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import { requestErrorMessage } from '../../settings/error-message';
    import { NOTIFICATION_CHANNELS_SECTION_ID as CHANNELS_SECTION_ID } from '../../settings/notification-policy';

    // Where alerts go: each channel, its sign-in and a test that sends one real message.
    let connectingGmail = $state(false);
    let connectingOutlook = $state(false);
    let disconnectingEmailOAuth = $state(false);

    let {
        discordEnabled = $bindable(false),
        discordWebhook = $bindable(''),
        discordWebhookSaved = $bindable(false),
        discordBotName = $bindable('YA-WAMF Bird Bot'),
        pushoverEnabled = $bindable(false),
        pushoverUserKey = $bindable(''),
        pushoverUserSaved = $bindable(false),
        pushoverApiToken = $bindable(''),
        pushoverTokenSaved = $bindable(false),
        pushoverPriority = $bindable(0),
        pushoverDevice = $bindable(''),
        telegramEnabled = $bindable(false),
        telegramBotToken = $bindable(''),
        telegramTokenSaved = $bindable(false),
        telegramChatId = $bindable(''),
        telegramChatIdSaved = $bindable(false),
        emailEnabled = $bindable(false),
        emailUseOAuth = $bindable(true),
        emailConnectedEmail = $bindable<string | null>(null),
        emailOAuthProvider = $bindable<string | null>(null),
        emailGmailClientId = $bindable(''),
        emailGmailClientSecret = $bindable(''),
        emailGmailClientSecretSaved = $bindable(false),
        emailOutlookClientId = $bindable(''),
        emailOutlookClientSecret = $bindable(''),
        emailOutlookClientSecretSaved = $bindable(false),
        emailOnlyOnEnd = $bindable(false),
        emailSmtpHost = $bindable(''),
        emailSmtpPort = $bindable(587),
        emailSmtpUseTls = $bindable(true),
        emailSmtpUsername = $bindable(''),
        emailSmtpPassword = $bindable(''),
        emailSmtpPasswordSaved = $bindable(false),
        emailFromEmail = $bindable(''),
        emailToEmail = $bindable(''),
        emailIncludeSnapshot = $bindable(true),
        sendTestEmail,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        onActionFeedback = (_type: 'success' | 'error', _text: string) => {}
    }: {
        discordEnabled: boolean;
        discordWebhook: string;
        discordWebhookSaved: boolean;
        discordBotName: string;
        pushoverEnabled: boolean;
        pushoverUserKey: string;
        pushoverUserSaved: boolean;
        pushoverApiToken: string;
        pushoverTokenSaved: boolean;
        pushoverPriority: number;
        pushoverDevice: string;
        telegramEnabled: boolean;
        telegramBotToken: string;
        telegramTokenSaved: boolean;
        telegramChatId: string;
        telegramChatIdSaved: boolean;
        emailEnabled: boolean;
        emailUseOAuth: boolean;
        emailConnectedEmail: string | null;
        emailOAuthProvider: string | null;
        emailGmailClientId: string;
        emailGmailClientSecret: string;
        emailGmailClientSecretSaved: boolean;
        emailOutlookClientId: string;
        emailOutlookClientSecret: string;
        emailOutlookClientSecretSaved: boolean;
        emailOnlyOnEnd: boolean;
        emailSmtpHost: string;
        emailSmtpPort: number;
        emailSmtpUseTls: boolean;
        emailSmtpUsername: string;
        emailSmtpPassword: string;
        emailSmtpPasswordSaved: boolean;
        emailFromEmail: string;
        emailToEmail: string;
        emailIncludeSnapshot: boolean;
        sendTestEmail: (request?: TestEmailRequest) => Promise<TestEmailResponse>;
        initiateGmailOAuth: () => Promise<OAuthAuthorizeResponse>;
        initiateOutlookOAuth: () => Promise<OAuthAuthorizeResponse>;
        disconnectEmailOAuth: (provider: 'gmail' | 'outlook') => Promise<{ message: string }>;
        onActionFeedback: (type: 'success' | 'error', text: string) => void;
    } = $props();

    // A channel can send a test once it has what delivery needs, typed or already saved.
    const discordReady = $derived(Boolean(discordWebhook || discordWebhookSaved));
    const pushoverReady = $derived(Boolean((pushoverUserKey || pushoverUserSaved) && (pushoverApiToken || pushoverTokenSaved)));
    const telegramReady = $derived(Boolean((telegramBotToken || telegramTokenSaved) && (telegramChatId || telegramChatIdSaved)));
    const emailReady = $derived(Boolean(emailToEmail));

    // Channel tests use the shared DiagnosticDialog (see
    // docs/standards/diagnostics-and-dialogs.md). Each is a single real delivery
    // check, so the pass/fail a user sees is exactly what the send returned.
    let ntOpen = $state(false);
    let ntRunning = $state(false);
    let ntChannel = $state<'discord' | 'pushover' | 'telegram' | 'email'>('discord');
    let ntChannelLabel = $state('');
    let ntStages = $state<DiagnosticStage[]>([]);
    let ntResult = $state<DiagnosticResult | null>(null);
    let ntRunId = $state(0);

    async function runNotificationTest(
        channel: 'discord' | 'pushover' | 'telegram' | 'email',
        channelLabel: string,
        run: () => Promise<{ status: string; message: string }>
    ): Promise<void> {
        ntOpen = true;
        ntRunning = true;
        ntResult = null;
        ntChannel = channel;
        ntChannelLabel = channelLabel;
        ntRunId += 1;
        const label = $_('settings.notifications.test_stage_deliver', { default: 'Deliver a test message' });
        ntStages = [{ id: 'deliver', label, state: 'pending', message: '' }];
        try {
            const result = await run();
            const ok = result.status === 'ok';
            ntStages = [{ id: 'deliver', label, state: ok ? 'passed' : 'failed', message: result.message }];
            ntResult = { ok, message: result.message };
        } catch (error) {
            const text = error instanceof Error && error.message.trim()
                ? error.message
                : $_('settings.notifications.test_failed', { default: 'The test message could not be sent.' });
            ntStages = [{ id: 'deliver', label, state: 'failed', message: text }];
            ntResult = { ok: false, message: text };
        } finally {
            ntRunning = false;
        }
    }

    const runDiscordTest = () => runNotificationTest('discord', 'Discord', () => testNotification('discord', { webhook_url: discordWebhook }));
    const runPushoverTest = () => runNotificationTest('pushover', 'Pushover', () => testNotification('pushover', { user_key: pushoverUserKey, api_token: pushoverApiToken }));
    const runTelegramTest = () => runNotificationTest('telegram', 'Telegram', () => testNotification('telegram', { bot_token: telegramBotToken, chat_id: telegramChatId }));
    const runEmailTest = () => runNotificationTest('email', 'Email', async () => {
        const result = await sendTestEmail();
        return { status: 'ok', message: result.message || $_('settings.email.test_email_sent') };
    });

    function retryNotificationTest(): void {
        if (ntChannel === 'discord') void runDiscordTest();
        else if (ntChannel === 'pushover') void runPushoverTest();
        else if (ntChannel === 'telegram') void runTelegramTest();
        else void runEmailTest();
    }
</script>

<SettingsCard
    id={CHANNELS_SECTION_ID}
    title={$_('settings.notifications.channels_title', { default: 'Channels' })}
    description={$_('settings.notifications.channels_desc', { default: 'Where alerts go. Turn a channel on to set it up.' })}
>
    <div data-notification-channel="discord">
        <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
                <h3 id="discord-channel-label" class="text-base font-medium text-strong">{$_('settings.discord.title')}</h3>
                <p class="mt-1 max-w-prose text-sm leading-snug text-muted">{$_('settings.discord.desc', { default: 'Posts each alert to a Discord channel through its webhook.' })}</p>
            </div>
            <SettingsToggle
                checked={discordEnabled}
                labelledBy="discord-channel-label"
                srLabel={$_('settings.discord.title')}
                onchange={(v) => (discordEnabled = v)}
            />
        </div>

        {#if discordEnabled}
        <div class="settings-stack mt-4 border-t border-line-soft pt-4">
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <label for="discord-webhook" class="block text-base font-medium text-strong">{$_('settings.discord.webhook_url')}</label>
                <div class="min-w-0">
                    <SecretInput
                        id="discord-webhook"
                        type="text"
                        value={discordWebhook}
                        saved={discordWebhookSaved}
                        emptyPlaceholder={$_('settings.discord.webhook_placeholder')}
                        ariaLabel={$_('settings.discord.webhook_url')}
                        oninput={(v) => (discordWebhook = v)}
                    />
                </div>
            </div>
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <label for="discord-botname" class="block text-base font-medium text-strong">{$_('settings.discord.bot_username')}</label>
                <div class="min-w-0">
                    <input
                        id="discord-botname"
                        type="text"
                        bind:value={discordBotName}
                        placeholder={$_('settings.discord.bot_placeholder')}
                        aria-label={$_('settings.discord.bot_username')}
                        class="input-base w-full"
                    />
                </div>
            </div>
            <button
                type="button"
                onclick={runDiscordTest}
                disabled={ntRunning || !discordReady}
                aria-describedby={discordReady ? undefined : 'discord-test-reason'}
                class="btn btn-secondary min-h-11 px-4"
            >
                {$_('settings.discord.test_notification')}
            </button>
            {#if !discordReady}
                <p id="discord-test-reason" class="text-xs text-muted">{$_('settings.discord.test_needs', { default: 'Enter the webhook URL to send a test.' })}</p>
            {/if}
        </div>
        {/if}
    </div>

    <div data-notification-channel="pushover">
        <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
                <h3 id="pushover-channel-label" class="text-base font-medium text-strong">{$_('settings.pushover.title')}</h3>
                <p class="mt-1 max-w-prose text-sm leading-snug text-muted">{$_('settings.pushover.desc', { default: 'Sends each alert to your phone through the Pushover app.' })}</p>
            </div>
            <SettingsToggle
                checked={pushoverEnabled}
                labelledBy="pushover-channel-label"
                srLabel={$_('settings.pushover.title')}
                onchange={(v) => (pushoverEnabled = v)}
            />
        </div>

        {#if pushoverEnabled}
        <div class="settings-stack mt-4 border-t border-line-soft pt-4">
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <label for="pushover-userkey" class="block text-base font-medium text-strong">{$_('settings.pushover.user_key')}</label>
                <div class="min-w-0">
                    <SecretInput
                        id="pushover-userkey"
                        type="text"
                        value={pushoverUserKey}
                        saved={pushoverUserSaved}
                        emptyPlaceholder={$_('settings.pushover.user_key_placeholder')}
                        ariaLabel={$_('settings.pushover.user_key')}
                        oninput={(v) => (pushoverUserKey = v)}
                    />
                </div>
            </div>
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <label for="pushover-apitoken" class="block text-base font-medium text-strong">{$_('settings.pushover.api_token')}</label>
                <div class="min-w-0">
                    <SecretInput
                        id="pushover-apitoken"
                        type="text"
                        value={pushoverApiToken}
                        saved={pushoverTokenSaved}
                        emptyPlaceholder={$_('settings.pushover.api_token_placeholder')}
                        ariaLabel={$_('settings.pushover.api_token')}
                        oninput={(v) => (pushoverApiToken = v)}
                    />
                </div>
            </div>
            <button
                type="button"
                onclick={runPushoverTest}
                disabled={ntRunning || !pushoverReady}
                aria-describedby={pushoverReady ? undefined : 'pushover-test-reason'}
                class="btn btn-secondary min-h-11 px-4"
            >
                {$_('settings.pushover.test_notification')}
            </button>
            {#if !pushoverReady}
                <p id="pushover-test-reason" class="text-xs text-muted">{$_('settings.pushover.test_needs', { default: 'Enter the user key and API token to send a test.' })}</p>
            {/if}

            <AdvancedSection
                id="notifications-pushover-advanced"
                title={$_('settings.pushover.advanced_title', { default: 'Priority & device targeting' })}
            >
                <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                    <label for="pushover-priority" class="block text-base font-medium text-strong">{$_('settings.pushover.priority')}</label>
                    <div class="min-w-0">
                        <select
                            id="pushover-priority"
                            bind:value={pushoverPriority}
                            aria-label={$_('settings.pushover.priority')}
                            class="input-base w-full"
                        >
                            <option value={-2}>{$_('settings.pushover.priority_lowest')}</option>
                            <option value={-1}>{$_('settings.pushover.priority_low')}</option>
                            <option value={0}>{$_('settings.pushover.priority_normal')}</option>
                            <option value={1}>{$_('settings.pushover.priority_high')}</option>
                            <option value={2}>{$_('settings.pushover.priority_emergency')}</option>
                        </select>
                    </div>
                </div>
                <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                    <label for="pushover-device" class="block text-base font-medium text-strong">{$_('settings.pushover.device')}</label>
                    <div class="min-w-0">
                        <input
                            id="pushover-device"
                            type="text"
                            bind:value={pushoverDevice}
                            placeholder={$_('settings.pushover.device_placeholder')}
                            aria-label={$_('settings.pushover.device')}
                            class="input-base min-h-11 w-full"
                        />
                        <p class="mt-1.5 text-xs text-muted ml-1">{$_('settings.pushover.device_hint')}</p>
                    </div>
                </div>
            </AdvancedSection>
        </div>
        {/if}
    </div>

    <div data-notification-channel="telegram">
        <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
                <h3 id="telegram-channel-label" class="text-base font-medium text-strong">{$_('settings.telegram.title')}</h3>
                <p class="mt-1 max-w-prose text-sm leading-snug text-muted">{$_('settings.telegram.desc', { default: 'Sends each alert to a Telegram chat through your bot.' })}</p>
            </div>
            <SettingsToggle
                checked={telegramEnabled}
                labelledBy="telegram-channel-label"
                srLabel={$_('settings.telegram.title')}
                onchange={(v) => (telegramEnabled = v)}
            />
        </div>

        {#if telegramEnabled}
        <div class="settings-stack mt-4 border-t border-line-soft pt-4">
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <label for="telegram-bottoken" class="block text-base font-medium text-strong">{$_('settings.telegram.bot_token')}</label>
                <div class="min-w-0">
                    <SecretInput
                        id="telegram-bottoken"
                        value={telegramBotToken}
                        saved={telegramTokenSaved}
                        emptyPlaceholder={$_('settings.telegram.bot_token_placeholder')}
                        ariaLabel={$_('settings.telegram.bot_token')}
                        oninput={(v) => (telegramBotToken = v)}
                    />
                </div>
            </div>
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <label for="telegram-chatid" class="block text-base font-medium text-strong">{$_('settings.telegram.chat_id')}</label>
                <div class="min-w-0">
                    <SecretInput
                        id="telegram-chatid"
                        type="text"
                        value={telegramChatId}
                        saved={telegramChatIdSaved}
                        emptyPlaceholder={$_('settings.telegram.chat_id_placeholder')}
                        ariaLabel={$_('settings.telegram.chat_id')}
                        oninput={(v) => (telegramChatId = v)}
                    />
                </div>
            </div>
            <button
                type="button"
                onclick={runTelegramTest}
                disabled={ntRunning || !telegramReady}
                aria-describedby={telegramReady ? undefined : 'telegram-test-reason'}
                class="btn btn-secondary min-h-11 px-4"
            >
                {$_('settings.telegram.test_notification')}
            </button>
            {#if !telegramReady}
                <p id="telegram-test-reason" class="text-xs text-muted">{$_('settings.telegram.test_needs', { default: 'Enter the bot token and chat ID to send a test.' })}</p>
            {/if}
        </div>
        {/if}
    </div>

    <div data-notification-channel="email">
        <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
                <h3 id="email-channel-label" class="text-base font-medium text-strong">{$_('settings.email.title')}</h3>
                <p class="mt-1 max-w-prose text-sm leading-snug text-muted">{$_('settings.email.desc', { default: 'Sends each alert by email, from Gmail, Outlook or your own mail server.' })}</p>
            </div>
            <SettingsToggle
                checked={emailEnabled}
                labelledBy="email-channel-label"
                srLabel={$_('settings.email.title')}
                onchange={(v) => (emailEnabled = v)}
            />
        </div>

        {#if emailEnabled}
        <div class="settings-stack mt-4 border-t border-line-soft pt-4">
            <!-- Auth Mode Selector -->
            <SettingsRow labelId="email-auth-mode-label" label={$_('settings.email.auth_mode')}>
                <SettingsSegmented
                    value={emailUseOAuth ? 'oauth' : 'smtp'}
                    labelledBy="email-auth-mode-label"
                    onchange={(mode) => (emailUseOAuth = mode === 'oauth')}
                    options={[
                        { value: 'oauth', label: $_('settings.email.oauth') },
                        { value: 'smtp', label: $_('settings.email.smtp') }
                    ]}
                />
            </SettingsRow>

            {#if emailUseOAuth}
                <!-- OAuth App Credentials -->
                <div class="border-t border-line-soft pt-4 space-y-3">
                    <div>
                        <h4 class="text-sm font-semibold mb-1 text-ink">{$_('settings.email.oauth_app_credentials')}</h4>
                        <p class="text-xs text-muted">{$_('settings.email.oauth_app_credentials_desc')}</p>
                    </div>
                    <!-- Gmail credentials -->
                    <div class="grid grid-cols-1 gap-2">
                        <div>
                            <label for="gmail-client-id" class="block text-sm font-semibold mb-1 text-ink">{$_('settings.email.gmail_client_id')}</label>
                            <input
                                id="gmail-client-id"
                                type="text"
                                autocomplete="off"
                                bind:value={emailGmailClientId}
                                placeholder={$_('settings.email.gmail_client_id_placeholder')}
                                aria-label={$_('settings.email.gmail_client_id')}
                                class="input-base w-full"
                            />
                        </div>
                        <div>
                            <label for="gmail-client-secret" class="block text-sm font-semibold mb-1 text-ink">{$_('settings.email.gmail_client_secret')}</label>
                            <SecretInput
                                id="gmail-client-secret"
                                value={emailGmailClientSecret}
                                saved={emailGmailClientSecretSaved}
                                emptyPlaceholder={$_('settings.email.gmail_client_secret_placeholder')}
                                ariaLabel={$_('settings.email.gmail_client_secret')}
                                oninput={(v) => (emailGmailClientSecret = v)}
                            />
                        </div>
                    </div>
                    <!-- Outlook credentials -->
                    <div class="grid grid-cols-1 gap-2 pt-2 border-t border-line-soft">
                        <div>
                            <label for="outlook-client-id" class="block text-sm font-semibold mb-1 text-ink">{$_('settings.email.outlook_client_id')}</label>
                            <input
                                id="outlook-client-id"
                                type="text"
                                autocomplete="off"
                                bind:value={emailOutlookClientId}
                                placeholder={$_('settings.email.outlook_client_id_placeholder')}
                                aria-label={$_('settings.email.outlook_client_id')}
                                class="input-base w-full"
                            />
                        </div>
                        <div>
                            <label for="outlook-client-secret" class="block text-sm font-semibold mb-1 text-ink">{$_('settings.email.outlook_client_secret')}</label>
                            <SecretInput
                                id="outlook-client-secret"
                                value={emailOutlookClientSecret}
                                saved={emailOutlookClientSecretSaved}
                                emptyPlaceholder={$_('settings.email.outlook_client_secret_placeholder')}
                                ariaLabel={$_('settings.email.outlook_client_secret')}
                                oninput={(v) => (emailOutlookClientSecret = v)}
                            />
                        </div>
                    </div>
                </div>

                <!-- OAuth Section -->
                <div class="border-t border-line-soft pt-4 space-y-3">
                    <p class="text-xs text-muted">{$_('settings.email.oauth_desc')}</p>
                    <div class="flex gap-2">
                        <button
                            onclick={async () => {
                                try {
                                    connectingGmail = true;
                                    const response = await initiateGmailOAuth();
                                    window.open(response.authorization_url, '_blank', 'width=600,height=700');
                                    onActionFeedback('success', $_('settings.email.connect_gmail'));
                                } catch (error) {
                                    onActionFeedback('error', requestErrorMessage(error, $_('settings.email.test_email_error_generic')));
                                } finally {
                                    connectingGmail = false;
                                }
                            }}
                            aria-label={$_('settings.email.connect_gmail')}
                            disabled={connectingGmail || connectingOutlook || disconnectingEmailOAuth}
                            class="flex-1 text-sm transition-all"
                        >
                            {connectingGmail ? $_('common.testing') : $_('settings.email.connect_gmail')}
                        </button>
                        <button
                            onclick={async () => {
                                try {
                                    connectingOutlook = true;
                                    const response = await initiateOutlookOAuth();
                                    window.open(response.authorization_url, '_blank', 'width=600,height=700');
                                    onActionFeedback('success', $_('settings.email.connect_outlook'));
                                } catch (error) {
                                    onActionFeedback('error', requestErrorMessage(error, $_('settings.email.test_email_error_generic')));
                                } finally {
                                    connectingOutlook = false;
                                }
                            }}
                            aria-label={$_('settings.email.connect_outlook')}
                            disabled={connectingOutlook || connectingGmail || disconnectingEmailOAuth}
                            class="flex-1 text-sm transition-all"
                        >
                            {connectingOutlook ? $_('common.testing') : $_('settings.email.connect_outlook')}
                        </button>
                    </div>
                    {#if emailConnectedEmail}
                        <div class="flex items-center justify-between p-3 bg-status-ok-soft rounded-xl">
                            <span class="text-sm text-status-ok">{$_('settings.email.connected', { values: { email: emailConnectedEmail } })}</span>
                            <button
                                onclick={async () => {
                                    try {
                                        disconnectingEmailOAuth = true;
                                        await disconnectEmailOAuth((emailOAuthProvider as 'gmail' | 'outlook') || 'gmail');
                                        emailConnectedEmail = null;
                                        emailOAuthProvider = null;
                                        onActionFeedback('success', $_('settings.email.disconnect'));
                                    } catch (error) {
                                        onActionFeedback('error', requestErrorMessage(error, $_('settings.email.test_email_error_generic')));
                                    } finally {
                                        disconnectingEmailOAuth = false;
                                    }
                                }}
                                aria-label={$_('settings.email.disconnect')}
                                disabled={disconnectingEmailOAuth}
                                class="text-xs text-status-fail hover:underline"
                            >
                                {disconnectingEmailOAuth ? $_('common.testing') : $_('settings.email.disconnect')}
                            </button>
                        </div>
                    {/if}
                </div>
            {:else}
                <!-- SMTP Section -->
                <div class="space-y-3">
                    <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                        <label for="smtp-host" class="block text-base font-medium text-strong">{$_('settings.email.smtp_host')}</label>
                        <div class="min-w-0">
                            <input
                                id="smtp-host"
                                type="text"
                                bind:value={emailSmtpHost}
                                placeholder={$_('settings.email.smtp_host_placeholder')}
                                aria-label={$_('settings.email.smtp_host')}
                                class="input-base w-full"
                            />
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-3">
                        <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                            <label for="smtp-port" class="block text-base font-medium text-strong">{$_('settings.email.smtp_port')}</label>
                            <div class="min-w-0">
                                <input
                                    id="smtp-port"
                                    type="number"
                                    bind:value={emailSmtpPort}
                                    aria-label={$_('settings.email.smtp_port')}
                                    class="input-base w-full"
                                />
                            </div>
                        </div>
                        <div class="flex items-end">
                            <div class="flex min-h-11 items-center justify-between gap-3 w-full">
                                <span id="smtp-tls-label" class="text-sm font-semibold text-ink">{$_('settings.email.smtp_use_tls')}</span>
                                <SettingsToggle checked={emailSmtpUseTls} labelledBy="smtp-tls-label" srLabel={$_('settings.email.smtp_use_tls')} onchange={(value) => (emailSmtpUseTls = value)} />
                            </div>
                        </div>
                    </div>
                    <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                        <label for="smtp-username" class="block text-base font-medium text-strong">{$_('settings.email.smtp_username')}</label>
                        <div class="min-w-0">
                            <input
                                id="smtp-username"
                                type="text"
                                bind:value={emailSmtpUsername}
                                aria-label={$_('settings.email.smtp_username')}
                                class="input-base w-full"
                            />
                        </div>
                    </div>
                    <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                        <label for="smtp-password" class="block text-base font-medium text-strong">{$_('settings.email.smtp_password')}</label>
                        <div class="min-w-0">
                            <SecretInput
                                id="smtp-password"
                                value={emailSmtpPassword}
                                saved={emailSmtpPasswordSaved}
                                ariaLabel={$_('settings.email.smtp_password')}
                                oninput={(v) => (emailSmtpPassword = v)}
                            />
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Common Email Settings -->
            <div class="pt-4 border-t border-line-soft space-y-3">
                <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                    <label for="email-from" class="block text-base font-medium text-strong">{$_('settings.email.from_email')}</label>
                    <div class="min-w-0">
                        <input
                            id="email-from"
                            type="email"
                            bind:value={emailFromEmail}
                            placeholder={$_('settings.email.from_email_placeholder')}
                            aria-label={$_('settings.email.from_email')}
                            class="input-base w-full"
                        />
                    </div>
                </div>
                <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                    <label for="email-to" class="block text-base font-medium text-strong">{$_('settings.email.to_email')}</label>
                    <div class="min-w-0">
                        <input
                            id="email-to"
                            type="email"
                            bind:value={emailToEmail}
                            placeholder={$_('settings.email.to_email_placeholder')}
                            aria-label={$_('settings.email.to_email')}
                            class="input-base w-full"
                        />
                    </div>
                </div>
                <div>
                    <div class="flex min-h-11 items-center justify-between gap-3 ">
                                <span id="email-include-snapshot-label" class="text-sm font-semibold text-ink">{$_('settings.email.include_snapshot')}</span>
                                <SettingsToggle checked={emailIncludeSnapshot} labelledBy="email-include-snapshot-label" srLabel={$_('settings.email.include_snapshot')} onchange={(value) => (emailIncludeSnapshot = value)} />
                            </div>
                </div>
            </div>

            <AdvancedSection
                id="notifications-email-advanced"
                title={$_('settings.email.advanced_title', { default: 'Delivery timing & dashboard link' })}
            >
                <div>
                    <div class="flex min-h-11 items-center justify-between gap-3 ">
                                <span id="email-only-on-end-label" class="text-sm font-semibold text-ink">{$_('settings.email.only_on_end')}</span>
                                <SettingsToggle checked={emailOnlyOnEnd} labelledBy="email-only-on-end-label" srLabel={$_('settings.email.only_on_end')} onchange={(value) => (emailOnlyOnEnd = value)} />
                            </div>
                    <p class="mt-1 text-xs text-muted">{$_('settings.email.only_on_end_desc')}</p>
                </div>
            </AdvancedSection>

            <button
                type="button"
                onclick={runEmailTest}
                disabled={ntRunning || !emailReady}
                aria-describedby={emailReady ? undefined : 'email-test-reason'}
                class="btn btn-secondary min-h-11 px-4"
            >
                {$_('settings.email.test_email')}
            </button>
            {#if !emailReady}
                <p id="email-test-reason" class="text-xs text-muted">{$_('settings.email.test_needs', { default: 'Enter the recipient address to send a test.' })}</p>
            {/if}
        </div>
        {/if}
    </div>
</SettingsCard>

{#if ntOpen}
    <DiagnosticDialog
        title={$_('settings.notifications.test_title', { default: 'Notification test' })}
        subtitle={$_('settings.notifications.test_subtitle', { default: 'Sends one test message using the current settings for this channel.' })}
        stages={ntStages}
        busy={ntRunning}
        result={ntResult}
        runId={ntRunId}
        retryLabel={$_('settings.notifications.test_retry', { default: 'Send again' })}
        onClose={() => (ntOpen = false)}
        onRetry={retryNotificationTest}
    >
        {#snippet summary()}
            <span class="text-sm font-semibold text-ink">{$_('settings.notifications.test_channel', { default: 'Channel' })}</span>
            <span class="font-bold text-ink">{ntChannelLabel}</span>
        {/snippet}
    </DiagnosticDialog>
{/if}
