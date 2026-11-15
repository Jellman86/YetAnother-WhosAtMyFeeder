<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { notificationLinkPreview, type NotificationLinkTarget } from '../../settings/notification-link';
    import {
        searchSpecies,
        type SearchResult,
        type TestEmailRequest,
        type TestEmailResponse,
        type OAuthAuthorizeResponse
    } from '../../api';
    import type { BlockedSpeciesEntry, NotificationSpeciesFilterMode } from '../../api/settings';
    import {
        buildBlockedSpeciesEntry,
        formatBlockedSpeciesLabel,
        mergeBlockedSpeciesEntries,
    } from '../../settings/blocked-species';
    import SecretInput from './_primitives/SecretInput.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticResult } from '../../utils/diagnostic-runner';
    import { testNotification } from '../../api/maintenance';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import NotificationPolicySentence from './NotificationPolicySentence.svelte';
    import { policyChannels } from '../../settings/notification-policy';
    import FieldRefusal from './_primitives/FieldRefusal.svelte';
    import { settingsFieldErrorLookup } from '../../settings/field-error-context';

    function extractErrorMessage(error: unknown, fallback: string): string {
        const message = error instanceof Error ? error.message : fallback;
        if (typeof message === 'string' && message.trim().startsWith('{')) {
            try {
                const parsed = JSON.parse(message);
                const payload = parsed && typeof parsed === 'object'
                    ? parsed as Record<string, unknown>
                    : {};
                return String(payload.detail || payload.message || fallback);
            } catch {
                return message;
            }
        }
        return message;
    }

    let connectingGmail = $state(false);
    let connectingOutlook = $state(false);
    let disconnectingEmailOAuth = $state(false);

    // Props
    let {
        // Global filters
        notifyMinConfidence = $bindable(0.7),
        notifyAudioOnly = $bindable(false),
        filterSpeciesMode = $bindable<NotificationSpeciesFilterMode>('none'),
        filterSpeciesEntries = $bindable<BlockedSpeciesEntry[]>([]),
        legacySpeciesWhitelist = $bindable<string[]>([]),
        notifyMode = $bindable<'silent' | 'final' | 'standard' | 'realtime' | 'custom'>('standard'),
        notifyOnInsert = $bindable(true),
        notifyOnUpdate = $bindable(false),
        notifyDelayUntilVideo = $bindable(false),
        notifyVideoFallbackTimeout = $bindable(45),
        notifyCooldownMinutes = $bindable(0),

        // Discord
        discordEnabled = $bindable(false),
        discordWebhook = $bindable(''),
        discordWebhookSaved = $bindable(false),
        discordBotName = $bindable('YA-WAMF Bird Bot'),

        // Pushover
        pushoverEnabled = $bindable(false),
        pushoverUserKey = $bindable(''),
        pushoverUserSaved = $bindable(false),
        pushoverApiToken = $bindable(''),
        pushoverTokenSaved = $bindable(false),
        pushoverPriority = $bindable(0),
        pushoverDevice = $bindable(''),

        // Telegram
        telegramEnabled = $bindable(false),
        telegramBotToken = $bindable(''),
        telegramTokenSaved = $bindable(false),
        telegramChatId = $bindable(''),
        telegramChatIdSaved = $bindable(false),

        // Notification language
        notificationLanguage = $bindable('en'),

        // Email
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
        instanceUrl = $bindable(''),
        linkTarget = $bindable<NotificationLinkTarget>('yawamf'),
        frigateExternalUrl = '',
        onOpenConnection = () => {},

        // Garden animals (beta): its alerts are set in Garden; this tab only links there.
        gardenBeta = false,
        onOpenGarden,

        // Functions
        sendTestEmail,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        onActionFeedback = (_type: 'success' | 'error', _text: string) => {}
    }: {
        notifyMinConfidence: number;
        notifyAudioOnly: boolean;
        filterSpeciesMode: NotificationSpeciesFilterMode;
        filterSpeciesEntries: BlockedSpeciesEntry[];
        legacySpeciesWhitelist: string[];
        notifyMode: 'silent' | 'final' | 'standard' | 'realtime' | 'custom';
        notifyOnInsert: boolean;
        notifyOnUpdate: boolean;
        notifyDelayUntilVideo: boolean;
        notifyVideoFallbackTimeout: number;
        notifyCooldownMinutes: number;
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
        notificationLanguage: string;
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
        instanceUrl: string;
        linkTarget: NotificationLinkTarget;
        frigateExternalUrl?: string;
        /** Opens Connection, where the Frigate public URL is set. */
        onOpenConnection?: () => void;
        /** Whether the Garden beta is on, as the page holds it. */
        gardenBeta?: boolean;
        /** Opens Garden's alerts in Beta features. */
        onOpenGarden?: () => void;
        sendTestEmail: (request?: TestEmailRequest) => Promise<TestEmailResponse>;
        initiateGmailOAuth: () => Promise<OAuthAuthorizeResponse>;
        initiateOutlookOAuth: () => Promise<OAuthAuthorizeResponse>;
        disconnectEmailOAuth: (provider: 'gmail' | 'outlook') => Promise<{ message: string }>;
        onActionFeedback: (type: 'success' | 'error', text: string) => void;
    } = $props();

    const fieldErrors = settingsFieldErrorLookup();
    const instanceUrlRefusal = $derived(fieldErrors?.errorFor('notifications_instance_url'));

    const linkPreview = $derived(notificationLinkPreview(linkTarget, instanceUrl, frigateExternalUrl));
    const frigateUrlMissing = $derived(linkTarget === 'frigate' && frigateExternalUrl.trim() === '');
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

    let speciesSearchQuery = $state('');
    let speciesSearchResults = $state<SearchResult[]>([]);
    let speciesSearchLoading = $state(false);
    let speciesSearchError = $state('');

    function applyPreset(mode: typeof notifyMode) {
        if (mode === 'silent') {
            notifyOnInsert = false;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = false;
            return;
        }
        if (mode === 'final') {
            notifyOnInsert = true;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = true;
            return;
        }
        if (mode === 'realtime') {
            notifyOnInsert = true;
            notifyOnUpdate = true;
            notifyDelayUntilVideo = false;
            return;
        }
        if (mode === 'standard') {
            notifyOnInsert = true;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = false;
        }
    }

    function setMode(mode: typeof notifyMode) {
        notifyMode = mode;
        if (mode !== 'custom') {
            applyPreset(mode);
        }
    }

    const speciesFilterSectionId = 'notification-species-filter-section';
    const channelsSectionId = 'notification-channels';
    // What the cooldown goes back to when switched on again; ten minutes the first time.
    // svelte-ignore state_referenced_locally
    let lastCooldownMinutes = $state(notifyCooldownMinutes > 0 ? notifyCooldownMinutes : 10);

    const speciesFilterCount = $derived(
        filterSpeciesEntries.length +
            (filterSpeciesMode === 'whitelist' ? legacySpeciesWhitelist.length : 0)
    );

    const policyChannelList = $derived(
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

    function setSpeciesFilterMode(mode: NotificationSpeciesFilterMode) {
        filterSpeciesMode = mode;
        speciesSearchQuery = '';
        speciesSearchResults = [];
        speciesSearchError = '';
        if (mode === 'none') {
            filterSpeciesEntries = [];
            legacySpeciesWhitelist = [];
        }
    }

    function speciesEntryKey(entry: BlockedSpeciesEntry): string {
        if (entry.taxa_id != null) return `taxa:${entry.taxa_id}`;
        if (entry.scientific_name) return `scientific:${entry.scientific_name.toLocaleLowerCase()}`;
        if (entry.common_name) return `common:${entry.common_name.toLocaleLowerCase()}`;
        return 'empty';
    }

    function addSpeciesFilterResult(result: SearchResult) {
        const entry = buildBlockedSpeciesEntry(result);
        if (!entry) return;
        filterSpeciesEntries = mergeBlockedSpeciesEntries([...filterSpeciesEntries, entry]);
        speciesSearchQuery = '';
        speciesSearchResults = [];
        speciesSearchError = '';
    }

    function removeSpeciesFilterEntry(entry: BlockedSpeciesEntry) {
        const key = speciesEntryKey(entry);
        filterSpeciesEntries = filterSpeciesEntries.filter((candidate) => speciesEntryKey(candidate) !== key);
    }

    function removeLegacySpeciesWhitelist(species: string) {
        legacySpeciesWhitelist = legacySpeciesWhitelist.filter((candidate) => candidate !== species);
    }

    function getResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;
        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }
        return { primary: common || scientific || fallback, secondary: null };
    }

    const speciesFilterListTitle = $derived(
        filterSpeciesMode === 'blacklist'
            ? $_('settings.notifications.species_filter_blacklist_list')
            : $_('settings.notifications.species_filter_whitelist_list')
    );

    $effect(() => {
        const query = speciesSearchQuery.trim();
        if (filterSpeciesMode === 'none' || query.length < 2) {
            speciesSearchResults = [];
            speciesSearchLoading = false;
            speciesSearchError = '';
            return;
        }

        speciesSearchLoading = true;
        const timeout = setTimeout(async () => {
            try {
                speciesSearchResults = await searchSpecies(query, 20, true);
                speciesSearchError = '';
            } catch (error) {
                speciesSearchResults = [];
                speciesSearchError = extractErrorMessage(error, $_('settings.notifications.species_filter_search_failed'));
            } finally {
                speciesSearchLoading = false;
            }
        }, 250);

        return () => {
            clearTimeout(timeout);
        };
    });
</script>

<div class="space-y-6">

    <!-- Global Notification Filters -->
    <SettingsCard title={$_('settings.notifications.global_filters')}>
            <!-- Delivery policy as one sentence; every slot is editable in place -->
            <NotificationPolicySentence
                mode={notifyMode}
                onModeChange={setMode}
                minConfidence={notifyMinConfidence}
                onMinConfidenceChange={(value) => (notifyMinConfidence = value)}
                videoFallbackTimeout={notifyVideoFallbackTimeout}
                onVideoFallbackChange={(value) => (notifyVideoFallbackTimeout = value)}
                audioOnly={notifyAudioOnly}
                onAudioOnlyChange={(value) => (notifyAudioOnly = value)}
                speciesMode={filterSpeciesMode}
                speciesCount={speciesFilterCount}
                speciesSectionId={speciesFilterSectionId}
                channels={policyChannelList}
                {channelsSectionId}
            />

            <!-- Off is zero minutes: a switch says so instead of asking for "0 to disable". -->
            <div class="settings-row space-y-3 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row data-notification-cooldown>
                <div class="min-w-0">
                    <span id="notification-cooldown-label" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.notifications.cooldown')}</span>
                    <span class="mt-1 block max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.cooldown_desc')}</span>
                </div>
                <div class="min-w-0 space-y-3">
                    <SettingsToggle
                        checked={notifyCooldownMinutes > 0}
                        labelledBy="notification-cooldown-label"
                        srLabel={$_('settings.notifications.cooldown')}
                        onchange={(on) => (notifyCooldownMinutes = on ? lastCooldownMinutes : 0)}
                    />
                    {#if notifyCooldownMinutes > 0}
                        <div class="flex flex-wrap items-center gap-2">
                            <input
                                id="notification-cooldown-minutes"
                                type="number"
                                min="1"
                                step="1"
                                value={notifyCooldownMinutes}
                                oninput={(event) => {
                                    const minutes = Math.max(1, Math.floor(Number(event.currentTarget.value) || 1));
                                    notifyCooldownMinutes = minutes;
                                    lastCooldownMinutes = minutes;
                                }}
                                onblur={(event) => {
                                    // Show what will be saved: whole minutes, at least one.
                                    event.currentTarget.value = String(notifyCooldownMinutes);
                                }}
                                class="input-base min-h-11 w-24"
                                aria-labelledby="notification-cooldown-label notification-cooldown-unit"
                            />
                            <span id="notification-cooldown-unit" class="text-sm text-slate-600 dark:text-slate-400">{$_('settings.notifications.cooldown_unit')}</span>
                        </div>
                    {/if}
                </div>
            </div>

            <!-- Notification Language -->
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <div class="min-w-0">
                    <label for="notification-language" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.notifications.notification_language')}</label>
                    <p id="notification-language-desc" class="mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-400">{$_('settings.notifications.notification_language_desc')}</p>
                </div>
                <select
                    id="notification-language"
                    bind:value={notificationLanguage}
                    aria-describedby="notification-language-desc"
                    class="select-base min-h-11 w-full"
                >
                    <option value="en">English</option>
                    <option value="es">Español</option>
                    <option value="fr">Français</option>
                    <option value="de">Deutsch</option>
                    <option value="ja">日本語</option>
                    <option value="zh">中文</option>
                    <option value="ru">Русский</option>
                    <option value="pt">Português</option>
                    <option value="it">Italiano</option>
                </select>
            </div>

            <!-- Instance address: where notifications link back to -->
            <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                <div class="min-w-0">
                    <label for="notification-instance-url" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.notifications.instance_url')}</label>
                    <p id="notification-instance-url-hint" class="mt-1 max-w-prose text-sm text-slate-600 dark:text-slate-400">{$_('settings.notifications.instance_url_desc')}</p>
                </div>
                <div class="min-w-0">
                    <input
                        id="notification-instance-url"
                        type="url"
                        bind:value={instanceUrl}
                        placeholder={$_('settings.notifications.instance_url_placeholder')}
                        aria-describedby={instanceUrlRefusal ? 'notification-instance-url-hint notification-instance-url-error' : 'notification-instance-url-hint'}
                        aria-invalid={instanceUrlRefusal && !instanceUrlRefusal.conflict ? 'true' : undefined}
                        class="input-base min-h-11 w-full"
                    />
                    <FieldRefusal id="notification-instance-url-error" refusal={instanceUrlRefusal} />
                </div>
            </div>

            <!-- Where the notification link opens -->
            <div>
                <h3 class="mb-3 text-base font-medium text-slate-900 dark:text-white">{$_('settings.notifications.link_opens')}</h3>
                <div class="space-y-1" role="radiogroup" aria-label={$_('settings.notifications.link_opens')}>
                    <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                        <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-link-target" value="yawamf" bind:group={linkTarget} />
                        <span class="min-w-0">
                            <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.link_opens_yawamf')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_yawamf_desc')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_yawamf_req')}</span>
                        </span>
                    </label>
                    <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                        <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-link-target" value="frigate" bind:group={linkTarget} />
                        <span class="min-w-0">
                            <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.link_opens_frigate')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_frigate_desc')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_opens_frigate_req')}</span>
                        </span>
                    </label>
                </div>
                {#if frigateUrlMissing}
                    <div class="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-attention-800 dark:text-attention-200" role="status">
                        <span>{$_('settings.notifications.link_frigate_url_missing')}</span>
                        <button type="button" class="btn btn-ghost text-xs" onclick={onOpenConnection}>{$_('settings.notifications.link_open_connection', { default: 'Open Connection' })}</button>
                    </div>
                {/if}
                <div class="mt-4 grid gap-1 text-xs">
                    <div class="flex flex-wrap gap-x-3 gap-y-1">
                        <span class="font-bold text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_preview_telegram')}</span>
                        {#if linkPreview}
                            <span class="font-mono break-all text-slate-900 dark:text-white">{linkPreview}</span>
                        {:else}
                            <span class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_preview_none')}</span>
                        {/if}
                    </div>
                    <span class="text-slate-600 dark:text-slate-400">{$_('settings.notifications.link_preview_others')}</span>
                </div>
            </div>

            <!-- Species Filter -->
            <div id={speciesFilterSectionId} class="scroll-mt-24">
                <h3 class="mb-3 text-base font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter')}</h3>
                <div class="space-y-1" role="radiogroup" aria-label={$_('settings.notifications.species_filter')}>
                    <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                        <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-species-filter-mode" checked={filterSpeciesMode === 'none'} onchange={() => setSpeciesFilterMode('none')} />
                        <span class="min-w-0">
                            <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter_none')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_none_desc')}</span>
                        </span>
                    </label>
                    <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                        <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-species-filter-mode" checked={filterSpeciesMode === 'blacklist'} onchange={() => setSpeciesFilterMode('blacklist')} />
                        <span class="min-w-0">
                            <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter_blacklist')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_blacklist_desc')}</span>
                        </span>
                    </label>
                    <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-raised has-focus-visible:ring-2 has-focus-visible:ring-focus">
                        <input class="mt-1 h-4 w-4 shrink-0 accent-brand-600" type="radio" name="notification-species-filter-mode" checked={filterSpeciesMode === 'whitelist'} onchange={() => setSpeciesFilterMode('whitelist')} />
                        <span class="min-w-0">
                            <span class="block text-sm font-medium text-slate-900 dark:text-white">{$_('settings.notifications.species_filter_whitelist')}</span>
                            <span class="mt-0.5 block text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_whitelist_desc')}</span>
                        </span>
                    </label>
                </div>

                {#if filterSpeciesMode !== 'none'}
                    <div class="mt-5">
                        <label for="notification-species-search" class="block text-sm font-semibold text-slate-700 mb-2 dark:text-slate-200">{speciesFilterListTitle}</label>
                        <input
                            id="notification-species-search"
                            bind:value={speciesSearchQuery}
                            placeholder={$_('settings.notifications.species_filter_search_placeholder')}
                            aria-label={$_('settings.notifications.species_filter_search_placeholder')}
                            class="input-base w-full"
                        />
                        {#if speciesSearchLoading}
                            <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('common.loading')}</p>
                        {:else if speciesSearchError}
                            <p class="mt-2 text-xs font-bold text-red-700 dark:text-red-300">{speciesSearchError}</p>
                        {:else if speciesSearchQuery.trim().length >= 2 && speciesSearchResults.length === 0}
                            <p class="mt-2 text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.species_filter_no_results')}</p>
                        {/if}

                        {#if speciesSearchResults.length > 0}
                            <div class="mt-3 max-h-56 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950">
                                {#each speciesSearchResults as result}
                                    {@const names = getResultNames(result)}
                                    <button
                                        type="button"
                                        onclick={() => addSpeciesFilterResult(result)}
                                        class="block w-full px-4 py-3 text-left hover:bg-brand-50 dark:hover:bg-slate-800"
                                    >
                                        <span class="block text-sm font-bold text-slate-900 dark:text-white">{names.primary}</span>
                                        {#if names.secondary}
                                            <span class="block text-xs font-semibold italic text-slate-600 dark:text-slate-400">{names.secondary}</span>
                                        {/if}
                                    </button>
                                {/each}
                            </div>
                        {/if}

                        <div class="mt-4 flex flex-wrap gap-2">
                            {#each filterSpeciesEntries as entry}
                                <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-brand-200 dark:border-brand-700/50 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300">
                                    {formatBlockedSpeciesLabel(entry)}
                                    <button
                                        onclick={() => removeSpeciesFilterEntry(entry)}
                                        aria-label={$_('settings.notifications.species_filter_remove_label', { values: { species: formatBlockedSpeciesLabel(entry) } })}
                                        class="text-slate-600 dark:text-slate-400 hover:text-red-500 transition-colors"
                                    >
                                        x
                                    </button>
                                </span>
                            {/each}
                            {#if filterSpeciesEntries.length === 0 && legacySpeciesWhitelist.length === 0}
                                <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.no_species_filter')}</p>
                            {/if}
                        </div>

                        {#if filterSpeciesMode === 'whitelist' && legacySpeciesWhitelist.length > 0}
                            <div class="mt-4 border-t border-brand-200/60 pt-3 dark:border-brand-700/30">
                                <p class="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.notifications.species_filter_legacy')}</p>
                                <div class="flex flex-wrap gap-2">
                                    {#each legacySpeciesWhitelist as species}
                                        <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300">
                                            {species}
                                            <button
                                                onclick={() => removeLegacySpeciesWhitelist(species)}
                                                aria-label={$_('settings.notifications.remove_species_label', { values: { species } })}
                                                class="text-slate-600 dark:text-slate-400 hover:text-red-500 transition-colors"
                                            >
                                                x
                                            </button>
                                        </span>
                                    {/each}
                                </div>
                            </div>
                        {/if}
                    </div>
                {/if}
            </div>

    </SettingsCard>

    <!-- One surface for every channel: a row each, its switch on the right, its fields inside the row while on. -->
    <SettingsCard
        id={channelsSectionId}
        title={$_('settings.notifications.channels_title', { default: 'Channels' })}
        description={$_('settings.notifications.channels_desc', { default: 'Where alerts go. Turn a channel on to set it up.' })}
    >
        <div data-notification-channel="discord">
            <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                    <h3 id="discord-channel-label" class="text-base font-medium text-slate-900 dark:text-white">{$_('settings.discord.title')}</h3>
                    <p class="mt-1 max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.discord.desc', { default: 'Posts each alert to a Discord channel through its webhook.' })}</p>
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
                    <label for="discord-webhook" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.discord.webhook_url')}</label>
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
                    <label for="discord-botname" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.discord.bot_username')}</label>
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
                    <p id="discord-test-reason" class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.discord.test_needs', { default: 'Enter the webhook URL to send a test.' })}</p>
                {/if}
            </div>
            {/if}
        </div>

        <div data-notification-channel="pushover">
            <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                    <h3 id="pushover-channel-label" class="text-base font-medium text-slate-900 dark:text-white">{$_('settings.pushover.title')}</h3>
                    <p class="mt-1 max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.pushover.desc', { default: 'Sends each alert to your phone through the Pushover app.' })}</p>
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
                    <label for="pushover-userkey" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.pushover.user_key')}</label>
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
                    <label for="pushover-apitoken" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.pushover.api_token')}</label>
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
                    <p id="pushover-test-reason" class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.pushover.test_needs', { default: 'Enter the user key and API token to send a test.' })}</p>
                {/if}

                <AdvancedSection
                    id="notifications-pushover-advanced"
                    title={$_('settings.pushover.advanced_title', { default: 'Priority & device targeting' })}
                >
                    <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                        <label for="pushover-priority" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.pushover.priority')}</label>
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
                        <label for="pushover-device" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.pushover.device')}</label>
                        <div class="min-w-0">
                            <input
                                id="pushover-device"
                                type="text"
                                bind:value={pushoverDevice}
                                placeholder={$_('settings.pushover.device_placeholder')}
                                aria-label={$_('settings.pushover.device')}
                                class="input-base min-h-11 w-full"
                            />
                            <p class="mt-1.5 text-xs text-slate-600 dark:text-slate-400 ml-1">{$_('settings.pushover.device_hint')}</p>
                        </div>
                    </div>
                </AdvancedSection>
            </div>
            {/if}
        </div>

        <div data-notification-channel="telegram">
            <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                    <h3 id="telegram-channel-label" class="text-base font-medium text-slate-900 dark:text-white">{$_('settings.telegram.title')}</h3>
                    <p class="mt-1 max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.telegram.desc', { default: 'Sends each alert to a Telegram chat through your bot.' })}</p>
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
                    <label for="telegram-bottoken" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.telegram.bot_token')}</label>
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
                    <label for="telegram-chatid" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.telegram.chat_id')}</label>
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
                    <p id="telegram-test-reason" class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.telegram.test_needs', { default: 'Enter the bot token and chat ID to send a test.' })}</p>
                {/if}
            </div>
            {/if}
        </div>

        <div data-notification-channel="email">
            <div class="flex items-start justify-between gap-4">
                <div class="min-w-0">
                    <h3 id="email-channel-label" class="text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.title')}</h3>
                    <p class="mt-1 max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{$_('settings.email.desc', { default: 'Sends each alert by email, from Gmail, Outlook or your own mail server.' })}</p>
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
                            <h4 class="text-sm font-semibold text-slate-700 mb-1 dark:text-slate-200">{$_('settings.email.oauth_app_credentials')}</h4>
                            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.email.oauth_app_credentials_desc')}</p>
                        </div>
                        <!-- Gmail credentials -->
                        <div class="grid grid-cols-1 gap-2">
                            <div>
                                <label for="gmail-client-id" class="block text-sm font-semibold text-slate-700 mb-1 dark:text-slate-200">{$_('settings.email.gmail_client_id')}</label>
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
                                <label for="gmail-client-secret" class="block text-sm font-semibold text-slate-700 mb-1 dark:text-slate-200">{$_('settings.email.gmail_client_secret')}</label>
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
                        <div class="grid grid-cols-1 gap-2 pt-2 border-t border-slate-200 dark:border-slate-700">
                            <div>
                                <label for="outlook-client-id" class="block text-sm font-semibold text-slate-700 mb-1 dark:text-slate-200">{$_('settings.email.outlook_client_id')}</label>
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
                                <label for="outlook-client-secret" class="block text-sm font-semibold text-slate-700 mb-1 dark:text-slate-200">{$_('settings.email.outlook_client_secret')}</label>
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
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.email.oauth_desc')}</p>
                        <div class="flex gap-2">
                            <button
                                onclick={async () => {
                                    try {
                                        connectingGmail = true;
                                        const response = await initiateGmailOAuth();
                                        window.open(response.authorization_url, '_blank', 'width=600,height=700');
                                        onActionFeedback('success', $_('settings.email.connect_gmail'));
                                    } catch (error) {
                                        onActionFeedback('error', extractErrorMessage(error, $_('settings.email.test_email_error_generic')));
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
                                        onActionFeedback('error', extractErrorMessage(error, $_('settings.email.test_email_error_generic')));
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
                            <div class="flex items-center justify-between p-3 bg-success-50 dark:bg-success-900/20 rounded-xl">
                                <span class="text-sm text-success-700 dark:text-success-300">{$_('settings.email.connected', { values: { email: emailConnectedEmail } })}</span>
                                <button
                                    onclick={async () => {
                                        try {
                                            disconnectingEmailOAuth = true;
                                            await disconnectEmailOAuth((emailOAuthProvider as 'gmail' | 'outlook') || 'gmail');
                                            emailConnectedEmail = null;
                                            emailOAuthProvider = null;
                                            onActionFeedback('success', $_('settings.email.disconnect'));
                                        } catch (error) {
                                            onActionFeedback('error', extractErrorMessage(error, $_('settings.email.test_email_error_generic')));
                                        } finally {
                                            disconnectingEmailOAuth = false;
                                        }
                                    }}
                                    aria-label={$_('settings.email.disconnect')}
                                    disabled={disconnectingEmailOAuth}
                                    class="text-xs text-red-700 dark:text-red-400 hover:underline"
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
                            <label for="smtp-host" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.smtp_host')}</label>
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
                                <label for="smtp-port" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.smtp_port')}</label>
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
                                    <span id="smtp-tls-label" class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.email.smtp_use_tls')}</span>
                                    <SettingsToggle checked={emailSmtpUseTls} labelledBy="smtp-tls-label" srLabel={$_('settings.email.smtp_use_tls')} onchange={(value) => (emailSmtpUseTls = value)} />
                                </div>
                            </div>
                        </div>
                        <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                            <label for="smtp-username" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.smtp_username')}</label>
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
                            <label for="smtp-password" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.smtp_password')}</label>
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
                <div class="pt-4 border-t border-slate-200 dark:border-slate-700 space-y-3">
                    <div class="settings-row space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row>
                        <label for="email-from" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.from_email')}</label>
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
                        <label for="email-to" class="block text-base font-medium text-slate-900 dark:text-white">{$_('settings.email.to_email')}</label>
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
                                    <span id="email-include-snapshot-label" class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.email.include_snapshot')}</span>
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
                                    <span id="email-only-on-end-label" class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.email.only_on_end')}</span>
                                    <SettingsToggle checked={emailOnlyOnEnd} labelledBy="email-only-on-end-label" srLabel={$_('settings.email.only_on_end')} onchange={(value) => (emailOnlyOnEnd = value)} />
                                </div>
                        <p class="mt-1 text-xs text-slate-600 dark:text-slate-400">{$_('settings.email.only_on_end_desc')}</p>
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
                    <p id="email-test-reason" class="text-xs text-slate-600 dark:text-slate-300">{$_('settings.email.test_needs', { default: 'Enter the recipient address to send a test.' })}</p>
                {/if}
            </div>
            {/if}
        </div>
    </SettingsCard>

    {#if gardenBeta}
        <!-- Garden alerts are set with the rest of Garden; their channels are the ones set up here. -->
        <p class="px-1 text-sm text-slate-600 dark:text-slate-300" data-garden-alerts-elsewhere>
            {$_('settings.notifications.garden_elsewhere', { default: 'Garden animal alerts are set with Garden animals, in Beta features. They send through the channels above.' })}
            {#if onOpenGarden}
                <button type="button" class="focus-ring min-h-11 rounded-sm font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200" onclick={onOpenGarden}>
                    {$_('settings.notifications.garden_open', { default: 'Open Garden alerts' })}
                </button>
            {/if}
        </p>
    {/if}
</div>

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
            <span class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.notifications.test_channel', { default: 'Channel' })}</span>
            <span class="font-bold text-slate-800 dark:text-slate-100">{ntChannelLabel}</span>
        {/snippet}
    </DiagnosticDialog>
{/if}
