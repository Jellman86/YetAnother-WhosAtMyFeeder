<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import {
        fetchSettings,
        updateSettings,
        testFrigateConnection,
        fetchFrigateConfig,
        fetchClassifierStatus,
        downloadDefaultModel,
        fetchWildlifeModelStatus,
        downloadWildlifeModel,
        fetchMaintenanceStats,
        runCleanup,
        runBackfill,
        fetchCacheStats,
        runCacheCleanup,
        fetchTaxonomyStatus,
        startTaxonomySync,
        resetDatabase,
        analyzeUnknowns,
        fetchAnalysisStatus,
        testBirdWeather,
        testBirdNET,
        testMQTTPublish,
        testNotification,
        fetchVersion,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        sendTestEmail,
        type ClassifierStatus,
        type WildlifeModelStatus,
        type MaintenanceStats,
        type BackfillResult,
        type CacheStats,
        type CacheCleanupResult,
        type TaxonomySyncStatus,
        type VersionInfo
    } from '../api';
    import { themeStore, theme, type Theme } from '../stores/theme.svelte';
    import { layoutStore, layout, type Layout } from '../stores/layout.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { _, locale } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import SettingsTabs from '../components/settings/SettingsTabs.svelte';

    // Import all 7 settings components
    import AccessibilitySettings from '../components/settings/AccessibilitySettings.svelte';
    import AppearanceSettings from '../components/settings/AppearanceSettings.svelte';
    import ConnectionSettings from '../components/settings/ConnectionSettings.svelte';
    import DetectionSettings from '../components/settings/DetectionSettings.svelte';
    import DataSettings from '../components/settings/DataSettings.svelte';
    import IntegrationSettings from '../components/settings/IntegrationSettings.svelte';
    import NotificationSettings from '../components/settings/NotificationSettings.svelte';
    import AuthenticationSettings from '../components/settings/AuthenticationSettings.svelte';

    let frigateUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let mqttAuth = $state(false);
    let mqttUsername = $state('');
    let mqttPassword = $state('');
    let audioTopic = $state('birdnet/text');
    let cameraAudioMapping = $state<Record<string, string>>({});
    let audioBufferHours = $state(24);
    let audioCorrelationWindowSeconds = $state(300);
    let clipsEnabled = $state(true);
    let threshold = $state(0.7);
    let minConfidence = $state(0.4);
    let trustFrigateSublabel = $state(true);
    let displayCommonNames = $state(true);
    let scientificNamePrimary = $state(false);
    let autoVideoClassification = $state(false);
    let videoClassificationDelay = $state(30);
    let videoClassificationMaxRetries = $state(3);
    let videoCircuitOpen = $state(false);
    let videoCircuitUntil = $state<string | null>(null);
    let videoCircuitFailures = $state(0);
    let selectedCameras = $state<string[]>([]);
    let retentionDays = $state(0);
    let blockedLabels = $state<string[]>([]);
    let newBlockedLabel = $state('');

    // Taxonomy Sync State
    let taxonomyStatus = $state<TaxonomySyncStatus | null>(null);
    let syncingTaxonomy = $state(false);
    let taxonomyPollInterval: any;

    // Location Settings
    let locationLat = $state<number | null>(null);
    let locationLon = $state<number | null>(null);
    let locationAuto = $state(true);
    let locationTemperatureUnit = $state<'celsius' | 'fahrenheit'>('celsius');

    // BirdNET-Go Settings
    let birdnetEnabled = $state(true);

    // BirdWeather Settings
    let birdweatherEnabled = $state(false);
    let birdweatherStationToken = $state('');

    // LLM Settings
    let llmEnabled = $state(false);
    let llmProvider = $state('gemini');
    let llmApiKey = $state('');
    let llmModel = $state('gemini-3-flash-preview');

    // Available models per provider (Updated January 2026)
    const modelsByProvider = {
        gemini: [
            { value: 'gemini-3-pro-preview', label: 'Gemini 3 Pro (Latest, Most Capable)' },
            { value: 'gemini-3-flash-preview', label: 'Gemini 3 Flash (Latest, Fast & Affordable)' },
            { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
            { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite (Lightweight)' },
            { value: 'gemini-2.0-flash-exp', label: 'Gemini 2.0 Flash Exp (Legacy, retiring March 2026)' }
        ],
        openai: [
            { value: 'gpt-5.2-pro', label: 'GPT-5.2 Pro (Latest, Most Advanced)' },
            { value: 'gpt-5.2-thinking', label: 'GPT-5.2 Thinking (Advanced Reasoning)' },
            { value: 'gpt-5.2-instant', label: 'GPT-5.2 Instant (Fast)' },
            { value: 'gpt-4o', label: 'GPT-4o (Previous Generation)' },
            { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Lightweight)' }
        ],
        claude: [
            { value: 'claude-opus-4-5', label: 'Claude Opus 4.5 (Latest, Most Intelligent)' },
            { value: 'claude-sonnet-4-5-20250929', label: 'Claude Sonnet 4.5 (Balanced)' },
            { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5 (Fastest & Most Affordable)' },
            { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Legacy)' },
            { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku (Legacy)' }
        ]
    };

    // Get models for current provider
    let availableModels = $derived(modelsByProvider[llmProvider as keyof typeof modelsByProvider] || []);

    // Update model to first available when provider changes
    $effect(() => {
        const models = modelsByProvider[llmProvider as keyof typeof modelsByProvider];
        if (models && models.length > 0) {
            // Check if current model is valid for new provider
            const isValidModel = models.some(m => m.value === llmModel);
            if (!isValidModel) {
                llmModel = models[0].value;
            }
        }
    });

    // Telemetry
    let telemetryEnabled = $state(true);
    let telemetryInstallationId = $state<string | undefined>(undefined);
    let telemetryPlatform = $state<string | undefined>(undefined);

    // Authentication + Public Access
    let authEnabled = $state(false);
    let authUsername = $state('admin');
    let authHasPassword = $state(false);
    let authPassword = $state('');
    let authPasswordConfirm = $state('');
    let authSessionExpiryHours = $state(168);
    let trustedProxyHosts = $state<string[]>([]);
    let trustedProxyHostsSuggested = $state(false);
    let newTrustedProxyHost = $state('');
    let publicAccessEnabled = $state(false);
    let publicAccessShowCameraNames = $state(true);
    let publicAccessHistoricalDays = $state(7);
    let publicAccessRateLimitPerMinute = $state(30);

    // Notifications
    let discordEnabled = $state(false);
    let discordWebhook = $state('');
    let discordWebhookSaved = $state(false);
    let discordUsername = $state('YA-WAMF');

    let pushoverEnabled = $state(false);
    let pushoverUser = $state('');
    let pushoverUserSaved = $state(false);
    let pushoverToken = $state('');
    let pushoverTokenSaved = $state(false);
    let pushoverPriority = $state(0);

    let telegramEnabled = $state(false);
    let telegramToken = $state('');
    let telegramTokenSaved = $state(false);
    let telegramChatId = $state('');
    let telegramChatIdSaved = $state(false);

    let emailEnabled = $state(false);
    let emailUseOAuth = $state(false);
    let emailOAuthProvider = $state<string | null>(null);
    let emailConnectedEmail = $state<string | null>(null);
    let emailSmtpHost = $state('');
    let emailSmtpPort = $state(587);
    let emailSmtpUsername = $state('');
    let emailSmtpPassword = $state('');
    let emailSmtpPasswordSaved = $state(false);
    let emailSmtpUseTls = $state(true);
    let emailFromEmail = $state('');
    let emailToEmail = $state('');
    let emailIncludeSnapshot = $state(true);
    let emailDashboardUrl = $state('');

    let filterWhitelist = $state<string[]>([]);
    let newWhitelistSpecies = $state('');
    let filterConfidence = $state(0.7);
    let filterAudioOnly = $state(false);
    let notifyOnInsert = $state(true);
    let notifyOnUpdate = $state(false);
    let notifyDelayUntilVideo = $state(false);
    let notifyVideoFallbackTimeout = $state(45);

    let testingNotification = $state<Record<string, boolean>>({});

    // Accessibility
    let highContrast = $state(false);
    let dyslexiaFont = $state(false);
    let liveAnnouncements = $state(true);
    let speciesInfoSource = $state('auto');

    $effect(() => {
        if (highContrast) document.documentElement.classList.add('high-contrast');
        else document.documentElement.classList.remove('high-contrast');
    });

    function addTrustedProxyHost() {
        const host = newTrustedProxyHost.trim();
        if (!host) return;
        if (trustedProxyHostsSuggested) {
            trustedProxyHostsSuggested = false;
        }
        if (!trustedProxyHosts.includes(host)) {
            trustedProxyHosts = [...trustedProxyHosts, host];
        }
        newTrustedProxyHost = '';
    }

    function removeTrustedProxyHost(host: string) {
        if (trustedProxyHostsSuggested) {
            trustedProxyHostsSuggested = false;
        }
        trustedProxyHosts = trustedProxyHosts.filter((item) => item !== host);
    }

    function acceptTrustedProxySuggestions() {
        trustedProxyHostsSuggested = false;
    }

    const effectiveTrustedProxyHosts = $derived.by(() => {
        return trustedProxyHostsSuggested ? ['*'] : trustedProxyHosts;
    });

    $effect(() => {
        if (dyslexiaFont) document.documentElement.classList.add('font-dyslexic');
        else document.documentElement.classList.remove('font-dyslexic');
    });

    $effect(() => {
        if (discordWebhookSaved && discordWebhook) {
            discordWebhookSaved = false;
        }
    });

    $effect(() => {
        if (pushoverUserSaved && pushoverUser) {
            pushoverUserSaved = false;
        }
    });

    $effect(() => {
        if (pushoverTokenSaved && pushoverToken) {
            pushoverTokenSaved = false;
        }
    });

    $effect(() => {
        if (telegramTokenSaved && telegramToken) {
            telegramTokenSaved = false;
        }
    });

    $effect(() => {
        if (telegramChatIdSaved && telegramChatId) {
            telegramChatIdSaved = false;
        }
    });

    $effect(() => {
        if (emailSmtpPasswordSaved && emailSmtpPassword) {
            emailSmtpPasswordSaved = false;
        }
    });

    // Version Info
    const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
    const appVersionBase = appVersion.includes('+') ? appVersion.split('+')[0] : appVersion;
    let versionInfo = $state<VersionInfo>({
        version: appVersion,
        base_version: appVersionBase,
        git_hash: __GIT_HASH__
    });

    let availableCameras = $state<string[]>([]);
    let camerasLoading = $state(false);

    let loading = $state(true);
    let saving = $state(false);
    let testing = $state(false);
    let testingBirdWeather = $state(false);
    let testingBirdNET = $state(false);
    let message = $state<{ type: 'success' | 'error'; text: string } | null>(null);
    let currentTheme: Theme = $state('system');
    let currentLayout: Layout = $state('horizontal');

    const normalizeSecret = (value?: string | null) => value === '***REDACTED***' ? '' : (value || '');

    // Dirty state check
    let isDirty = $derived.by(() => {
        const s = settingsStore.settings;
        if (!s) {
            console.log('isDirty: settingsStore.settings is null');
            return false;
        }

        const checks = [
            { key: 'frigateUrl', val: frigateUrl, store: s.frigate_url },
            { key: 'mqttServer', val: mqttServer, store: s.mqtt_server },
            { key: 'mqttPort', val: mqttPort, store: s.mqtt_port },
            { key: 'mqttAuth', val: mqttAuth, store: s.mqtt_auth },
            { key: 'mqttUsername', val: mqttUsername, store: s.mqtt_username || '' },
            { key: 'mqttPassword', val: mqttPassword, store: s.mqtt_password || '' },
            { key: 'audioTopic', val: audioTopic, store: s.audio_topic || 'birdnet/text' },
            { key: 'audioBufferHours', val: audioBufferHours, store: s.audio_buffer_hours ?? 24 },
            { key: 'audioCorrelationWindowSeconds', val: audioCorrelationWindowSeconds, store: s.audio_correlation_window_seconds ?? 300 },
            { key: 'birdnetEnabled', val: birdnetEnabled, store: s.birdnet_enabled ?? true },
            { key: 'clipsEnabled', val: clipsEnabled, store: s.clips_enabled ?? true },
            { key: 'threshold', val: threshold, store: s.classification_threshold },
            { key: 'trustFrigateSublabel', val: trustFrigateSublabel, store: s.trust_frigate_sublabel ?? true },
            { key: 'displayCommonNames', val: displayCommonNames, store: s.display_common_names ?? true },
            { key: 'scientificNamePrimary', val: scientificNamePrimary, store: s.scientific_name_primary ?? false },
            { key: 'autoVideoClassification', val: autoVideoClassification, store: s.auto_video_classification ?? false },
            { key: 'videoClassificationDelay', val: videoClassificationDelay, store: s.video_classification_delay ?? 30 },
            { key: 'videoClassificationMaxRetries', val: videoClassificationMaxRetries, store: s.video_classification_max_retries ?? 3 },
            { key: 'selectedCameras', val: JSON.stringify(selectedCameras), store: JSON.stringify(s.cameras || []) },
            { key: 'retentionDays', val: retentionDays, store: s.retention_days || 0 },
            { key: 'blockedLabels', val: JSON.stringify(blockedLabels), store: JSON.stringify(s.blocked_labels || []) },
            { key: 'cacheEnabled', val: cacheEnabled, store: s.media_cache_enabled ?? true },
            { key: 'cacheSnapshots', val: cacheSnapshots, store: s.media_cache_snapshots ?? true },
            { key: 'cacheClips', val: cacheClips, store: s.media_cache_clips ?? true },
            { key: 'cacheRetentionDays', val: cacheRetentionDays, store: s.media_cache_retention_days ?? 0 },
            { key: 'locationLat', val: locationLat, store: s.location_latitude ?? null },
            { key: 'locationLon', val: locationLon, store: s.location_longitude ?? null },
            { key: 'locationAuto', val: locationAuto, store: s.location_automatic ?? true },
            { key: 'locationTemperatureUnit', val: locationTemperatureUnit, store: s.location_temperature_unit ?? 'celsius' },
            { key: 'birdweatherEnabled', val: birdweatherEnabled, store: s.birdweather_enabled ?? false },
            { key: 'birdweatherStationToken', val: birdweatherStationToken, store: s.birdweather_station_token || '' },
            { key: 'llmEnabled', val: llmEnabled, store: s.llm_enabled ?? false },
            { key: 'llmProvider', val: llmProvider, store: s.llm_provider ?? 'gemini' },
            { key: 'llmApiKey', val: llmApiKey, store: s.llm_api_key || '' },
            { key: 'llmModel', val: llmModel, store: s.llm_model ?? 'gemini-3-flash-preview' },
            { key: 'cameraAudioMapping', val: JSON.stringify(cameraAudioMapping), store: JSON.stringify(s.camera_audio_mapping || {}) },
            { key: 'minConfidence', val: minConfidence, store: s.classification_min_confidence ?? 0.4 },
            { key: 'telemetryEnabled', val: telemetryEnabled, store: s.telemetry_enabled ?? true },
            { key: 'authEnabled', val: authEnabled, store: s.auth_enabled ?? false },
            { key: 'authUsername', val: authUsername, store: s.auth_username || 'admin' },
            { key: 'authSessionExpiryHours', val: authSessionExpiryHours, store: s.auth_session_expiry_hours ?? 168 },
            { key: 'trustedProxyHosts', val: JSON.stringify(effectiveTrustedProxyHosts), store: JSON.stringify(s.trusted_proxy_hosts || []) },
            { key: 'publicAccessEnabled', val: publicAccessEnabled, store: s.public_access_enabled ?? false },
            { key: 'publicAccessShowCameraNames', val: publicAccessShowCameraNames, store: s.public_access_show_camera_names ?? true },
            { key: 'publicAccessHistoricalDays', val: publicAccessHistoricalDays, store: s.public_access_historical_days ?? 7 },
            { key: 'publicAccessRateLimitPerMinute', val: publicAccessRateLimitPerMinute, store: s.public_access_rate_limit_per_minute ?? 30 },

            // Notifications
            { key: 'discordEnabled', val: discordEnabled, store: s.notifications_discord_enabled ?? false },
            { key: 'discordWebhook', val: discordWebhook, store: normalizeSecret(s.notifications_discord_webhook_url) },
            { key: 'discordUsername', val: discordUsername, store: s.notifications_discord_username || 'YA-WAMF' },

            { key: 'pushoverEnabled', val: pushoverEnabled, store: s.notifications_pushover_enabled ?? false },
            { key: 'pushoverUser', val: pushoverUser, store: normalizeSecret(s.notifications_pushover_user_key) },
            { key: 'pushoverToken', val: pushoverToken, store: normalizeSecret(s.notifications_pushover_api_token) },
            { key: 'pushoverPriority', val: pushoverPriority, store: s.notifications_pushover_priority ?? 0 },

            { key: 'telegramEnabled', val: telegramEnabled, store: s.notifications_telegram_enabled ?? false },
            { key: 'telegramToken', val: telegramToken, store: normalizeSecret(s.notifications_telegram_bot_token) },
            { key: 'telegramChatId', val: telegramChatId, store: normalizeSecret(s.notifications_telegram_chat_id) },

            { key: 'emailEnabled', val: emailEnabled, store: s.notifications_email_enabled ?? false },
            { key: 'emailUseOAuth', val: emailUseOAuth, store: s.notifications_email_use_oauth ?? false },
            { key: 'emailOAuthProvider', val: emailOAuthProvider || '', store: s.notifications_email_oauth_provider || '' },
            { key: 'emailSmtpHost', val: emailSmtpHost, store: s.notifications_email_smtp_host || '' },
            { key: 'emailSmtpPort', val: emailSmtpPort, store: s.notifications_email_smtp_port ?? 587 },
            { key: 'emailSmtpUsername', val: emailSmtpUsername, store: s.notifications_email_smtp_username || '' },
            { key: 'emailSmtpPassword', val: emailSmtpPassword, store: normalizeSecret(s.notifications_email_smtp_password) },
            { key: 'emailSmtpUseTls', val: emailSmtpUseTls, store: s.notifications_email_smtp_use_tls ?? true },
            { key: 'emailFromEmail', val: emailFromEmail, store: s.notifications_email_from_email || '' },
            { key: 'emailToEmail', val: emailToEmail, store: s.notifications_email_to_email || '' },
            { key: 'emailIncludeSnapshot', val: emailIncludeSnapshot, store: s.notifications_email_include_snapshot ?? true },
            { key: 'emailDashboardUrl', val: emailDashboardUrl, store: s.notifications_email_dashboard_url || '' },

            { key: 'filterWhitelist', val: JSON.stringify(filterWhitelist), store: JSON.stringify(s.notifications_filter_species_whitelist || []) },
            { key: 'filterConfidence', val: filterConfidence, store: s.notifications_filter_min_confidence ?? 0.7 },
            { key: 'filterAudioOnly', val: filterAudioOnly, store: s.notifications_filter_audio_confirmed_only ?? false },
            { key: 'notifyOnInsert', val: notifyOnInsert, store: s.notifications_notify_on_insert ?? true },
            { key: 'notifyOnUpdate', val: notifyOnUpdate, store: s.notifications_notify_on_update ?? false },
            { key: 'notifyDelayUntilVideo', val: notifyDelayUntilVideo, store: s.notifications_delay_until_video ?? false },
            { key: 'notifyVideoFallbackTimeout', val: notifyVideoFallbackTimeout, store: s.notifications_video_fallback_timeout ?? 45 },

            // Accessibility
            { key: 'highContrast', val: highContrast, store: s.accessibility_high_contrast ?? false },
            { key: 'dyslexiaFont', val: dyslexiaFont, store: s.accessibility_dyslexia_font ?? false },
            { key: 'liveAnnouncements', val: liveAnnouncements, store: s.accessibility_live_announcements ?? true },
            { key: 'speciesInfoSource', val: speciesInfoSource, store: s.species_info_source ?? 'auto' }
        ];

        if (authPassword.length > 0 || authPasswordConfirm.length > 0) {
            return true;
        }

        const dirtyItem = checks.find(c => c.val !== c.store);
        if (dirtyItem) {
            console.log(`Dirty Setting: ${dirtyItem.key}`, { current: dirtyItem.val, saved: dirtyItem.store });
            return true;
        } else {
            // console.log('isDirty: No changes detected');
        }
        return false;
    });

    let classifierStatus = $state<ClassifierStatus | null>(null);
    let downloadingModel = $state(false);

    let wildlifeStatus = $state<WildlifeModelStatus | null>(null);
    let downloadingWildlifeModel = $state(false);

    let maintenanceStats = $state<MaintenanceStats | null>(null);
    let cleaningUp = $state(false);

    // Media cache state
    let cacheEnabled = $state(true);
    let cacheSnapshots = $state(true);
    let cacheClips = $state(true);
    let cacheRetentionDays = $state(0);
    let cacheStats = $state<CacheStats | null>(null);
    let cleaningCache = $state(false);

    // Backfill state
    let backfillDateRange = $state<'day' | 'week' | 'month' | 'custom'>('week');
    let backfillStartDate = $state('');
    let backfillEndDate = $state('');
    let backfilling = $state(false);
    let backfillResult = $state<BackfillResult | null>(null);
    let resettingDatabase = $state(false);
    let analyzingUnknowns = $state(false);
    let analysisTotal = $state(0);
    let analysisStatus = $state<{ pending: number; active: number; circuit_open: boolean } | null>(null);
    let analysisPollInterval: any;

    // Tab navigation
    let activeTab = $state('connection');

    theme.subscribe(t => currentTheme = t);
    layout.subscribe(l => currentLayout = l);

    onMount(async () => {
        // Handle deep linking to tabs
        const hash = window.location.hash.slice(1);
        if (hash && ['connection', 'detection', 'notifications', 'integrations', 'security', 'data', 'appearance', 'accessibility'].includes(hash)) {
            activeTab = hash;
        }

        // Ensure settings store is loaded for dirty checking
        await settingsStore.load();

        await Promise.all([
            loadSettings(),
            loadCameras(),
            loadClassifierStatus(),
            loadWildlifeStatus(),
            loadMaintenanceStats(),
            loadCacheStats(),
            loadTaxonomyStatus(),
            loadVersion(),
            loadAnalysisStatus() // Check if there's an ongoing job
        ]);

        taxonomyPollInterval = setInterval(loadTaxonomyStatus, 3000);
        
        // If there are pending/active items on load, start polling
        if (analysisStatus && (analysisStatus.pending > 0 || analysisStatus.active > 0)) {
             startAnalysisPolling();
             // We don't know total if we just reloaded, so maybe set total to pending+active
             if (analysisTotal === 0) {
                 analysisTotal = analysisStatus.pending + analysisStatus.active;
             }
        }
    });

    function handleTabChange(tab: string) {
        console.log('Tab changed to:', tab);
        activeTab = tab;
        window.location.hash = tab;
    }

    onDestroy(() => {
        if (taxonomyPollInterval) clearInterval(taxonomyPollInterval);
        if (analysisPollInterval) clearInterval(analysisPollInterval);
    });

    async function loadTaxonomyStatus() {
        try {
            taxonomyStatus = await fetchTaxonomyStatus();
        } catch (e) {
            console.error('Failed to load taxonomy status', e);
        }
    }

    async function loadVersion() {
        try {
            versionInfo = await fetchVersion();
        } catch (e) {
            console.error('Failed to load version info', e);
        }
    }

    async function handleStartTaxonomySync() {
        if (taxonomyStatus?.is_running) return;
        syncingTaxonomy = true;
        try {
            await startTaxonomySync();
            await loadTaxonomyStatus();
        } catch (e: any) {
            alert('Failed to start taxonomy sync: ' + e.message);
        } finally {
            syncingTaxonomy = false;
        }
    }

    async function loadMaintenanceStats() {
        try {
            maintenanceStats = await fetchMaintenanceStats();
        } catch (e) {
            console.error('Failed to load maintenance stats', e);
        }
    }

    async function handleCleanup() {
        cleaningUp = true;
        message = null;
        try {
            const result = await runCleanup();
            if (result.status === 'completed') {
                message = { type: 'success', text: `Cleanup complete! Deleted ${result.deleted_count} old detections.` };
            } else {
                message = { type: 'success', text: result.message || 'No cleanup needed.' };
            }
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Cleanup failed' };
        } finally {
            cleaningUp = false;
        }
    }

    async function handleResetDatabase() {
        console.log('Reset database requested');
        let confirmMsg = 'DANGER: This will delete ALL detections and clear the media cache. This action cannot be undone. Are you sure?';
        try {
            const t = get(_);
            confirmMsg = t('settings.danger.confirm');
        } catch (e) {
            console.warn('Translation lookup failed, using fallback', e);
        }

        if (!confirm(confirmMsg)) {
            console.log('Reset cancelled by user');
            return;
        }
        
        console.log('Reset confirmed, proceeding...');
        resettingDatabase = true;
        message = null;
        toastStore.show($_('settings.danger.resetting'), 'info');
        try {
            const result = await resetDatabase();
            message = { type: 'success', text: result.message };
            toastStore.success(result.message || $_('settings.danger.reset_button'));
            await Promise.all([loadMaintenanceStats(), loadCacheStats()]);
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Database reset failed' };
            toastStore.error(e.message || 'Database reset failed');
        } finally {
            resettingDatabase = false;
        }
    }

    async function loadCacheStats() {
        try {
            cacheStats = await fetchCacheStats();
        } catch (e) {
            console.error('Failed to load cache stats', e);
        }
    }

    async function handleCacheCleanup() {
        cleaningCache = true;
        message = null;
        try {
            const result = await runCacheCleanup();
            if (result.status === 'completed') {
                const freed = result.bytes_freed > 1024 * 1024
                    ? `${(result.bytes_freed / (1024 * 1024)).toFixed(1)} MB`
                    : `${(result.bytes_freed / 1024).toFixed(1)} KB`;
                message = { type: 'success', text: `Cache cleanup complete! Deleted ${result.snapshots_deleted} snapshots, ${result.clips_deleted} clips (${freed} freed).` };
            } else {
                message = { type: 'success', text: result.message || 'No cleanup needed.' };
            }
            await loadCacheStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Cache cleanup failed' };
        } finally {
            cleaningCache = false;
        }
    }

    async function handleBackfill() {
        backfilling = true;
        message = null;
        backfillResult = null;
        try {
            const result = await runBackfill({
                date_range: backfillDateRange,
                start_date: backfillDateRange === 'custom' ? backfillStartDate : undefined,
                end_date: backfillDateRange === 'custom' ? backfillEndDate : undefined
            });
            backfillResult = result;
            message = { type: 'success', text: result.message };
            await loadMaintenanceStats();
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Backfill failed' };
        } finally {
            backfilling = false;
        }
    }

    async function handleAnalyzeUnknowns() {
        analyzingUnknowns = true;
        message = null;
        try {
            const result = await analyzeUnknowns();
            message = { type: 'success', text: result.message };
            if (result.count > 0) {
                analysisTotal = result.count;
                startAnalysisPolling();
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Analysis failed' };
        } finally {
            analyzingUnknowns = false;
        }
    }

    function startAnalysisPolling() {
        if (analysisPollInterval) clearInterval(analysisPollInterval);
        loadAnalysisStatus();
        analysisPollInterval = setInterval(loadAnalysisStatus, 2000);
    }

    async function loadAnalysisStatus() {
        try {
            const status = await fetchAnalysisStatus();
            analysisStatus = status;
            if (status.pending === 0 && status.active === 0) {
                if (analysisPollInterval) {
                    clearInterval(analysisPollInterval);
                    analysisPollInterval = null;
                }
            }
        } catch (e) {
            console.error('Failed to load analysis status', e);
        }
    }

    async function loadClassifierStatus() {
        try {
            classifierStatus = await fetchClassifierStatus();
        } catch (e) {
            console.error('Failed to load classifier status', e);
        }
    }

    async function loadWildlifeStatus() {
        try {
            wildlifeStatus = await fetchWildlifeModelStatus();
        } catch (e) {
            console.error('Failed to load wildlife status', e);
        }
    }

    async function handleDownloadWildlifeModel() {
        downloadingWildlifeModel = true;
        message = null;
        try {
            const result = await downloadWildlifeModel();
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
                await loadWildlifeStatus();
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to download wildlife model' };
        } finally {
            downloadingWildlifeModel = false;
        }
    }

    async function loadSettings(silent = false) {
        if (!silent) loading = true;
        if (!silent) message = null;
        try {
            const settings = await fetchSettings();
            frigateUrl = settings.frigate_url;
            mqttServer = settings.mqtt_server;
            mqttPort = settings.mqtt_port;
            mqttAuth = settings.mqtt_auth;
            mqttUsername = settings.mqtt_username || '';
            mqttPassword = settings.mqtt_password || '';
            birdnetEnabled = settings.birdnet_enabled ?? true;
            audioTopic = settings.audio_topic || 'birdnet/text';
            cameraAudioMapping = settings.camera_audio_mapping || {};
            if (typeof cameraAudioMapping !== 'object' || Array.isArray(cameraAudioMapping)) {
                cameraAudioMapping = {};
            }
            audioBufferHours = settings.audio_buffer_hours ?? 24;
            audioCorrelationWindowSeconds = settings.audio_correlation_window_seconds ?? 300;
            clipsEnabled = settings.clips_enabled ?? true;
            threshold = settings.classification_threshold;
            minConfidence = settings.classification_min_confidence ?? 0.4;
            trustFrigateSublabel = settings.trust_frigate_sublabel ?? true;
            displayCommonNames = settings.display_common_names ?? true;
            scientificNamePrimary = settings.scientific_name_primary ?? false;
            autoVideoClassification = settings.auto_video_classification ?? false;
            videoClassificationDelay = settings.video_classification_delay ?? 30;
            videoClassificationMaxRetries = settings.video_classification_max_retries ?? 3;
            videoCircuitOpen = settings.video_classification_circuit_open ?? false;
            videoCircuitUntil = settings.video_classification_circuit_until ?? null;
            videoCircuitFailures = settings.video_classification_circuit_failures ?? 0;
            selectedCameras = settings.cameras || [];
            retentionDays = settings.retention_days || 0;
            blockedLabels = settings.blocked_labels || [];
            // Media cache settings
            cacheEnabled = settings.media_cache_enabled ?? true;
            cacheSnapshots = settings.media_cache_snapshots ?? true;
            cacheClips = settings.media_cache_clips ?? true;
            cacheRetentionDays = settings.media_cache_retention_days ?? 0;
            // Location settings
            locationLat = settings.location_latitude ?? null;
            locationLon = settings.location_longitude ?? null;
            locationAuto = settings.location_automatic ?? true;
            locationTemperatureUnit = settings.location_temperature_unit ?? 'celsius';
            // BirdWeather settings
            birdweatherEnabled = settings.birdweather_enabled ?? false;
            birdweatherStationToken = settings.birdweather_station_token ?? '';
            // LLM settings
            llmEnabled = settings.llm_enabled ?? false;
            llmProvider = settings.llm_provider ?? 'gemini';
            llmApiKey = settings.llm_api_key ?? '';
            llmModel = settings.llm_model ?? 'gemini-3-flash-preview';
            // Telemetry
            telemetryEnabled = settings.telemetry_enabled ?? true;
            telemetryInstallationId = settings.telemetry_installation_id;
            telemetryPlatform = settings.telemetry_platform;
            // Authentication + Public access
            authEnabled = settings.auth_enabled ?? false;
            authUsername = settings.auth_username || 'admin';
            authHasPassword = settings.auth_has_password ?? false;
            authPassword = '';
            authPasswordConfirm = '';
            authSessionExpiryHours = settings.auth_session_expiry_hours ?? 168;
            const proxyHosts = settings.trusted_proxy_hosts || [];
            const proxyHostsDefault = proxyHosts.length === 0 || (proxyHosts.length === 1 && proxyHosts[0] === '*');
            trustedProxyHostsSuggested = proxyHostsDefault;
            trustedProxyHosts = proxyHostsDefault ? ['nginx-rp', 'cloudflare-tunnel'] : proxyHosts;
            publicAccessEnabled = settings.public_access_enabled ?? false;
            publicAccessShowCameraNames = settings.public_access_show_camera_names ?? true;
            publicAccessHistoricalDays = settings.public_access_historical_days ?? 7;
            publicAccessRateLimitPerMinute = settings.public_access_rate_limit_per_minute ?? 30;

            // Notifications
            discordEnabled = settings.notifications_discord_enabled ?? false;
            if (settings.notifications_discord_webhook_url === '***REDACTED***') {
                discordWebhookSaved = true;
                discordWebhook = '';
            } else {
                discordWebhookSaved = false;
                discordWebhook = settings.notifications_discord_webhook_url || '';
            }
            discordUsername = settings.notifications_discord_username || 'YA-WAMF';

            pushoverEnabled = settings.notifications_pushover_enabled ?? false;
            if (settings.notifications_pushover_user_key === '***REDACTED***') {
                pushoverUserSaved = true;
                pushoverUser = '';
            } else {
                pushoverUserSaved = false;
                pushoverUser = settings.notifications_pushover_user_key || '';
            }
            if (settings.notifications_pushover_api_token === '***REDACTED***') {
                pushoverTokenSaved = true;
                pushoverToken = '';
            } else {
                pushoverTokenSaved = false;
                pushoverToken = settings.notifications_pushover_api_token || '';
            }
            pushoverPriority = settings.notifications_pushover_priority ?? 0;

            telegramEnabled = settings.notifications_telegram_enabled ?? false;
            if (settings.notifications_telegram_bot_token === '***REDACTED***') {
                telegramTokenSaved = true;
                telegramToken = '';
            } else {
                telegramTokenSaved = false;
                telegramToken = settings.notifications_telegram_bot_token || '';
            }
            if (settings.notifications_telegram_chat_id === '***REDACTED***') {
                telegramChatIdSaved = true;
                telegramChatId = '';
            } else {
                telegramChatIdSaved = false;
                telegramChatId = settings.notifications_telegram_chat_id || '';
            }

            emailEnabled = settings.notifications_email_enabled ?? false;
            emailUseOAuth = settings.notifications_email_use_oauth ?? false;
            emailOAuthProvider = settings.notifications_email_oauth_provider || null;
            emailConnectedEmail = settings.notifications_email_connected_email || null;
            emailSmtpHost = settings.notifications_email_smtp_host || '';
            emailSmtpPort = settings.notifications_email_smtp_port ?? 587;
            emailSmtpUsername = settings.notifications_email_smtp_username || '';
            if (settings.notifications_email_smtp_password === '***REDACTED***') {
                emailSmtpPasswordSaved = true;
                emailSmtpPassword = '';
            } else {
                emailSmtpPasswordSaved = false;
                emailSmtpPassword = settings.notifications_email_smtp_password || '';
            }
            emailSmtpUseTls = settings.notifications_email_smtp_use_tls ?? true;
            emailFromEmail = settings.notifications_email_from_email || '';
            emailToEmail = settings.notifications_email_to_email || '';
            emailIncludeSnapshot = settings.notifications_email_include_snapshot ?? true;
            emailDashboardUrl = settings.notifications_email_dashboard_url || '';

            filterWhitelist = settings.notifications_filter_species_whitelist || [];
            filterConfidence = settings.notifications_filter_min_confidence ?? 0.7;
            filterAudioOnly = settings.notifications_filter_audio_confirmed_only ?? false;
            notifyOnInsert = settings.notifications_notify_on_insert ?? true;
            notifyOnUpdate = settings.notifications_notify_on_update ?? false;
            notifyDelayUntilVideo = settings.notifications_delay_until_video ?? false;
            notifyVideoFallbackTimeout = settings.notifications_video_fallback_timeout ?? 45;

            // Accessibility
            highContrast = settings.accessibility_high_contrast ?? false;
            dyslexiaFont = settings.accessibility_dyslexia_font ?? false;
            liveAnnouncements = settings.accessibility_live_announcements ?? true;
            speciesInfoSource = settings.species_info_source ?? 'auto';
        } catch (e) {
            message = { type: 'error', text: $_('notifications.settings_load_failed') };
        } finally {
            if (!silent) loading = false;
        }
    }

    async function loadCameras() {
        camerasLoading = true;
        try {
            const config = await fetchFrigateConfig();
            if (config && config.cameras) {
                availableCameras = Object.keys(config.cameras);
            }
        } catch (e) {
            console.error('Failed to load cameras from Frigate', e);
            if (selectedCameras.length > 0 && availableCameras.length === 0) {
                 availableCameras = [...selectedCameras];
            }
        } finally {
            camerasLoading = false;
        }
    }

    async function saveSettings() {
        saving = true;
        message = null;
        if (authPassword || authPasswordConfirm) {
            if (authPassword !== authPasswordConfirm) {
                message = { type: 'error', text: 'Passwords do not match' };
                saving = false;
                return;
            }
            if (authPassword.length < 8) {
                message = { type: 'error', text: 'Password must be at least 8 characters' };
                saving = false;
                return;
            }
        }
        try {
            await updateSettings({
                frigate_url: frigateUrl,
                mqtt_server: mqttServer,
                mqtt_port: mqttPort,
                mqtt_auth: mqttAuth,
                mqtt_username: mqttUsername,
                mqtt_password: mqttPassword,
                birdnet_enabled: birdnetEnabled,
                audio_topic: audioTopic,
                camera_audio_mapping: cameraAudioMapping,
                audio_buffer_hours: audioBufferHours,
                audio_correlation_window_seconds: audioCorrelationWindowSeconds,
                clips_enabled: clipsEnabled,
                classification_threshold: threshold,
                classification_min_confidence: minConfidence,
                trust_frigate_sublabel: trustFrigateSublabel,
                display_common_names: displayCommonNames,
                scientific_name_primary: scientificNamePrimary,
                auto_video_classification: autoVideoClassification,
                video_classification_delay: videoClassificationDelay,
                video_classification_max_retries: videoClassificationMaxRetries,
                cameras: selectedCameras,
                retention_days: retentionDays,
                blocked_labels: blockedLabels,
                media_cache_enabled: cacheEnabled,
                media_cache_snapshots: cacheSnapshots,
                media_cache_clips: cacheClips,
                media_cache_retention_days: cacheRetentionDays,
                location_latitude: locationLat,
                location_longitude: locationLon,
                location_automatic: locationAuto,
                location_temperature_unit: locationTemperatureUnit,
                birdweather_enabled: birdweatherEnabled,
                birdweather_station_token: birdweatherStationToken,
                llm_enabled: llmEnabled,
                llm_provider: llmProvider,
                llm_api_key: llmApiKey,
                llm_model: llmModel,
                telemetry_enabled: telemetryEnabled,
                auth_enabled: authEnabled,
                auth_username: authUsername,
                auth_password: authPassword || undefined,
                auth_session_expiry_hours: authSessionExpiryHours,
                trusted_proxy_hosts: effectiveTrustedProxyHosts,
                public_access_enabled: publicAccessEnabled,
                public_access_show_camera_names: publicAccessShowCameraNames,
                public_access_historical_days: publicAccessHistoricalDays,
                public_access_rate_limit_per_minute: publicAccessRateLimitPerMinute,

                // Notifications
                notifications_discord_enabled: discordEnabled,
                notifications_discord_webhook_url: discordWebhook,
                notifications_discord_username: discordUsername,

                notifications_pushover_enabled: pushoverEnabled,
                notifications_pushover_user_key: pushoverUser,
                notifications_pushover_api_token: pushoverToken,
                notifications_pushover_priority: pushoverPriority,

                notifications_telegram_enabled: telegramEnabled,
                notifications_telegram_bot_token: telegramToken,
                notifications_telegram_chat_id: telegramChatId,

                notifications_email_enabled: emailEnabled,
                notifications_email_use_oauth: emailUseOAuth,
                notifications_email_oauth_provider: emailOAuthProvider,
                notifications_email_smtp_host: emailSmtpHost,
                notifications_email_smtp_port: emailSmtpPort,
                notifications_email_smtp_username: emailSmtpUsername,
                notifications_email_smtp_password: emailSmtpPassword,
                notifications_email_smtp_use_tls: emailSmtpUseTls,
                notifications_email_from_email: emailFromEmail,
                notifications_email_to_email: emailToEmail,
                notifications_email_include_snapshot: emailIncludeSnapshot,
                notifications_email_dashboard_url: emailDashboardUrl,

                notifications_filter_species_whitelist: filterWhitelist,
                notifications_filter_min_confidence: filterConfidence,
                notifications_filter_audio_confirmed_only: filterAudioOnly,
                notifications_notify_on_insert: notifyOnInsert,
                notifications_notify_on_update: notifyOnUpdate,
                notifications_delay_until_video: notifyDelayUntilVideo,
                notifications_video_fallback_timeout: notifyVideoFallbackTimeout,
                notification_language: $locale || 'en',

                // Accessibility
                accessibility_high_contrast: highContrast,
                accessibility_dyslexia_font: dyslexiaFont,
                accessibility_live_announcements: liveAnnouncements,
                species_info_source: speciesInfoSource
            });
            // Update store
            await settingsStore.load();
            // Sync local state to handle server-side normalization (e.g. stripped slashes)
            await loadSettings(true);
            message = { type: 'success', text: $_('notifications.settings_saved') };
            await Promise.all([loadMaintenanceStats(), loadCacheStats()]);
        } catch (e) {
            message = { type: 'error', text: 'Failed to save settings' };
        } finally {
            saving = false;
        }
    }

    async function testConnection() {
        testing = true;
        message = null;
        try {
            const result = await testFrigateConnection();
            if (result.status === 'ok') {
                message = { type: 'success', text: `Connected to Frigate v${result.version} at ${result.frigate_url}` };
            } else {
                message = { type: 'error', text: 'Frigate returned unexpected status' };
            }
        } catch (e: any) {
            const errorMsg = e.message || 'Failed to connect to Frigate';
            message = { type: 'error', text: errorMsg };
        } finally {
            testing = false;
        }
    }

    async function handleTestBirdWeather() {
        testingBirdWeather = true;
        message = null;
        try {
            const result = await testBirdWeather(birdweatherStationToken);
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test BirdWeather' };
        } finally {
            testingBirdWeather = false;
        }
    }

    async function handleTestBirdNET() {
        testingBirdNET = true;
        message = null;
        try {
            // Test generic MQTT first
            const mqttResult = await testMQTTPublish();
            if (mqttResult.status !== 'ok') {
                throw new Error(mqttResult.message);
            }

            // Then test BirdNET specific pipeline
            const result = await testBirdNET();
            if (result.status === 'ok') {
                message = { type: 'success', text: "MQTT Pipeline Verified: Test message sent to 'yawamf/test' and mock bird injected." };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || 'Failed to test MQTT Pipeline' };
        } finally {
            testingBirdNET = false;
        }
    }

    function toggleCamera(camera: string) {
        if (selectedCameras.includes(camera)) {
            selectedCameras = selectedCameras.filter(c => c !== camera);
        } else {
            selectedCameras = [...selectedCameras, camera];
        }
    }

    function setTheme(t: Theme) {
        themeStore.setTheme(t);
    }

    function setLayout(l: Layout) {
        layoutStore.setLayout(l);
    }

    function setLanguage(lang: string) {
        locale.set(lang);
        localStorage.setItem('preferred-language', lang);
    }

    function addBlockedLabel() {
        const label = newBlockedLabel.trim();
        if (label && !blockedLabels.includes(label)) {
            blockedLabels = [...blockedLabels, label];
            newBlockedLabel = '';
        }
    }

    function removeBlockedLabel(label: string) {
        blockedLabels = blockedLabels.filter(l => l !== label);
    }

    async function handleTestNotification(platform: string) {
        testingNotification[platform] = true;
        message = null;

        const credentials: any = {};
        if (platform === 'discord') {
            credentials.webhook_url = discordWebhook;
        } else if (platform === 'pushover') {
            credentials.user_key = pushoverUser;
            credentials.api_token = pushoverToken;
        } else if (platform === 'telegram') {
            credentials.bot_token = telegramToken;
            credentials.chat_id = telegramChatId;
        }

        try {
            const result = await testNotification(platform, credentials);
            if (result.status === 'ok') {
                message = { type: 'success', text: result.message };
            } else {
                message = { type: 'error', text: result.message };
            }
        } catch (e: any) {
            message = { type: 'error', text: e.message || `Failed to test ${platform}` };
        } finally {
            testingNotification[platform] = false;
        }
    }

    function addWhitelistSpecies() {
        const species = newWhitelistSpecies.trim();
        if (species && !filterWhitelist.includes(species)) {
            filterWhitelist = [...filterWhitelist, species];
            newWhitelistSpecies = '';
        }
    }

    function removeWhitelistSpecies(species: string) {
        filterWhitelist = filterWhitelist.filter(s => s !== species);
    }

    // Wrapper functions for notification testing to match component API
    async function sendTestDiscord() {
        await handleTestNotification('discord');
    }

    async function sendTestPushover() {
        await handleTestNotification('pushover');
    }

    async function sendTestTelegram() {
        await handleTestNotification('telegram');
    }
</script>

<div class="max-w-4xl mx-auto space-y-8 pb-20">
    <!-- Header -->
    <div class="flex items-center justify-between">
        <div>
            <h2 class="text-3xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.title')}</h2>
            <p class="text-sm text-slate-500 dark:text-slate-400 font-medium">{$_('settings.subtitle')}</p>
        </div>
        <button
            onclick={() => loadSettings()}
            disabled={loading}
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-bold rounded-xl
                   text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-800
                   border border-slate-200 dark:border-slate-700 shadow-sm
                   hover:bg-slate-50 dark:hover:bg-slate-700 hover:text-teal-600 dark:hover:text-teal-400
                   transition-all disabled:opacity-50"
        >
            <svg class="w-4 h-4 {loading ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            {$_('common.refresh')}
        </button>
    </div>

    <!-- Status Messages -->
    {#if message}
        <div class="p-4 rounded-2xl animate-in slide-in-from-top-2 {message.type === 'success'
            ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
            : 'bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20'}">
            <div class="flex items-center gap-3">
                {#if message.type === 'success'}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>
                {:else}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                {/if}
                <span class="font-bold text-sm">{message.text}</span>
            </div>
        </div>
    {/if}

    {#if loading}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            {#each [1, 2, 3, 4] as _}
                <div class="h-48 bg-slate-100 dark:bg-slate-800/50 rounded-3xl animate-pulse border border-slate-200 dark:border-slate-700/50"></div>
            {/each}
        </div>
    {:else}
        <!-- Tab Navigation -->
        <SettingsTabs {activeTab} ontabchange={handleTabChange} />

        <div class="space-y-6">
            <!-- Connection Tab -->
            {#if activeTab === 'connection'}
                <ConnectionSettings
                    bind:frigateUrl
                    bind:mqttServer
                    bind:mqttPort
                    bind:mqttAuth
                    bind:mqttUsername
                    bind:mqttPassword
                    bind:selectedCameras
                    bind:clipsEnabled
                    bind:telemetryEnabled
                    {availableCameras}
                    {camerasLoading}
                    {testing}
                    {telemetryInstallationId}
                    {telemetryPlatform}
                    {versionInfo}
                    {testConnection}
                    {loadCameras}
                    {handleTestBirdNET}
                    {toggleCamera}
                />
            {/if}

            <!-- Detection Tab -->
            {#if activeTab === 'detection'}
                <DetectionSettings
                    bind:threshold
                    bind:minConfidence
                    bind:trustFrigateSublabel
                    bind:displayCommonNames
                    bind:scientificNamePrimary
                    bind:autoVideoClassification
                    bind:videoClassificationDelay
                    bind:videoClassificationMaxRetries
                    bind:blockedLabels
                    bind:newBlockedLabel
                    {videoCircuitOpen}
                    {videoCircuitUntil}
                    {videoCircuitFailures}
                    {addBlockedLabel}
                    {removeBlockedLabel}
                />
            {/if}

            <!-- Notifications Tab -->
            {#if activeTab === 'notifications'}
                <NotificationSettings
                    bind:notifyMinConfidence={filterConfidence}
                    bind:notifyAudioOnly={filterAudioOnly}
                    bind:notifySpeciesWhitelist={filterWhitelist}
                    bind:newSpecies={newWhitelistSpecies}
                    bind:notifyOnInsert
                    bind:notifyOnUpdate
                    bind:notifyDelayUntilVideo
                    bind:notifyVideoFallbackTimeout
                    bind:discordEnabled
                    bind:discordWebhook
                    bind:discordWebhookSaved
                    bind:discordBotName={discordUsername}
                    bind:pushoverEnabled
                    bind:pushoverUserKey={pushoverUser}
                    bind:pushoverUserSaved
                    bind:pushoverApiToken={pushoverToken}
                    bind:pushoverTokenSaved
                    bind:pushoverPriority
                    bind:telegramEnabled
                    bind:telegramBotToken={telegramToken}
                    bind:telegramTokenSaved
                    bind:telegramChatId
                    bind:telegramChatIdSaved
                    bind:emailEnabled
                    bind:emailUseOAuth
                    bind:emailConnectedEmail
                    bind:emailOAuthProvider
                    bind:emailSmtpHost
                    bind:emailSmtpPort
                    bind:emailSmtpUseTls
                    bind:emailSmtpUsername
                    bind:emailSmtpPassword
                    bind:emailSmtpPasswordSaved
                    bind:emailFromEmail
                    bind:emailToEmail
                    bind:emailIncludeSnapshot
                    bind:emailDashboardUrl
                    bind:testingNotification
                    addSpeciesToWhitelist={addWhitelistSpecies}
                    removeSpeciesFromWhitelist={removeWhitelistSpecies}
                    {sendTestDiscord}
                    {sendTestPushover}
                    {sendTestTelegram}
                    {sendTestEmail}
                    {initiateGmailOAuth}
                    {initiateOutlookOAuth}
                    {disconnectEmailOAuth}
                />
            {/if}

            <!-- Integrations Tab -->
            {#if activeTab === 'integrations'}
                <IntegrationSettings
                    bind:birdnetEnabled
                    bind:audioTopic
                    bind:audioBufferHours
                    bind:audioCorrelationWindowSeconds
                    bind:cameraAudioMapping
                    bind:birdweatherEnabled
                    bind:birdweatherStationToken
                    bind:llmEnabled
                    bind:llmProvider
                    bind:llmApiKey
                    bind:llmModel
                    bind:locationLat
                    bind:locationLon
                    bind:locationAuto
                    bind:locationTemperatureUnit
                    {availableCameras}
                    {availableModels}
                    {testingBirdWeather}
                    {handleTestBirdNET}
                    {handleTestBirdWeather}
                />
            {/if}

            <!-- Security Tab -->
            {#if activeTab === 'security'}
                {#if authStore.httpsWarning}
                    <div class="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800">
                        <div class="flex items-center gap-2">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                            <span><strong>Security Warning:</strong> Authentication is enabled over HTTP. Your credentials may be exposed. Use HTTPS in production.</span>
                        </div>
                    </div>
                {/if}
                <AuthenticationSettings
                    bind:authEnabled
                    bind:authUsername
                    bind:authHasPassword
                    bind:authPassword
                    bind:authPasswordConfirm
                    bind:authSessionExpiryHours
                    bind:trustedProxyHosts
                    bind:trustedProxyHostsSuggested
                    bind:newTrustedProxyHost
                    bind:publicAccessEnabled
                    bind:publicAccessShowCameraNames
                    bind:publicAccessHistoricalDays
                    bind:publicAccessRateLimitPerMinute
                    addTrustedProxyHost={addTrustedProxyHost}
                    removeTrustedProxyHost={removeTrustedProxyHost}
                    acceptTrustedProxySuggestions={acceptTrustedProxySuggestions}
                />
            {/if}

            <!-- Data Tab -->
            {#if activeTab === 'data'}
                <DataSettings
                    bind:retentionDays
                    bind:cacheEnabled
                    bind:cacheSnapshots
                    bind:cacheClips
                    bind:cacheRetentionDays
                    bind:speciesInfoSource
                    bind:backfillDateRange
                    bind:backfillStartDate
                    bind:backfillEndDate
                    {maintenanceStats}
                    {cacheStats}
                    {cleaningUp}
                    {cleaningCache}
                    {backfilling}
                    {backfillResult}
                    {taxonomyStatus}
                    {syncingTaxonomy}
                    {resettingDatabase}
                    {analyzingUnknowns}
                    {analysisStatus}
                    {analysisTotal}
                    {handleCleanup}
                    {handleCacheCleanup}
                    {handleStartTaxonomySync}
                    {handleBackfill}
                    {handleAnalyzeUnknowns}
                    {handleResetDatabase}
                />
            {/if}

            <!-- Appearance Tab -->
            {#if activeTab === 'appearance'}
                <AppearanceSettings
                    {currentTheme}
                    {currentLayout}
                    currentLocale={$locale || 'en'}
                    {setTheme}
                    {setLayout}
                    {setLanguage}
                />
            {/if}

            <!-- Accessibility Tab -->
            {#if activeTab === 'accessibility'}
                <AccessibilitySettings
                    bind:highContrast
                    bind:dyslexiaFont
                    bind:liveAnnouncements
                />
            {/if}
        </div>

        <!-- Save Button (Sticky Footer) -->
        {#if isDirty}
            <div class="fixed bottom-0 left-0 right-0 bg-white/95 dark:bg-slate-900/95 backdrop-blur-lg border-t border-slate-200 dark:border-slate-700 shadow-2xl z-50 animate-in slide-in-from-bottom-4">
                <div class="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
                    <div class="flex items-center gap-3 text-slate-600 dark:text-slate-400">
                        <svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                        <span class="text-sm font-bold">{$_('common.unsaved_changes')}</span>
                    </div>
                    <button
                        onclick={saveSettings}
                        disabled={saving}
                        class="px-8 py-3 bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-600 hover:to-emerald-600
                               text-white font-black text-sm uppercase tracking-widest rounded-2xl shadow-lg
                               shadow-teal-500/30 transition-all disabled:opacity-50"
                    >
                        {saving ? $_('common.saving') : $_('common.apply_settings')}
                    </button>
                </div>
            </div>
        {/if}
    {/if}
</div>

<style>
    .custom-scrollbar::-webkit-scrollbar {
        width: 4px;
    }
    .custom-scrollbar::-webkit-scrollbar-track {
        background: transparent;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb {
        background: #94a3b833;
        border-radius: 10px;
    }
</style>
