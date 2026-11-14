<script lang="ts">
    import { onMount, onDestroy, tick, untrack } from 'svelte';
    import type { NotificationLinkTarget } from '../settings/notification-link';
    import { canonicalSettingsPath, settingsTabFromRoute, settingsTabPath, type SettingsTab } from '../settings/settings-route';
    import {
        fetchSettings,
        updateSettings,
        subscribeSettingsUpdates,
        fetchFrigateConfig,
        fetchClassifierStatus,
        downloadDefaultModel,
        fetchMaintenanceStats,
        runCleanup,
        clearAllFavorites,
        purgeMissingMedia,
        runBackfill,
        runWeatherBackfill,
        startBackfillJob,
        startWeatherBackfillJob,
        getBackfillStatus,
        fetchCacheStats,
        runCacheCleanup,
        fetchTaxonomyStatus,
        startTaxonomySync,
        fetchTimezoneRepairPreview,
        applyTimezoneRepair,
        resetDatabase,
        clearClassificationFeedback,
        analyzeUnknowns,
        fetchAudioSources,
        searchSpecies,
        fetchRecordingClipCapability,
        fetchVersion,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth,
        initiateInaturalistOAuth,
        disconnectInaturalistOAuth,
        sendTestEmail,
        exportEbirdCsv,
        exportConfigBackup,
        importConfigBackup,
        type ClassifierStatus,
        type MaintenanceStats,
        type BackfillResult,
        type WeatherBackfillResult,
        type BackfillJobStatus,
        type CacheStats,
        type CacheCleanupResult,
        type TaxonomySyncStatus,
        type TimezoneRepairPreview,
        type VersionInfo,
        type AnalysisStatus,
        type AudioSourceOption,
        type PurgeMissingMediaResult,
        type RecordingClipCapability
    } from '../api';
    import { SettingsSaveRejected, type BlockedSpeciesEntry, type ClassificationImageSource, type NotificationSpeciesFilterMode, type Settings as SettingsPayload, type SettingsUpdate } from '../api/settings';
    import { ApiRequestError } from '../api/core';
    import { themeStore, type Theme } from '../stores/theme.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { REFRESH_CADENCE_MS } from '../app/refresh-cadence';
    import { startVisiblePoll } from '../app/visible-poll';
    import { analysisQueueStatusStore } from '../stores/analysis_queue_status.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { toAppPath } from '../app/url-base';
    import { authStore } from '../stores/auth.svelte';
    import { passwordProblemMessage, validateAuthSettingsSave } from '../auth-password-policy';
    import { toastStore } from '../stores/toast.svelte';
    import { confirmAction } from '../stores/confirm_dialog.svelte';
    import { jobProgressStore } from '../stores/job_progress.svelte';
    import { jobDiagnosticsStore } from '../stores/job_diagnostics.svelte';
    import { notificationCenter } from '../stores/notification_center.svelte';
    import type { GardenNotificationChannel } from '../api/garden';
    import { notificationPolicy } from '../notifications/policy';
    import {
        formatBackfillProgressSummary,
        resolveRunningBackfillMessage,
        updateScopedBackfillProgress
    } from '../backfill/progress';
    import { formatTerminalBackfillMessage, isBackfillTerminalTransition } from '../backfill/terminal-message';
    import { _, locale } from 'svelte-i18n';
    import { setAppLocale } from '../i18n';
    import SettingsTabs from '../components/settings/SettingsTabs.svelte';
    import SettingsPage from '../components/settings/_primitives/SettingsPage.svelte';
    import AdvancedSection from '../components/settings/_primitives/AdvancedSection.svelte';
    import SettingsCard from '../components/settings/_primitives/SettingsCard.svelte';
    import SettingsRow from '../components/settings/_primitives/SettingsRow.svelte';
    import SettingsToggle from '../components/settings/_primitives/SettingsToggle.svelte';
    import type { DomesticBirdKey } from '../utils/domestic-birds';
    import { locationChangedFields } from '../settings/location-dirty';
    import { retentionShrinks } from '../settings/retention-change';
    import {
        inferenceProviderForSave,
        parseInferenceProvider,
        reconcileSavedInferenceProvider,
        type InferenceProvider
    } from '../settings/inference-providers';
    import { getErrorMessage } from '../utils/error-handling';

    // Every tab is its own chunk, loaded when it is opened (see the loaders above).
    import LazyRoute from '../components/LazyRoute.svelte';
    import { lazyComponent } from '../app/lazy-component';
    import { appearanceSection, type AppearanceDraft } from '../settings/appearance-section';
    import { accessibilitySection, type AccessibilityDraft } from '../settings/accessibility-section';
    import { enrichmentSection, type EnrichmentDraft } from '../settings/enrichment-section';
    import { aiSection, editAiDraft, type AiDraft } from '../settings/ai-section';
    import { sectionChangedFields } from '../settings/section-adapter';
    import { changedFields, settingsFieldPlace, settingsFieldTab, summarizeUnsaved } from '../settings/settings-fields';
    import { rangeFieldError, standingFieldErrors, type SettingsFieldError } from '../settings/field-errors';
    import { provideSettingsFieldErrors } from '../settings/field-error-context';
    import { unsavedChanges } from '../stores/unsaved-changes';
    import {
        buildBirdModelRegionOverrideSettings,
        resolveBirdModelRegionOverrideFromSettings,
    } from '../settings/bird-model-region-override';
    import { parseBirdFinder, type BirdFinder, type BirdFinderProvider } from '../settings/bird-finder';
    import {
        mergeBlockedSpeciesEntries,
        migrateLegacyBlockedLabels,
    } from '../settings/blocked-species';
    import { getRecommendedLlmModel } from '../settings/llm-models';
    import { savedNotifyMode, savedTrustedProxyHosts, type NotifyMode } from '../settings/notification-mode';

    let {
        onNavigate,
        currentRoute
    }: {
        onNavigate?: (path: string, opts?: { replace?: boolean }) => void;
        currentRoute?: string;
    } = $props();

    // Tab bodies load when first opened. Their drafts stay here, so a tab's edits survive leaving it.
    const loadConnectionSettings = lazyComponent(() => import('../components/settings/ConnectionSettings.svelte'));
    const loadDetectionSettings = lazyComponent(() => import('../components/settings/DetectionSettings.svelte'));
    const loadNotificationSettings = lazyComponent(() => import('../components/settings/NotificationSettings.svelte'));
    const loadIntegrationSettings = lazyComponent(() => import('../components/settings/IntegrationSettings.svelte'));
    const loadAuthenticationSettings = lazyComponent(() => import('../components/settings/AuthenticationSettings.svelte'));
    const loadDataSettings = lazyComponent(() => import('../components/settings/DataSettings.svelte'));
    const loadGardenBetaSettings = lazyComponent(() => import('../components/settings/GardenBetaSettings.svelte'));
    const loadAppearanceTab = lazyComponent(() => import('../components/settings/AppearanceSettings.svelte'));
    const loadAccessibilityTab = lazyComponent(() => import('../components/settings/AccessibilitySettings.svelte'));
    const loadHealthTab = lazyComponent(() => import('./Errors.svelte'));
    const loadEnrichmentTab = lazyComponent(() => import('../components/settings/EnrichmentSettings.svelte'));
    const loadAiTab = lazyComponent(() => import('../components/settings/AISettings.svelte'));

    function normalizeFrigateMissingBehavior(value: unknown): 'mark_missing' | 'keep' | 'delete' {
        return value === 'keep' || value === 'delete' ? value : 'mark_missing';
    }

    function normalizePublicDaysMode(value: unknown): 'retention' | 'custom' {
        return value === 'custom' ? 'custom' : 'retention';
    }

    let frigateUrl = $state('');
    let frigateIngestLabels = $state('bird');
    let frigateExternalUrl = $state('');
    let mqttServer = $state('');
    let mqttPort = $state(1883);
    let mqttAuth = $state(false);
    let mqttUsername = $state('');
    let mqttPassword = $state('');
    let mqttPasswordSaved = $state(false);
    let audioTopic = $state('birdnet/text');
    let cameraAudioMapping = $state<Record<string, string>>({});
    let cameraRoles = $state<Record<string, 'feeder' | 'nest'>>({});
    let gardenCameras = $state<string[]>([]);
    let gardenLabels = $state('cat, dog');
    let gardenMotionCameras = $state<string[]>([]);
    let gardenMotionConfidence = $state(0.5);
    let gardenNotificationsEnabled = $state(false);
    let gardenNotificationChannels = $state<GardenNotificationChannel[]>([]);
    let gardenNotificationsUseBirdChannels = $state(true);
    let gardenNotificationsIncludePhoto = $state(true);
    let gardenAutomaticNaming = $state(true);
    let gardenNamingThreshold = $state(0.8);
    let gardenDomesticBirds = $state<DomesticBirdKey[]>([]);
    let nestDedupeMinutes = $state(30);
    let birdnetSourceOptions = $state<AudioSourceOption[]>([]);
    let loadingBirdnetSources = $state(false);
    let birdnetSourcesError = $state<string | null>(null);
    let audioBufferHours = $state(24);
    let audioCorrelationWindowSeconds = $state(300);
    let classificationImageSource = $state<ClassificationImageSource>('frigate_snapshot');
    let recordingFrameDelaySeconds = $state(12);
    let clipsEnabled = $state(true);
    let recordingClipEnabled = $state(false);
    let recordingClipBeforeSeconds = $state(30);
    let recordingClipAfterSeconds = $state(90);
    let recordingClipCapability = $state<RecordingClipCapability | null>(null);
    let recordingClipCapabilityLoading = $state(false);
    let threshold = $state(0.7);
    let minConfidence = $state(0.4);
    let liveWorkerCount = $state<number | null>(null);
    let backgroundWorkerCount = $state<number | null>(null);
    let trustFrigateSublabel = $state(true);
    let writeFrigateSublabel = $state(true);
    // The font and colour live in the theme store so a choice previews across the app before
    // Apply; the rest of the Appearance draft is held here.
    let appearanceChoices = $state<Omit<AppearanceDraft, 'fontTheme' | 'colorTheme'>>({
        displayCommonNames: true,
        scientificNamePrimary: false,
        explorerView: 'cards',
        dateFormat: 'locale',
        timeFormat: 'locale'
    });
    const appearanceDraft: AppearanceDraft = $derived({
        ...appearanceChoices,
        fontTheme: themeStore.fontTheme,
        colorTheme: themeStore.colorTheme
    });
    let personalizedRerankEnabled = $state(false);
    let rangeFilterEnabled = $state(false);
    let rangeFilterRegionLevel = $state<'county' | 'state' | 'country'>('county');
    let autoVideoClassification = $state(false);
    let videoClassificationDelay = $state(30);
    let videoClassificationMaxRetries = $state(3);
    let videoClassificationFrames = $state(15);
    let birdModelRegionOverride = $state<'auto' | 'eu' | 'na'>('auto');
    let birdFinder = $state<BirdFinder>('yolox_tiny');
    let birdFinderProvider = $state<BirdFinderProvider>('auto');
    let imageExecutionMode = $state<'in_process' | 'subprocess' | string>('subprocess');
    let inferenceProvider = $state<InferenceProvider>('auto');
    let videoCircuitOpen = $state(false);
    let videoCircuitUntil = $state<string | null>(null);
    let videoCircuitFailures = $state(0);
    let selectedCameras = $state<string[]>([]);
    let retentionDays = $state(0);
    let maintenanceMaxConcurrent = $state(1);
    let frigateMissingBehavior = $state<'mark_missing' | 'keep' | 'delete'>('mark_missing');
    let autoPurgeMissingClips = $state(false);
    let autoPurgeMissingSnapshots = $state(false);
    let autoAnalyzeUnknowns = $state(false);
    let blockedLabels = $state<string[]>([]);
    let blockedSpecies = $state<BlockedSpeciesEntry[]>([]);
    let blockedLabelsBaseline = $state<string[]>([]);
    let blockedSpeciesBaseline = $state<BlockedSpeciesEntry[]>([]);

    // Taxonomy Sync State
    let taxonomyStatus = $state<TaxonomySyncStatus | null>(null);
    let syncingTaxonomy = $state(false);
    let taxonomyPollInterval: ReturnType<typeof setInterval> | undefined;
    // The repair starts as a background task after the request returns, so the first
    // status reads can still say idle. Keep polling for a bounded while after starting:
    // a run with nothing to repair finishes before it is ever seen running.
    const TAXONOMY_START_GRACE_MS = 15_000;
    let settingsLoadFailed = $state(false);
    /** A read the shell finished this recently is the same answer a second request would get. */
    const SHARED_SETTINGS_READ_MS = 5_000;
    let taxonomyAwaitingStartUntil = 0;
    let taxonomyStatusLoading = false;

    // Location Settings
    let locationLat = $state<number | null>(null);
    let locationLon = $state<number | null>(null);
    let locationState = $state('');
    let locationCountry = $state('');
    let locationAuto = $state(true);
    let locationWeatherUnitSystem = $state<'metric' | 'imperial' | 'british'>('metric');

    // BirdNET-Go Settings
    let birdnetEnabled = $state(true);
    let birdnetUrl = $state('');
    let birdnetExternalUrl = $state('');

    // BirdWeather Settings
    let birdweatherEnabled = $state(false);
    let birdweatherStationToken = $state('');
    let birdweatherStationTokenSaved = $state(false);
    let haWeatherEnabled = $state(false);
    let haWeatherBaseUrl = $state('');
    let haWeatherAccessToken = $state('');
    let haWeatherAccessTokenSaved = $state(false);
    let haWeatherEntity = $state('');
    let haWeatherTemperatureEntity = $state('');
    let haWeatherWindSpeedEntity = $state('');
    let haWeatherWindDirectionEntity = $state('');
    let haWeatherCloudCoverEntity = $state('');
    let haWeatherPrecipitationEntity = $state('');
    let haWeatherRainEntity = $state('');
    let haWeatherSnowfallEntity = $state('');
    let haWeatherIlluminanceEntity = $state('');

    // iNaturalist Settings
    let inaturalistEnabled = $state(false);
    let inaturalistClientId = $state('');
    let inaturalistClientSecret = $state('');
    let inaturalistClientIdSaved = $state(false);
    let inaturalistClientSecretSaved = $state(false);
    let inaturalistDefaultLat = $state<number | null>(null);
    let inaturalistDefaultLon = $state<number | null>(null);
    let inaturalistDefaultPlace = $state('');
    let inaturalistConnectedUser = $state<string | null>(null);

    let aiDraft = $state<AiDraft>({
        llmEnabled: false,
        llmProvider: 'gemini',
        llmApiKey: '',
        llmApiKeySaved: false,
        llmModel: getRecommendedLlmModel('gemini'),
        llmAnalysisPromptTemplate: '',
        llmConversationPromptTemplate: '',
        llmChartPromptTemplate: '',
        aiPricingJson: '[]'
    });

    // Telemetry
    let telemetryEnabled = $state(true);
    let telemetryHealthEnabled = $state(false);
    let telemetryInstallationId = $state<string | undefined>(undefined);
    let telemetryPlatform = $state<string | undefined>(undefined);
    let telemetryPayloadPreview = $state<Record<string, unknown> | undefined>(undefined);

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
    let publicAccessShowAiConversation = $state(false);
    let publicAccessAllowClipDownloads = $state(false);
    let publicAccessShowAudio = $state(true);
    let publicAccessShowSnapshots = $state(true);
    let publicAccessShowClips = $state(true);
    let publicAccessLocationPrecision = $state<'approximate' | 'exact'>('approximate');
    let publicAccessHistoricalDaysMode = $state<'retention' | 'custom'>('retention');
    let publicAccessHistoricalDays = $state(7);
    let publicAccessMediaDaysMode = $state<'retention' | 'custom'>('retention');
    let publicAccessMediaHistoricalDays = $state(7);
    let publicAccessRateLimitPerMinute = $state(30);
    let publicAccessExternalBaseUrl = $state('');
    let debugUiEnabled = $state(false);
    let strictNonFiniteOutput = $state(true);
    let betaGardenAnimals = $state(false);

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
    let pushoverDevice = $state('');

    let telegramEnabled = $state(false);
    let telegramToken = $state('');
    let telegramTokenSaved = $state(false);
    let telegramChatId = $state('');
    let telegramChatIdSaved = $state(false);

    let emailEnabled = $state(false);
    let emailUseOAuth = $state(false);
    let emailOAuthProvider = $state<string | null>(null);
    let emailConnectedEmail = $state<string | null>(null);
    let emailOnlyOnEnd = $state(false);
    let emailSmtpHost = $state('');
    let emailSmtpPort = $state(587);
    let emailSmtpUsername = $state('');
    let emailSmtpPassword = $state('');
    let emailSmtpPasswordSaved = $state(false);
    let emailSmtpUseTls = $state(true);
    let emailFromEmail = $state('');
    let emailToEmail = $state('');
    let emailIncludeSnapshot = $state(true);
    let instanceUrl = $state('');
    let notifyLinkTarget = $state<NotificationLinkTarget>('yawamf');
    let emailGmailClientId = $state('');
    let emailGmailClientSecret = $state('');
    let emailGmailClientSecretSaved = $state(false);
    let emailOutlookClientId = $state('');
    let emailOutlookClientSecret = $state('');
    let emailOutlookClientSecretSaved = $state(false);

    let notificationLanguage = $state('en');

    let filterWhitelist = $state<string[]>([]);
    let filterSpeciesMode = $state<NotificationSpeciesFilterMode>('none');
    let filterSpeciesEntries = $state<BlockedSpeciesEntry[]>([]);
    let filterConfidence = $state(0.7);
    let filterAudioOnly = $state(false);
    let notifyMode = $state<NotifyMode>('standard');
    let notifyOnInsert = $state(true);
    let notifyOnUpdate = $state(false);
    let notifyDelayUntilVideo = $state(false);
    let notifyVideoFallbackTimeout = $state(45);
    let notifyCooldownMinutes = $state(0);


    function normalizeNotificationSpeciesMode(value: unknown): NotificationSpeciesFilterMode | null {
        return value === 'none' || value === 'blacklist' || value === 'whitelist' ? value : null;
    }

    function inferNotificationSpeciesMode(settings: SettingsPayload): NotificationSpeciesFilterMode {
        const mode = normalizeNotificationSpeciesMode(settings.notifications_filter_species_mode);
        if (mode) return mode;
        const blacklist = settings.notifications_filter_species_blacklist_structured || [];
        const whitelist = settings.notifications_filter_species_whitelist_structured || [];
        const legacyWhitelist = settings.notifications_filter_species_whitelist || [];
        if (blacklist.length > 0) return 'blacklist';
        if (whitelist.length > 0 || legacyWhitelist.length > 0) return 'whitelist';
        return 'none';
    }

    function notificationSpeciesEntriesForMode(settings: SettingsPayload, mode: NotificationSpeciesFilterMode): BlockedSpeciesEntry[] {
        if (mode === 'blacklist') return settings.notifications_filter_species_blacklist_structured || [];
        if (mode === 'whitelist') return settings.notifications_filter_species_whitelist_structured || [];
        return [];
    }

    // Accessibility
    let accessibilityDraft = $state<AccessibilityDraft>({
        highContrast: false,
        dyslexiaFont: false,
        liveAnnouncements: true,
        reducedMotion: false
    });

    // eBird
    let ebirdEnabled = $state(false);
    let ebirdApiKey = $state('');
    let ebirdApiKeySaved = $state(false);
    let ebirdDefaultRadiusKm = $state(25);
    let ebirdDefaultDaysBack = $state(14);
    let ebirdMaxResults = $state(25);
    let ebirdLocale = $state('en');

    // Enrichment sources
    let enrichmentDraft = $state<EnrichmentDraft>({
        enrichmentMode: 'per_enrichment',
        enrichmentSingleProvider: 'wikipedia',
        enrichmentSummarySource: 'wikipedia',
        enrichmentTaxonomySource: 'inaturalist',
        enrichmentSightingsSource: 'disabled',
        enrichmentSeasonalitySource: 'disabled',
        enrichmentRaritySource: 'disabled',
        enrichmentLinksSources: ['wikipedia', 'inaturalist']
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
        if (mqttPasswordSaved && mqttPassword) {
            mqttPasswordSaved = false;
        }
    });

    $effect(() => {
        if (birdweatherStationTokenSaved && birdweatherStationToken) {
            birdweatherStationTokenSaved = false;
        }
    });

    $effect(() => {
        if (inaturalistClientIdSaved && inaturalistClientId) {
            inaturalistClientIdSaved = false;
        }
    });

    $effect(() => {
        if (inaturalistClientSecretSaved && inaturalistClientSecret) {
            inaturalistClientSecretSaved = false;
        }
    });

    $effect(() => {
        if (emailGmailClientSecretSaved && emailGmailClientSecret) {
            emailGmailClientSecretSaved = false;
        }
    });

    $effect(() => {
        if (emailOutlookClientSecretSaved && emailOutlookClientSecret) {
            emailOutlookClientSecretSaved = false;
        }
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
        git_hash: __GIT_HASH__,
        branch: typeof __APP_BRANCH__ === 'string' ? __APP_BRANCH__ : 'unknown'
    });

    let availableCameras = $state<string[]>([]);
    // Only a successful read says which cameras Frigate has; `availableCameras` falls back to the
    // saved list for the pickers that need names, which must not pass for Frigate's answer.
    let frigateCameras = $state<string[] | null>(null);
    let frigateCamerasFailed = $state(false);
    let camerasLoading = $state(false);

    let loading = $state(true);
    let saving = $state(false);
    // A refused save: the reasons on their fields, and the values they refused, so a corrected
    // field stops being marked as soon as it holds something else.
    let fieldErrors = $state.raw<SettingsFieldError[]>([]);
    let refusedPayload = $state.raw<Record<string, unknown>>({});
    let saveProblem = $state<{ key: string; values?: Record<string, string>; fallback: string } | null>(null);
    let currentTheme: Theme = $state('system');
    let lastFeedbackKey = '';
    let lastFeedbackAt = 0;
    const BACKFILL_TOAST_THROTTLE_MS = 6 * 60 * 60 * 1000;
    const BACKFILL_NOTIFICATION_SYNC_THROTTLE_MS = 1200;

    const normalizeSecret = (value?: string | null) => value === '***REDACTED***' ? '' : (value || '');
    const safeCount = (value: unknown): number => {
        const parsed = Number(value ?? 0);
        return Number.isFinite(parsed) ? Math.max(0, Math.floor(parsed)) : 0;
    };
    const toErrorMessage = (error: unknown, fallback: string): string => {
        if (error instanceof Error) {
            return error.message || fallback;
        }
        if (typeof error === 'string' && error.trim().length > 0) {
            return error.trim();
        }
        return fallback;
    };
    const mergeBackfillTotal = (
        previousJobId: string | null,
        previousTotal: number,
        status: BackfillJobStatus | null
    ): { jobId: string | null; total: number } => {
        return updateScopedBackfillProgress(
            { jobId: previousJobId, total: previousTotal },
            status
        );
    };

    function isBackfillNotificationForKind(item: { id: string; meta?: { kind?: unknown } }, kind: 'detections' | 'weather') {
        if (item.id.startsWith(`backfill:${kind}:`)) return true;
        if (!item.id.startsWith('backfill:')) return false;
        return item.meta?.kind === kind;
    }

    function settleBackfillProcessNotifications(kind: 'detections' | 'weather', keepId?: string) {
        const now = Date.now();
        for (const item of notificationCenter.items) {
            if (item.type !== 'process' || item.read) continue;
            if (!isBackfillNotificationForKind(item, kind)) continue;
            if (keepId && item.id === keepId) continue;
            notificationCenter.upsert({
                ...item,
                type: 'update',
                read: true,
                timestamp: now,
                meta: {
                    ...(item.meta ?? {}),
                    source: item.meta?.source ?? 'ui',
                    kind
                }
            });
        }
    }

    function reconcileBackfillNotification(kind: 'detections' | 'weather', status: BackfillJobStatus | null, scopedTotal = 0) {
        if (!status) {
            const prefix = `backfill:${kind}:`;
            jobProgressStore.closeActiveByPrefix(prefix, 'stale');
            return;
        }

        const jobId = status.id || 'unknown';
        const id = `backfill:${kind}:${jobId}`;
        const legacyId = `backfill:${jobId}`;
        if (legacyId !== id) {
            notificationCenter.remove(legacyId);
        }

        const processed = safeCount(status.processed);
        const total = safeCount(status.total);
        const updated = safeCount(status.updated);
        const newDetections = kind === 'weather' ? undefined : safeCount(status.new_detections);
        const skipped = safeCount(status.skipped);
        const errors = safeCount(status.errors);

        const isRunning = status.status === 'running';
        const normalizedTotal = total > 0 ? total : safeCount(scopedTotal);
        const progressTotal = normalizedTotal > 0 ? normalizedTotal : (isRunning ? 0 : processed);
        settleBackfillProcessNotifications(kind, isRunning ? id : undefined);

        let title = kind === 'weather'
            ? $_('notifications.event_weather_backfill')
            : $_('notifications.event_backfill');
        if (status.status === 'completed') {
            title = kind === 'weather'
                ? $_('notifications.event_weather_backfill_done')
                : $_('notifications.event_backfill_done');
        } else if (status.status === 'failed') {
            title = kind === 'weather'
                ? $_('notifications.event_weather_backfill_failed')
                : $_('notifications.event_backfill_failed');
        }

        const signature = [
            status.status,
            processed,
            total,
            updated,
            newDetections,
            skipped,
            errors,
            status.message ?? ''
        ].join('|');
        const syncKey = `settings:backfill-sync:${kind}:${jobId}`;
        const throttleMs = isRunning ? BACKFILL_NOTIFICATION_SYNC_THROTTLE_MS : BACKFILL_TOAST_THROTTLE_MS;
        if (!notificationPolicy.shouldEmit(syncKey, signature, throttleMs)) {
            return;
        }

        let message = formatBackfillProgressSummary(processed, normalizedTotal, updated, skipped, errors, newDetections);
        if (!isRunning) {
            if (status.status === 'failed') {
                message = status.message || $_('notifications.event_backfill_failed');
            } else {
                message = status.message || formatBackfillProgressSummary(processed, normalizedTotal, updated, skipped, errors, newDetections);
            }
        } else {
            message = resolveRunningBackfillMessage(status, message);
        }

        const progressTitle = kind === 'weather'
            ? $_('notifications.event_weather_backfill')
            : $_('notifications.event_backfill');
        if (status.status === 'failed') {
            jobProgressStore.markFailed({
                id,
                kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
                title: progressTitle,
                message,
                route: '/settings',
                current: processed,
                total: progressTotal,
                source: 'poll'
            });
        } else if (status.status === 'completed') {
            jobProgressStore.markCompleted({
                id,
                kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
                title: progressTitle,
                message,
                route: '/settings',
                current: processed,
                total: progressTotal,
                source: 'poll'
            });
        } else {
            jobProgressStore.upsertRunning({
                id,
                kind: kind === 'weather' ? 'weather_backfill' : 'backfill',
                title: progressTitle,
                message,
                route: '/settings',
                current: processed,
                total: progressTotal,
                source: 'poll'
            });
        }

        notificationCenter.upsert({
            id,
            type: isRunning ? 'process' : 'update',
            title,
            message,
            timestamp: Date.now(),
            read: !isRunning,
            meta: {
                source: 'ui',
                route: '/settings',
                kind,
                processed,
                total: normalizedTotal
            }
        });
    }

    function emitTerminalBackfillToast(
        kind: 'detections' | 'weather',
        status: BackfillJobStatus,
        previous: BackfillJobStatus | null,
        type: 'success' | 'error',
        fallbackText: string
    ): boolean {
        // The first poll restores history; only a running job becoming terminal is new feedback.
        if (!isBackfillTerminalTransition(previous, status)) return false;
        const jobId = status.id || 'unknown';
        const terminalState = status.status === 'completed' ? 'completed' : 'failed';
        const key = `settings:backfill-toast:${kind}:${jobId}:${terminalState}`;
        // Terminal toasts should be one-shot per job + terminal state.
        const signature = `${kind}|${jobId}|${terminalState}`;
        if (!notificationPolicy.shouldEmit(key, signature, BACKFILL_TOAST_THROTTLE_MS)) {
            return false;
        }
        notify(type, formatTerminalBackfillMessage(kind, status.message, fallbackText));
        return true;
    }

    // Every result of an action on this page is told once, as a notification. The save's own
    // problems are the exception: they stay in the save bar beside the fields they concern.
    function notify(type: 'success' | 'error', text: string): void {
        const key = `${type}:${text}`;
        const now = Date.now();
        if (key === lastFeedbackKey && (now - lastFeedbackAt) < 1200) return;
        lastFeedbackKey = key;
        lastFeedbackAt = now;
        if (type === 'success') toastStore.success(text);
        else toastStore.error(text);
    }

    function handleActionFeedback(type: 'success' | 'error', text: string) {
        notify(type, text);
    }

    // Every saved setting the draft would change, named as the save sends it. One list drives the
    // save bar's count and tabs, the leave warning and Discard, so they can never disagree.
    const changedSettingFields = $derived.by((): string[] => {
        const s = settingsStore.settings;
        if (!s) {
            return [];
        }

        const checks = [
            { field: 'frigate_url', draft: frigateUrl, saved: s.frigate_url },
            { field: 'frigate_ingest_labels', draft: frigateIngestLabels, saved: (s.frigate_ingest_labels ?? ['bird']).join(', ') },
            { field: 'frigate_external_url', draft: frigateExternalUrl, saved: s.frigate_external_url || '' },
            { field: 'mqtt_server', draft: mqttServer, saved: s.mqtt_server },
            { field: 'mqtt_port', draft: mqttPort, saved: s.mqtt_port },
            { field: 'mqtt_auth', draft: mqttAuth, saved: s.mqtt_auth },
            { field: 'mqtt_username', draft: mqttUsername, saved: s.mqtt_username || '' },
            { field: 'mqtt_password', draft: mqttPassword, saved: normalizeSecret(s.mqtt_password) },
            { field: 'audio_topic', draft: audioTopic, saved: s.audio_topic || 'birdnet/text' },
            { field: 'audio_buffer_hours', draft: audioBufferHours, saved: s.audio_buffer_hours ?? 24 },
            { field: 'audio_correlation_window_seconds', draft: audioCorrelationWindowSeconds, saved: s.audio_correlation_window_seconds ?? 300 },
            { field: 'birdnet_enabled', draft: birdnetEnabled, saved: s.birdnet_enabled ?? true },
            { field: 'birdnet_url', draft: birdnetUrl, saved: s.birdnet_url || '' },
            { field: 'birdnet_external_url', draft: birdnetExternalUrl, saved: s.birdnet_external_url || '' },
            { field: 'classification_image_source', draft: classificationImageSource, saved: s.classification_image_source ?? 'frigate_snapshot' },
            { field: 'recording_frame_delay_seconds', draft: recordingFrameDelaySeconds, saved: s.recording_frame_delay_seconds ?? 12 },
            { field: 'clips_enabled', draft: clipsEnabled, saved: s.clips_enabled ?? true },
            { field: 'recording_clip_enabled', draft: recordingClipEnabled, saved: s.recording_clip_enabled ?? false },
            { field: 'recording_clip_before_seconds', draft: recordingClipBeforeSeconds, saved: s.recording_clip_before_seconds ?? 30 },
            { field: 'recording_clip_after_seconds', draft: recordingClipAfterSeconds, saved: s.recording_clip_after_seconds ?? 90 },
            { field: 'classification_threshold', draft: threshold, saved: s.classification_threshold },
            { field: 'trust_frigate_sublabel', draft: trustFrigateSublabel, saved: s.trust_frigate_sublabel ?? true },
            { field: 'write_frigate_sublabel', draft: writeFrigateSublabel, saved: s.write_frigate_sublabel ?? true },
            { field: 'personalized_rerank_enabled', draft: personalizedRerankEnabled, saved: s.personalized_rerank_enabled ?? false },
            { field: 'range_filter_enabled', draft: rangeFilterEnabled, saved: s.range_filter_enabled ?? false },
            { field: 'range_filter_region_level', draft: rangeFilterRegionLevel, saved: s.range_filter_region_level ?? 'county' },
            { field: 'auto_video_classification', draft: autoVideoClassification, saved: s.auto_video_classification ?? false },
            { field: 'video_classification_delay', draft: videoClassificationDelay, saved: s.video_classification_delay ?? 30 },
            { field: 'video_classification_max_retries', draft: videoClassificationMaxRetries, saved: s.video_classification_max_retries ?? 3 },
            { field: 'video_classification_frames', draft: videoClassificationFrames, saved: s.video_classification_frames ?? 15 },
            { field: 'image_execution_mode', draft: imageExecutionMode, saved: s.image_execution_mode ?? 'subprocess' },
            { field: 'strict_non_finite_output', draft: strictNonFiniteOutput, saved: s.strict_non_finite_output ?? true },
            { field: 'beta_garden_animals', draft: betaGardenAnimals, saved: s.beta_garden_animals ?? false },
            { field: 'inference_provider', draft: inferenceProvider, saved: parseInferenceProvider(s.inference_provider) ?? 'auto' },
            { field: 'cameras', draft: JSON.stringify(selectedCameras), saved: JSON.stringify(s.cameras || []) },
            { field: 'retention_days', draft: retentionDays, saved: s.retention_days || 0 },
            { field: 'maintenance_max_concurrent', draft: maintenanceMaxConcurrent, saved: s.maintenance_max_concurrent ?? 1 },
            { field: 'frigate_missing_behavior', draft: frigateMissingBehavior, saved: normalizeFrigateMissingBehavior(s.frigate_missing_behavior) },
            {
                field: 'auto_purge_missing_clips',
                draft: autoPurgeMissingClips || autoPurgeMissingSnapshots,
                saved: (s.auto_purge_missing_clips ?? false) || (s.auto_purge_missing_snapshots ?? false)
            },
            { field: 'auto_analyze_unknowns', draft: autoAnalyzeUnknowns, saved: s.auto_analyze_unknowns ?? false },
            { field: 'blocked_labels', draft: JSON.stringify(blockedLabels), saved: JSON.stringify(blockedLabelsBaseline) },
            { field: 'blocked_species', draft: JSON.stringify(blockedSpecies), saved: JSON.stringify(blockedSpeciesBaseline) },
            { field: 'media_cache_clips', draft: cacheClips, saved: s.media_cache_clips ?? false },
            { field: 'media_cache_high_quality_event_snapshots', draft: cacheHighQualityEventSnapshots, saved: s.media_cache_high_quality_event_snapshots ?? false },
            { field: 'media_cache_high_quality_event_snapshot_jpeg_quality', draft: cacheHighQualityEventSnapshotJpegQuality, saved: s.media_cache_high_quality_event_snapshot_jpeg_quality ?? 90 },
            { field: 'media_cache_retention_days', draft: cacheRetentionDays, saved: s.media_cache_retention_days ?? 0 },
            { field: 'media_cache_per_species_maximum', draft: cachePerSpeciesMaximum, saved: s.media_cache_per_species_maximum ?? 0 },
            { field: 'media_cache_max_size_mb', draft: cacheMaxSizeMb, saved: s.media_cache_max_size_mb ?? 0 },
            { field: 'media_cache_automatic_multi_bird_scan', draft: cacheAutomaticMultiBirdScan, saved: s.media_cache_automatic_multi_bird_scan ?? false },
            { field: 'media_cache_bird_scan_mode', draft: cacheBirdScanMode, saved: s.media_cache_bird_scan_mode ?? 'intensive' },
            { field: 'media_cache_per_species_minimum', draft: cachePerSpeciesMinimum, saved: s.media_cache_per_species_minimum ?? 0 },
            { field: 'birdweather_enabled', draft: birdweatherEnabled, saved: s.birdweather_enabled ?? false },
            { field: 'birdweather_station_token', draft: birdweatherStationToken, saved: normalizeSecret(s.birdweather_station_token) },
            { field: 'ha_weather_enabled', draft: haWeatherEnabled, saved: s.ha_weather_enabled ?? false },
            { field: 'ha_weather_base_url', draft: haWeatherBaseUrl, saved: s.ha_weather_base_url ?? '' },
            { field: 'ha_weather_access_token', draft: haWeatherAccessToken, saved: normalizeSecret(s.ha_weather_access_token) },
            { field: 'ha_weather_entity', draft: haWeatherEntity, saved: s.ha_weather_entity ?? '' },
            { field: 'ha_weather_temperature_entity', draft: haWeatherTemperatureEntity, saved: s.ha_weather_temperature_entity ?? '' },
            { field: 'ha_weather_wind_speed_entity', draft: haWeatherWindSpeedEntity, saved: s.ha_weather_wind_speed_entity ?? '' },
            { field: 'ha_weather_wind_direction_entity', draft: haWeatherWindDirectionEntity, saved: s.ha_weather_wind_direction_entity ?? '' },
            { field: 'ha_weather_cloud_cover_entity', draft: haWeatherCloudCoverEntity, saved: s.ha_weather_cloud_cover_entity ?? '' },
            { field: 'ha_weather_precipitation_entity', draft: haWeatherPrecipitationEntity, saved: s.ha_weather_precipitation_entity ?? '' },
            { field: 'ha_weather_rain_entity', draft: haWeatherRainEntity, saved: s.ha_weather_rain_entity ?? '' },
            { field: 'ha_weather_snowfall_entity', draft: haWeatherSnowfallEntity, saved: s.ha_weather_snowfall_entity ?? '' },
            { field: 'ha_weather_illuminance_entity', draft: haWeatherIlluminanceEntity, saved: s.ha_weather_illuminance_entity ?? '' },
            { field: 'ebird_enabled', draft: ebirdEnabled, saved: s.ebird_enabled ?? false },
            { field: 'ebird_api_key', draft: ebirdApiKey, saved: normalizeSecret(s.ebird_api_key) },
            { field: 'ebird_default_radius_km', draft: ebirdDefaultRadiusKm, saved: s.ebird_default_radius_km ?? 25 },
            { field: 'ebird_default_days_back', draft: ebirdDefaultDaysBack, saved: s.ebird_default_days_back ?? 14 },
            { field: 'ebird_max_results', draft: ebirdMaxResults, saved: s.ebird_max_results ?? 25 },
            { field: 'ebird_locale', draft: ebirdLocale, saved: s.ebird_locale ?? 'en' },
            { field: 'inaturalist_enabled', draft: inaturalistEnabled, saved: s.inaturalist_enabled ?? false },
            { field: 'inaturalist_client_id', draft: inaturalistClientId, saved: normalizeSecret(s.inaturalist_client_id) },
            { field: 'inaturalist_client_secret', draft: inaturalistClientSecret, saved: normalizeSecret(s.inaturalist_client_secret) },
            { field: 'inaturalist_default_latitude', draft: inaturalistDefaultLat, saved: s.inaturalist_default_latitude ?? null },
            { field: 'inaturalist_default_longitude', draft: inaturalistDefaultLon, saved: s.inaturalist_default_longitude ?? null },
            { field: 'inaturalist_default_place_guess', draft: inaturalistDefaultPlace, saved: s.inaturalist_default_place_guess ?? '' },
            { field: 'camera_audio_mapping', draft: JSON.stringify(cameraAudioMapping), saved: JSON.stringify(s.camera_audio_mapping || {}) },
            { field: 'garden_motion_cameras', draft: JSON.stringify(gardenMotionCameras), saved: JSON.stringify(s.garden_motion_cameras || []) },
            { field: 'garden_cameras', draft: JSON.stringify(gardenCameras), saved: JSON.stringify(s.garden_cameras || []) },
            { field: 'garden_motion_confidence', draft: gardenMotionConfidence, saved: s.garden_motion_confidence ?? 0.5 },
            { field: 'garden_notifications_enabled', draft: gardenNotificationsEnabled, saved: s.garden_notifications_enabled ?? false },
            { field: 'garden_notification_channels', draft: JSON.stringify(gardenNotificationChannels), saved: JSON.stringify(s.garden_notification_channels ?? []) },
            { field: 'garden_notifications_use_bird_channels', draft: gardenNotificationsUseBirdChannels, saved: s.garden_notifications_use_bird_channels ?? true },
            { field: 'garden_notifications_include_photo', draft: gardenNotificationsIncludePhoto, saved: s.garden_notifications_include_photo ?? true },
            { field: 'garden_automatic_naming', draft: gardenAutomaticNaming, saved: s.garden_automatic_naming ?? true },
            { field: 'garden_naming_threshold', draft: gardenNamingThreshold, saved: s.garden_naming_threshold ?? 0.8 },
            { field: 'garden_domestic_birds', draft: JSON.stringify(gardenDomesticBirds), saved: JSON.stringify(s.garden_domestic_birds ?? []) },
            { field: 'garden_labels', draft: JSON.stringify(gardenLabels.split(/[,;\n]+/).map(label => label.trim().toLowerCase()).filter(Boolean)), saved: JSON.stringify(s.garden_labels || ['cat', 'dog']) },
            { field: 'camera_roles', draft: JSON.stringify(cameraRoles), saved: JSON.stringify(s.camera_roles || {}) },
            { field: 'nest_dedupe_minutes', draft: nestDedupeMinutes, saved: s.nest_dedupe_minutes ?? 30 },
            { field: 'classification_min_confidence', draft: minConfidence, saved: s.classification_min_confidence ?? 0.4 },
            { field: 'live_worker_count', draft: liveWorkerCount, saved: s.live_worker_count ?? null },
            { field: 'background_worker_count', draft: backgroundWorkerCount, saved: s.background_worker_count ?? null },
            { field: 'telemetry_enabled', draft: telemetryEnabled, saved: s.telemetry_enabled ?? true },
            { field: 'telemetry_health_enabled', draft: telemetryHealthEnabled, saved: s.telemetry_health_enabled ?? false },
            { field: 'auth_enabled', draft: authEnabled, saved: s.auth_enabled ?? false },
            { field: 'auth_username', draft: authUsername, saved: s.auth_username || 'admin' },
            { field: 'auth_session_expiry_hours', draft: authSessionExpiryHours, saved: s.auth_session_expiry_hours ?? 168 },
            { field: 'trusted_proxy_hosts', draft: JSON.stringify(effectiveTrustedProxyHosts), saved: JSON.stringify(savedTrustedProxyHosts(s.trusted_proxy_hosts)) },
            { field: 'public_access_enabled', draft: publicAccessEnabled, saved: s.public_access_enabled ?? false },
            { field: 'public_access_show_camera_names', draft: publicAccessShowCameraNames, saved: s.public_access_show_camera_names ?? true },
            { field: 'public_access_show_ai_conversation', draft: publicAccessShowAiConversation, saved: s.public_access_show_ai_conversation ?? false },
            { field: 'public_access_allow_clip_downloads', draft: publicAccessAllowClipDownloads, saved: s.public_access_allow_clip_downloads ?? false },
            { field: 'public_access_show_audio', draft: publicAccessShowAudio, saved: s.public_access_show_audio ?? true },
            { field: 'public_access_show_snapshots', draft: publicAccessShowSnapshots, saved: s.public_access_show_snapshots ?? true },
            { field: 'public_access_show_clips', draft: publicAccessShowClips, saved: s.public_access_show_clips ?? true },
            { field: 'public_access_location_precision', draft: publicAccessLocationPrecision, saved: s.public_access_location_precision ?? 'approximate' },
            { field: 'public_access_historical_days_mode', draft: publicAccessHistoricalDaysMode, saved: normalizePublicDaysMode(s.public_access_historical_days_mode) },
            { field: 'public_access_historical_days', draft: publicAccessHistoricalDays, saved: s.public_access_historical_days ?? 7 },
            { field: 'public_access_media_days_mode', draft: publicAccessMediaDaysMode, saved: normalizePublicDaysMode(s.public_access_media_days_mode) },
            { field: 'public_access_media_historical_days', draft: publicAccessMediaHistoricalDays, saved: s.public_access_media_historical_days ?? 7 },
            { field: 'public_access_rate_limit_per_minute', draft: publicAccessRateLimitPerMinute, saved: s.public_access_rate_limit_per_minute ?? 30 },
            { field: 'public_access_external_base_url', draft: publicAccessExternalBaseUrl, saved: s.public_access_external_base_url ?? '' },

            // Notifications
            { field: 'notifications_discord_enabled', draft: discordEnabled, saved: s.notifications_discord_enabled ?? false },
            { field: 'notifications_discord_webhook_url', draft: discordWebhook, saved: normalizeSecret(s.notifications_discord_webhook_url) },
            { field: 'notifications_discord_username', draft: discordUsername, saved: s.notifications_discord_username || 'YA-WAMF' },

            { field: 'notifications_pushover_enabled', draft: pushoverEnabled, saved: s.notifications_pushover_enabled ?? false },
            { field: 'notifications_pushover_user_key', draft: pushoverUser, saved: normalizeSecret(s.notifications_pushover_user_key) },
            { field: 'notifications_pushover_api_token', draft: pushoverToken, saved: normalizeSecret(s.notifications_pushover_api_token) },
            { field: 'notifications_pushover_priority', draft: pushoverPriority, saved: s.notifications_pushover_priority ?? 0 },
            { field: 'notifications_pushover_device', draft: pushoverDevice, saved: s.notifications_pushover_device ?? '' },

            { field: 'notifications_telegram_enabled', draft: telegramEnabled, saved: s.notifications_telegram_enabled ?? false },
            { field: 'notifications_telegram_bot_token', draft: telegramToken, saved: normalizeSecret(s.notifications_telegram_bot_token) },
            { field: 'notifications_telegram_chat_id', draft: telegramChatId, saved: normalizeSecret(s.notifications_telegram_chat_id) },

            { field: 'notifications_email_enabled', draft: emailEnabled, saved: s.notifications_email_enabled ?? false },
            { field: 'notifications_email_use_oauth', draft: emailUseOAuth, saved: s.notifications_email_use_oauth ?? false },
            { field: 'notifications_email_oauth_provider', draft: emailOAuthProvider || '', saved: s.notifications_email_oauth_provider || '' },
            { field: 'notifications_email_only_on_end', draft: emailOnlyOnEnd, saved: s.notifications_email_only_on_end ?? false },
            { field: 'notifications_email_gmail_client_id', draft: emailGmailClientId, saved: s.notifications_email_gmail_client_id || '' },
            { field: 'notifications_email_gmail_client_secret', draft: emailGmailClientSecret, saved: normalizeSecret(s.notifications_email_gmail_client_secret) },
            { field: 'notifications_email_outlook_client_id', draft: emailOutlookClientId, saved: s.notifications_email_outlook_client_id || '' },
            { field: 'notifications_email_outlook_client_secret', draft: emailOutlookClientSecret, saved: normalizeSecret(s.notifications_email_outlook_client_secret) },
            { field: 'notifications_email_smtp_host', draft: emailSmtpHost, saved: s.notifications_email_smtp_host || '' },
            { field: 'notifications_email_smtp_port', draft: emailSmtpPort, saved: s.notifications_email_smtp_port ?? 587 },
            { field: 'notifications_email_smtp_username', draft: emailSmtpUsername, saved: s.notifications_email_smtp_username || '' },
            { field: 'notifications_email_smtp_password', draft: emailSmtpPassword, saved: normalizeSecret(s.notifications_email_smtp_password) },
            { field: 'notifications_email_smtp_use_tls', draft: emailSmtpUseTls, saved: s.notifications_email_smtp_use_tls ?? true },
            { field: 'notifications_email_from_email', draft: emailFromEmail, saved: s.notifications_email_from_email || '' },
            { field: 'notifications_email_to_email', draft: emailToEmail, saved: s.notifications_email_to_email || '' },
            { field: 'notifications_email_include_snapshot', draft: emailIncludeSnapshot, saved: s.notifications_email_include_snapshot ?? true },
            { field: 'notifications_instance_url', draft: instanceUrl, saved: s.notifications_instance_url || '' },
            { field: 'notifications_link_target', draft: notifyLinkTarget, saved: s.notifications_link_target ?? 'yawamf' },

            { field: 'notification_language', draft: notificationLanguage, saved: s.notification_language ?? 'en' },

            { field: 'notifications_filter_species_mode', draft: filterSpeciesMode, saved: inferNotificationSpeciesMode(s) },
            { field: 'notifications_filter_species_whitelist_structured', draft: JSON.stringify(filterSpeciesEntries), saved: JSON.stringify(notificationSpeciesEntriesForMode(s, inferNotificationSpeciesMode(s))) },
            { field: 'notifications_filter_species_whitelist', draft: JSON.stringify(filterWhitelist), saved: JSON.stringify(inferNotificationSpeciesMode(s) === 'whitelist' ? (s.notifications_filter_species_whitelist || []) : []) },
            { field: 'notifications_filter_min_confidence', draft: filterConfidence, saved: s.notifications_filter_min_confidence ?? 0.7 },
            { field: 'notifications_filter_audio_confirmed_only', draft: filterAudioOnly, saved: s.notifications_filter_audio_confirmed_only ?? false },
            { field: 'notifications_mode', draft: notifyMode, saved: savedNotifyMode(s) },
            { field: 'notifications_notify_on_insert', draft: notifyOnInsert, saved: s.notifications_notify_on_insert ?? true },
            { field: 'notifications_notify_on_update', draft: notifyOnUpdate, saved: s.notifications_notify_on_update ?? false },
            { field: 'notifications_delay_until_video', draft: notifyDelayUntilVideo, saved: s.notifications_delay_until_video ?? false },
            { field: 'notifications_video_fallback_timeout', draft: notifyVideoFallbackTimeout, saved: s.notifications_video_fallback_timeout ?? 45 },
            { field: 'notifications_notification_cooldown_minutes', draft: notifyCooldownMinutes, saved: s.notifications_notification_cooldown_minutes ?? 0 },

            { field: 'bird_model_region_override', draft: birdModelRegionOverride, saved: resolveBirdModelRegionOverrideFromSettings(s.bird_model_region_override) },
            { field: 'bird_crop_inference_provider', draft: birdFinderProvider, saved: s.bird_crop_inference_provider ?? 'auto' },
            { field: 'bird_crop_accurate_detector', draft: birdFinder, saved: parseBirdFinder(s.bird_crop_accurate_detector) }
        ];

        return [
            ...changedFields(checks),
            ...(authPassword.length > 0 || authPasswordConfirm.length > 0 ? ['auth_password'] : []),
            ...sectionChangedFields(appearanceSection, appearanceDraft, s),
            ...sectionChangedFields(accessibilitySection, accessibilityDraft, s),
            ...sectionChangedFields(enrichmentSection, enrichmentDraft, s),
            ...sectionChangedFields(aiSection, aiDraft, s),
            ...locationChangedFields({
                current: {
                    latitude: locationLat,
                    longitude: locationLon,
                    state: locationState,
                    country: locationCountry,
                    automatic: locationAuto,
                    weatherUnitSystem: locationWeatherUnitSystem
                },
                stored: s
            })
        ];
    });
    const unsavedSummary = $derived(summarizeUnsaved(changedSettingFields));
    const isDirty = $derived(unsavedSummary.count > 0);

    const standingErrors = $derived(
        fieldErrors.length > 0 ? standingFieldErrors(fieldErrors, refusedPayload, buildSettingsPayload() as Record<string, unknown>) : []
    );
    provideSettingsFieldErrors({ errorFor: (field) => standingErrors.find((error) => error.field === field) });

    const tabLabel = (tab: SettingsTab): string => $_(`settings.tabs.${tab}`);
    const unsavedTabNames = $derived(
        new Intl.ListFormat($locale || 'en', { type: 'conjunction' }).format(unsavedSummary.tabs.map(tabLabel))
    );

    // Leaving Settings with unsaved edits asks first; moving between its tabs keeps the draft.
    onMount(() => unsavedChanges.hold((to) => {
        if (!isDirty || to.startsWith('/settings')) return null;
        return {
            title: $_('settings.leave.title', { default: 'Leave without saving?' }),
            message: $_('settings.leave.message', {
                values: { count: unsavedSummary.count, tabs: unsavedTabNames },
                default: '{count, plural, one {# change} other {# changes}} in {tabs} will be lost.'
            }),
            confirmLabel: $_('settings.leave.confirm', { default: 'Leave without saving' }),
            tone: 'danger'
        };
    }));

    // A reload or a closed tab cannot use the in-app question; the browser asks its own.
    $effect(() => {
        if (!isDirty) return;
        const keepUnsavedWork = (event: BeforeUnloadEvent) => {
            event.preventDefault();
            event.returnValue = '';
        };
        window.addEventListener('beforeunload', keepUnsavedWork);
        return () => window.removeEventListener('beforeunload', keepUnsavedWork);
    });

    let classifierStatus = $state<ClassifierStatus | null>(null);
    let downloadingModel = $state(false);

    let maintenanceStats = $state<MaintenanceStats | null>(null);
    // Shortening retention deletes history at the next cleanup, so the count is read from the
    // server (read-only) before saving, for the note under the picker and the confirmation.
    const savedRetentionDays = $derived(settingsStore.settings ? (settingsStore.settings.retention_days || 0) : null);
    const retentionShrinking = $derived(savedRetentionDays !== null && retentionShrinks(savedRetentionDays, retentionDays));
    let retentionPreview = $state<{ days: number; count: number | null; counting: boolean } | null>(null);
    const retentionNote = $derived(
        retentionShrinking && retentionPreview?.days === retentionDays
            ? retentionDeletionText(retentionPreview.days, retentionPreview.count, retentionPreview.counting)
            : null
    );
    let cleaningUp = $state(false);
    let clearingFavorites = $state(false);
    let purgingMissingMedia = $state(false);
    let timezoneRepairPreview = $state<TimezoneRepairPreview | null>(null);
    let previewingTimezoneRepair = $state(false);
    let applyingTimezoneRepair = $state(false);

    // Media cache state
    let cacheClips = $state(false);
    let cacheHighQualityEventSnapshots = $state(false);
    let cacheHighQualityEventSnapshotJpegQuality = $state(90);
    let cacheRetentionDays = $state(0);
    let cachePerSpeciesMaximum = $state<number>(0);
    let cacheMaxSizeMb = $state<number>(0);
    let cacheAutomaticMultiBirdScan = $state(false);
    let cacheBirdScanMode = $state<'standard' | 'intensive'>('intensive');
    let cachePerSpeciesMinimum = $state(0);
    let cacheStats = $state<CacheStats | null>(null);
    let cacheStatsError = $state(false);
    let cacheStatsLoading = $state(false);
    let cleaningCache = $state(false);

    // Backfill state
    let backfillDateRange = $state<'day' | 'week' | 'month' | 'custom'>('week');
    let backfillStartDate = $state('');
    let backfillEndDate = $state('');
    let backfilling = $state(false);
    let backfillResult = $state<BackfillResult | null>(null);
    let backfillJob = $state<BackfillJobStatus | null>(null);
    let backfillTotalJobId = $state<string | null>(null);
    let backfillTotal = $state(0);
    let weatherBackfilling = $state(false);
    let weatherBackfillResult = $state<WeatherBackfillResult | null>(null);
    let weatherBackfillJob = $state<BackfillJobStatus | null>(null);
    let weatherBackfillTotalJobId = $state<string | null>(null);
    let weatherBackfillTotal = $state(0);
    let backfillPollInterval: ReturnType<typeof setInterval> | null = null;
    let backfillStatusLoading = false;
    let resettingDatabase = $state(false);
    let clearingFeedback = $state(false);
    let exportingConfigBackup = $state(false);
    let importingConfigBackup = $state(false);
    let analyzingUnknowns = $state(false);
    let analysisTotal = $state(0);
    let analysisStatus = $state<AnalysisStatus | null>(null);

    // Tab navigation — derived from the route so /settings/<tab> deep links survive reload.
    let activeTab = $derived<SettingsTab>(settingsTabFromRoute(currentRoute));

    const parseDateOnly = (value: string): Date | null => {
        const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
        if (!match) return null;
        const year = Number(match[1]);
        const month = Number(match[2]);
        const day = Number(match[3]);
        const date = new Date(year, month - 1, day);
        if (
            date.getFullYear() !== year
            || date.getMonth() !== month - 1
            || date.getDate() !== day
        ) {
            return null;
        }
        date.setHours(0, 0, 0, 0);
        return date;
    };

    const validateBackfillCustomRange = (
        dateRange: 'day' | 'week' | 'month' | 'custom',
        startDate: string,
        endDate: string
    ): string | null => {
        if (dateRange !== 'custom') return null;
        if (!startDate || !endDate) {
            return $_('settings.data.backfill_validation_select_both', { default: 'Select both start and end dates.' });
        }

        const start = parseDateOnly(startDate);
        const end = parseDateOnly(endDate);
        if (!start || !end) {
            return $_('settings.data.backfill_validation_invalid', { default: 'Enter a valid date range.' });
        }

        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (start > today || end > today) {
            return $_('settings.data.backfill_validation_future', { default: 'Future dates are not allowed.' });
        }
        if (start > end) {
            return $_('settings.data.backfill_validation_order', { default: 'Start date must be before or equal to end date.' });
        }
        return null;
    };

    let backfillCustomError = $derived(validateBackfillCustomRange(backfillDateRange, backfillStartDate, backfillEndDate));
    let backfillCustomValid = $derived(backfillDateRange !== 'custom' || !backfillCustomError);

    $effect(() => {
        currentTheme = themeStore.theme;
    });

    onMount(() => subscribeSettingsUpdates(reconcileLocalSettingsUpdate));

    onMount(async () => {
        // Guests should never load the Settings view or call /api/settings.
        if (!authStore.showSettings) {
            authStore.requestLogin();
            return;
        }

        // Settings route canonicalisation lives in a reactive $effect below so it
        // also self-heals after popstate / back-button to non-canonical URLs.

            await Promise.all([
                // The shell has usually just read the settings; opening this page joins that read.
                loadSettings(false, true),
                loadCameras(),
                loadClassifierStatus(),
                loadMaintenanceStats(),
                loadCacheStats(),
                loadTaxonomyStatus(),
                loadVersion(),
                loadBackfillStatus()
            ]);

        // Taxonomy polling lifecycle for the data tab is handled by the activeTab
        // $effect below, so no need to start it explicitly here.

        if ((backfillJob && backfillJob.status === 'running') || (weatherBackfillJob && weatherBackfillJob.status === 'running')) {
            startBackfillPolling();
        }
    });

    $effect(() => {
        if (isDirty) return;
        return pageRefreshAction.register(async () => {
            await Promise.all([loadSettings(), loadClassifierStatus()]);
        });
    });

    // A harness can finish in another tab, and isolated workers can start after
    // the completion response. Keep the visible runtime current without touching
    // the settings form or accumulating overlapping background reads.
    $effect(() => {
        if (activeTab !== 'detection' || !authStore.showSettings) return;
        const stop = untrack(() => startVisiblePoll({
            read: () => (classifierStatusReads === 0 ? loadClassifierStatus() : undefined),
            delayMs: () => REFRESH_CADENCE_MS.classifierRuntime
        }));
        return () => {
            stop();
            classifierStatusRequest += 1;
        };
    });

    $effect(() => {
        const status = analysisQueueStatusStore.analysisStatus;
        if (!status) return;
        untrack(() => applyAnalysisStatus(status));
    });

    function handleTabChange(tab: SettingsTab) {
        const path = settingsTabPath(tab);
        if (onNavigate) onNavigate(path);
        else window.history.pushState(null, '', toAppPath(path));
    }

    // A tab's code arrives after the tab is chosen, so a link that lands on one of its fields waits
    // for the field to exist. A tab that fails to load shows its own retry; nothing is focused then.
    const FIELD_WAIT_FRAMES = 60;
    async function fieldInOpenedTab(loadTab: () => Promise<unknown>, find: () => HTMLElement | null): Promise<HTMLElement | null> {
        try {
            await loadTab();
        } catch {
            return null;
        }
        for (let frame = 0; frame < FIELD_WAIT_FRAMES; frame += 1) {
            await tick();
            const field = find();
            if (field) return field;
            await new Promise((resolve) => requestAnimationFrame(resolve));
        }
        return null;
    }

    // The range filter's next steps live in Integrations; land on the field itself, not the top of the tab.
    // A field hidden behind its switch (the key while eBird is off, coordinates while the location
    // is automatic) falls back to that switch, which is the step that reveals it.
    async function openIntegrationField(...selectors: string[]): Promise<void> {
        handleTabChange('integrations');
        const field = await fieldInOpenedTab(loadIntegrationSettings, () =>
            selectors.map((selector) => document.querySelector<HTMLElement>(selector)).find(Boolean) ?? null
        );
        field?.scrollIntoView({ block: 'center' });
        field?.focus({ preventScroll: true });
    }

    // Beta features names the Garden cameras but they are chosen in Connection, so the link lands
    // on the camera list itself rather than at the top of a tab whose first card is Frigate.
    async function openCameraSettings(): Promise<void> {
        handleTabChange('connection');
        const list = await fieldInOpenedTab(loadConnectionSettings, () => document.getElementById('settings-camera-list'));
        list?.scrollIntoView({ block: 'start' });
        list?.focus({ preventScroll: true });
    }

    // Drive taxonomy status from the derived active tab so router-driven changes
    // (back/forward, deep links) still flip the lifecycle correctly. Opening the tab reads
    // the status once; polling runs only while a repair runs, not every 3 s for as long as
    // the tab stays open.
    $effect(() => {
        if (activeTab === 'data') {
            void loadTaxonomyStatus();
        } else {
            stopTaxonomyPolling();
        }
    });

    // Self-heal non-canonical routes that arrive after mount (popstate from a
    // bookmark to /settings/foo, manual address-bar edit, etc.). canonicalSettingsPath
    // returns null for already-canonical inputs so this is a no-op in steady state.
    $effect(() => {
        if (typeof window === 'undefined') return;
        if (!currentRoute || !currentRoute.startsWith('/settings')) return;
        const canonical = canonicalSettingsPath(currentRoute, window.location.hash.slice(1));
        if (canonical && canonical !== currentRoute) {
            if (onNavigate) onNavigate(canonical, { replace: true });
            else window.history.replaceState(null, '', toAppPath(canonical));
        }
    });

    onDestroy(() => {
        // The font and colour preview live outside this page; leaving without saving takes them
        // back to what is saved, as it does for every other unsaved edit.
        const saved = settingsStore.settings;
        if (saved) {
            const { fontTheme, colorTheme } = appearanceSection.decode(saved);
            themeStore.setFontTheme(fontTheme);
            themeStore.setColorTheme(colorTheme);
        }
        stopTaxonomyPolling();
        if (backfillPollInterval) clearInterval(backfillPollInterval);
    });

    function startTaxonomyPolling() {
        if (taxonomyPollInterval) return;
        taxonomyPollInterval = setInterval(() => {
            if (!document.hidden) void loadTaxonomyStatus();
        }, 3000);
    }

    function stopTaxonomyPolling() {
        if (!taxonomyPollInterval) return;
        clearInterval(taxonomyPollInterval);
        taxonomyPollInterval = undefined;
    }

    async function loadTaxonomyStatus() {
        if (taxonomyStatusLoading) return;
        taxonomyStatusLoading = true;
        try {
            taxonomyStatus = await fetchTaxonomyStatus();
            if (taxonomyStatus.is_running) {
                taxonomyAwaitingStartUntil = 0;
                startTaxonomyPolling();
                jobProgressStore.upsertRunning({
                    id: 'taxonomy:sync',
                    kind: 'taxonomy_sync',
                    title: $_('settings.data.taxonomy_title'),
                    message: taxonomyStatus.message || taxonomyStatus.current_item || $_('settings.data.taxonomy_syncing'),
                    current: taxonomyStatus.processed,
                    total: taxonomyStatus.total,
                    source: 'poll'
                });
            } else if (taxonomyStatus.progress_state === 'failed') {
                taxonomyAwaitingStartUntil = 0;
                stopTaxonomyPolling();
                jobProgressStore.markFailed({
                    id: 'taxonomy:sync',
                    kind: 'taxonomy_sync',
                    title: $_('settings.data.taxonomy_title'),
                    message: taxonomyStatus.error || taxonomyStatus.message || $_('settings.data.taxonomy_failed'),
                    current: taxonomyStatus.processed,
                    total: taxonomyStatus.total,
                    source: 'poll'
                });
            } else if (taxonomyStatus.progress_state === 'completed' && taxonomyStatus.processed > 0) {
                taxonomyAwaitingStartUntil = 0;
                stopTaxonomyPolling();
                jobProgressStore.markCompleted({
                    id: 'taxonomy:sync',
                    kind: 'taxonomy_sync',
                    title: $_('settings.data.taxonomy_title'),
                    current: taxonomyStatus.processed,
                    total: taxonomyStatus.total,
                    source: 'poll'
                });
            } else if (Date.now() >= taxonomyAwaitingStartUntil) {
                stopTaxonomyPolling();
                jobProgressStore.closeActiveByPrefix('taxonomy:', 'stale');
            }
        } catch (e) {
            console.error('Failed to load taxonomy status', e);
        } finally {
            taxonomyStatusLoading = false;
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
            taxonomyAwaitingStartUntil = Date.now() + TAXONOMY_START_GRACE_MS;
            startTaxonomyPolling();
            await loadTaxonomyStatus();
            notify('success', $_('settings.data.taxonomy_syncing'));
        } catch (e) {
            taxonomyAwaitingStartUntil = 0;
            notify('error', $_('settings.data.taxonomy_sync_error', { values: { error: getErrorMessage(e) } }));
        } finally {
            syncingTaxonomy = false;
        }
    }

    async function handlePreviewTimezoneRepair() {
        previewingTimezoneRepair = true;
        try {
            timezoneRepairPreview = await fetchTimezoneRepairPreview();
            const count = timezoneRepairPreview.summary.repair_candidate_count;
            notify('success', count > 0
                    ? $_('settings.data.timezone_repair_preview_found', {
                        default: '{count, plural, one {# detection can be repaired.} other {# detections can be repaired.}}',
                        values: { count }
                    })
                    : $_('settings.data.timezone_repair_preview_none', {
                        default: 'No safe timezone repairs were found.'
                    }));
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.timezone_repair_error', {
                    default: 'Timezone repair scan failed.'
                }));
        } finally {
            previewingTimezoneRepair = false;
        }
    }

    async function handleApplyTimezoneRepair() {
        const confirmed = await confirmAction({
            title: $_('settings.data.timezone_repair_title', { default: 'Timezone Repair' }),
            message: $_('settings.data.timezone_repair_confirm', {
                default: 'Apply safe timezone repairs to the previewed detections?'
            }),
            confirmLabel: $_('settings.data.timezone_repair_apply_button', { default: 'Apply Timezone Repair' }),
            tone: 'default'
        });
        if (!confirmed) return;

        applyingTimezoneRepair = true;
        try {
            const result = await applyTimezoneRepair();
            timezoneRepairPreview = result.preview;
            notify('success', $_('settings.data.timezone_repair_apply_success', {
                    default: 'Repaired {count, plural, one {# detection} other {# detections}}.',
                    values: { count: result.repaired_count }
                }));
            await loadMaintenanceStats();
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.timezone_repair_error', {
                    default: 'Timezone repair failed.'
                }));
        } finally {
            applyingTimezoneRepair = false;
        }
    }

    async function loadMaintenanceStats() {
        try {
            maintenanceStats = await fetchMaintenanceStats();
        } catch (e) {
            console.error('Failed to load maintenance stats', e);
        }
    }

    async function countRetentionDeletions(days: number): Promise<number | null> {
        try {
            return (await fetchMaintenanceStats(days)).preview_detections_to_cleanup ?? null;
        } catch (e) {
            console.error('Failed to count detections for the new retention', e);
            return null;
        }
    }

    $effect(() => {
        if (!retentionShrinking) {
            retentionPreview = null;
            return;
        }
        const days = retentionDays;
        let current = true;
        retentionPreview = { days, count: null, counting: true };
        void countRetentionDeletions(days).then((count) => {
            if (current) retentionPreview = { days, count, counting: false };
        });
        return () => {
            current = false;
        };
    });

    /** What saving `days` of history deletes, worded for the cleanup rule the server applies. */
    function retentionDeletionText(days: number, count: number | null, counting: boolean): string {
        if (counting) {
            return $_('settings.data.retention_shrink_counting', {
                values: { days },
                default: 'Counting the detections older than {days} days…'
            });
        }
        const automatic = maintenanceStats?.automatic_cleanup !== false;
        let consequence: string;
        if (!automatic) {
            consequence = count === null
                ? $_('settings.data.retention_shrink_manual_uncounted', {
                    values: { days },
                    default: 'Automatic cleanup is off, so saving deletes nothing by itself. Purge Old Records would then delete every detection older than {days} days.'
                })
                : $_('settings.data.retention_shrink_manual', {
                    values: { count, days },
                    default: 'Automatic cleanup is off, so saving deletes nothing by itself. Purge Old Records would then delete {count, plural, one {# detection} other {# detections}} older than {days} days.'
                });
        } else {
            consequence = count === null
                ? $_('settings.data.retention_shrink_uncounted', {
                    values: { days },
                    default: 'Saving this permanently deletes every detection older than {days} days at the next cleanup (on restart, then every 24 hours).'
                })
                : $_('settings.data.retention_shrink_note', {
                    values: { count, days },
                    default: 'Saving this permanently deletes {count, plural, one {# detection} other {# detections}} older than {days} days at the next cleanup (on restart, then every 24 hours).'
                });
        }
        const floor = maintenanceStats?.kept_newest_per_species ?? 0;
        const kept = floor > 0
            ? $_('settings.data.retention_shrink_kept_floor', {
                values: { floor },
                default: 'Favourites and the newest {floor, plural, one {# detection} other {# detections}} of each species are kept. Older BirdNET-Go audio and Garden animal records are deleted too.'
            })
            : $_('settings.data.retention_shrink_kept', {
                default: 'Favourites are kept. Older BirdNET-Go audio and Garden animal records are deleted too.'
            });
        return `${consequence} ${kept}`;
    }

    /** Asks before a save that deletes history. False means the owner kept what they have. */
    async function confirmRetentionChange(): Promise<boolean> {
        if (!retentionShrinking || maintenanceStats?.automatic_cleanup === false) return true;
        const days = retentionDays;
        // Counted again at the moment of asking, so the number is not minutes stale.
        const count = await countRetentionDeletions(days);
        if (count === 0) return true;
        return confirmAction({
            title: $_('settings.data.retention_confirm_title', { default: 'Delete older history?' }),
            message: retentionDeletionText(days, count, false),
            confirmLabel: count === null
                ? $_('settings.data.retention_confirm_uncounted', { default: 'Save and delete older history' })
                : $_('settings.data.retention_confirm_button', {
                    values: { count },
                    default: 'Save and delete {count, plural, one {# detection} other {# detections}}'
                })
        });
    }

    async function handleCleanup() {
        // Deletes history outright, so it asks first like every other destructive action.
        // With unlimited retention the server deletes nothing, so there is nothing to ask.
        const days = maintenanceStats?.retention_days ?? retentionDays;
        if (days > 0) {
            const confirmed = await confirmAction({
                title: $_('settings.data.purge_button', { default: 'Purge Old Records' }),
                message: $_('settings.data.purge_confirm', {
                    values: { count: maintenanceStats?.detections_to_cleanup ?? 0, days },
                    default: "Permanently delete {count, plural, one {# detection} other {# detections}} and the BirdNET-Go audio older than {days} days? Favourites and each species' newest kept visits stay. This cannot be undone."
                }),
                confirmLabel: $_('settings.data.purge_button', { default: 'Purge Old Records' })
            });
            if (!confirmed) return;
        }
        cleaningUp = true;
        try {
            const result = await runCleanup();
            if (result.status === 'completed') {
                notify('success', $_('settings.data.cleanup_success', { values: { count: result.deleted_count } }));
            } else {
                notify('success', result.message || $_('settings.data.cleanup_none'));
            }
            await loadMaintenanceStats();
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.cleanup_error'));
        } finally {
            cleaningUp = false;
        }
    }

    async function handleClearFavorites() {
        const confirmed = await confirmAction({
            title: $_('settings.data.clear_favorites_button', { default: 'Delete All Favorites' }),
            message: $_('settings.data.clear_favorites_confirm', {
                default: 'Remove all favorite markers? This cannot be undone.'
            }),
            confirmLabel: $_('settings.data.clear_favorites_button', { default: 'Delete All Favorites' })
        });
        if (!confirmed) return;

        clearingFavorites = true;
        try {
            const result = await clearAllFavorites();
            if ((result.deleted_count ?? 0) > 0) {
                notify('success', $_('settings.data.clear_favorites_success', { values: { count: result.deleted_count } }));
            } else {
                notify('success', result.message || $_('settings.data.clear_favorites_none'));
            }
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.clear_favorites_error'));
        } finally {
            clearingFavorites = false;
        }
    }

    async function handlePurgeMissingMedia() {
        const confirmed = await confirmAction({
            title: $_('settings.data.purge_missing_media', { default: 'Run media integrity scan now' }),
            message: $_('settings.data.purge_missing_media_confirm', {
                default: 'Scan detections whose Frigate event, clip, or snapshot is missing and apply the configured policy?'
            }),
            confirmLabel: $_('settings.data.purge_missing_media', { default: 'Run media integrity scan now' })
        });
        if (!confirmed) return;

        purgingMissingMedia = true;
        try {
            const result = await purgeMissingMedia();
            notify('success', formatMissingMediaScanResult(result));
            await loadMaintenanceStats();
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.cleanup_error'));
        } finally {
            purgingMissingMedia = false;
        }
    }

    function formatMissingMediaScanResult(result: PurgeMissingMediaResult): string {
        return $_('settings.data.purge_missing_scan_success', {
            values: {
                checked: (result.checked ?? 0).toLocaleString(),
                missing: (result.missing ?? 0).toLocaleString(),
                deleted: (result.deleted_count ?? 0).toLocaleString(),
                marked: (result.marked_missing_count ?? 0).toLocaleString(),
                kept: (result.kept_count ?? 0).toLocaleString(),
                restored: (result.cleared_missing_count ?? 0).toLocaleString(),
                errors: (result.errors ?? 0).toLocaleString()
            },
            default: 'Scan complete: checked {checked}, missing {missing}, deleted {deleted}, marked missing {marked}, kept {kept}, restored {restored}. Unable to check {errors}; their saved state was preserved.'
        });
    }

    async function handleResetDatabase() {
        let confirmMsg = 'DANGER: This will delete ALL detections, clear the media cache and remove every archived favourite. This action cannot be undone. Are you sure?';
        try {
            confirmMsg = $_('settings.danger.confirm');
        } catch (e) {
            console.warn('Translation lookup failed, using fallback', e);
        }

        const confirmed = await confirmAction({
            title: $_('settings.danger.reset_button', { default: 'Reset Database & Cache' }),
            message: confirmMsg,
            confirmLabel: $_('settings.danger.reset_button', { default: 'Reset Database & Cache' })
        });
        if (!confirmed) {
            return;
        }

        resettingDatabase = true;
        toastStore.show($_('settings.danger.resetting'), 'info');
        try {
            const result = await resetDatabase();
            notify('success', result.message);
            toastStore.success(result.message || $_('settings.danger.reset_button'));
            await Promise.all([loadMaintenanceStats(), loadCacheStats(), loadClassifierStatus()]);
        } catch (e) {
            const errorMessage = getErrorMessage(e) || $_('settings.data.reset_error');
            notify('error', errorMessage);
            toastStore.error(errorMessage);
        } finally {
            resettingDatabase = false;
        }
    }

    async function handleClearFeedback() {
        let confirmMsg = 'Are you sure you want to clear all personalized re-ranking data? This will revert the AI back to its baseline accuracy and cannot be undone.';
        try {
            confirmMsg = $_('settings.danger.clear_feedback_confirm', { default: confirmMsg });
        } catch (e) {
            console.warn('Translation lookup failed, using fallback', e);
        }

        const confirmed = await confirmAction({
            title: $_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' }),
            message: confirmMsg,
            confirmLabel: $_('settings.danger.clear_feedback_button', { default: 'Clear Personalization Data' })
        });
        if (!confirmed) {
            return;
        }

        clearingFeedback = true;
        try {
            const result = await clearClassificationFeedback();
            notify('success', result.message);
            toastStore.success(result.message || 'Personalization data cleared');
        } catch (e) {
            const errorMessage = getErrorMessage(e) || 'Failed to clear personalization data';
            notify('error', errorMessage);
            toastStore.error(errorMessage);
        } finally {
            clearingFeedback = false;
        }
    }

    async function loadCacheStats() {
        if (cacheStatsLoading) return;
        cacheStatsLoading = true;
        cacheStatsError = false;
        try {
            cacheStats = await fetchCacheStats();
            cacheStatsError = false;
        } catch (e) {
            // Keep any earlier figure rather than replacing it with nothing;
            // DataSettings shows an honest unavailable state, never 0 MB.
            cacheStatsError = true;
            console.error('Failed to load cache stats', e);
        } finally {
            cacheStatsLoading = false;
        }
    }

    async function handleCacheCleanup() {
        // One click once deleted 59 GB here without a word. It asks first now.
        const confirmed = await confirmAction({
            title: $_('settings.data.cache_clear_button', { default: 'Clear Cached Files' }),
            message: $_('settings.data.cache_cleanup_confirm', {
                default: "Delete cached photos and clips older than the retention period, and cached files that no longer belong to a detection? Favourites and each species' newest kept visits stay. This cannot be undone."
            }),
            confirmLabel: $_('settings.data.cache_clear_button', { default: 'Clear Cached Files' })
        });
        if (!confirmed) return;
        cleaningCache = true;
        try {
            const result = await runCacheCleanup();
            if (result.status === 'completed') {
                const freed = result.bytes_freed > 1024 * 1024
                    ? `${(result.bytes_freed / (1024 * 1024)).toFixed(1)} MB`
                    : `${(result.bytes_freed / 1024).toFixed(1)} KB`;
                notify('success', $_('settings.data.cache_cleanup_success', { values: { snapshots: result.snapshots_deleted, clips: result.clips_deleted, freed } }));
            } else {
                notify('success', result.message || $_('settings.data.cleanup_none'));
            }
            await loadCacheStats();
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.cache_cleanup_error'));
        } finally {
            cleaningCache = false;
        }
    }

    async function handleBackfill() {
        if (!backfillCustomValid) {
            notify('error', backfillCustomError || $_('settings.data.backfill_error'));
            return;
        }
        backfilling = true;
        backfillResult = null;
        backfillJob = null;
        backfillTotalJobId = null;
        backfillTotal = 0;
        try {
            const job = await startBackfillJob({
                date_range: backfillDateRange,
                start_date: backfillDateRange === 'custom' ? backfillStartDate : undefined,
                end_date: backfillDateRange === 'custom' ? backfillEndDate : undefined
            });
            backfillJob = job;
            const scoped = mergeBackfillTotal(backfillTotalJobId, backfillTotal, job);
            backfillTotalJobId = scoped.jobId;
            backfillTotal = scoped.total;
            startBackfillPolling();
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.backfill_error'));
        }
    }

    async function handleWeatherBackfill() {
        if (!backfillCustomValid) {
            notify('error', backfillCustomError || $_('settings.data.weather_backfill_error'));
            return;
        }
        weatherBackfilling = true;
        weatherBackfillResult = null;
        weatherBackfillJob = null;
        weatherBackfillTotalJobId = null;
        weatherBackfillTotal = 0;
        try {
            const job = await startWeatherBackfillJob({
                date_range: backfillDateRange,
                start_date: backfillDateRange === 'custom' ? backfillStartDate : undefined,
                end_date: backfillDateRange === 'custom' ? backfillEndDate : undefined,
                only_missing: true
            });
            weatherBackfillJob = job;
            const scoped = mergeBackfillTotal(weatherBackfillTotalJobId, weatherBackfillTotal, job);
            weatherBackfillTotalJobId = scoped.jobId;
            weatherBackfillTotal = scoped.total;
            startBackfillPolling();
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.weather_backfill_error'));
        }
    }

    async function handleExportConfigBackup() {
        const confirmed = await confirmAction({
            title: $_('settings.data.config_backup_export', { default: 'Export Config' }),
            message: $_('settings.data.config_backup_export_confirm', {
                default: 'This backup includes secrets such as tokens, webhooks, passwords, and auth secrets. Store it somewhere private?'
            }),
            confirmLabel: $_('settings.data.config_backup_export_confirm_button', { default: 'Export backup' }),
            tone: 'default'
        });
        if (!confirmed) return;

        exportingConfigBackup = true;
        try {
            const { blob, filename } = await exportConfigBackup();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            notify('success', $_('settings.data.config_backup_exported', { default: 'Configuration backup exported.' }));
        } catch (e) {
            notify('error', getErrorMessage(e) || $_('settings.data.config_backup_export_error', { default: 'Failed to export configuration backup' }));
        } finally {
            exportingConfigBackup = false;
        }
    }

    async function handleImportConfigBackup(file: File) {
        const confirmed = await confirmAction({
            title: $_('settings.data.config_backup_import', { default: 'Import Config' }),
            message: $_('settings.data.config_backup_import_confirm', {
                default: 'Importing this backup replaces the current YA-WAMF configuration, including secrets. This installation keeps its own sign-in sessions and the key for its stored OAuth tokens. Continue?'
            }),
            confirmLabel: $_('settings.data.config_backup_import_confirm_button', { default: 'Replace configuration' })
        });
        if (!confirmed) return;

        importingConfigBackup = true;
        try {
            const payload = JSON.parse(await file.text());
            const result = await importConfigBackup(payload);
            await settingsStore.load();
            await loadSettings(true);
            notify('success', $_('settings.data.config_backup_imported', {
                    values: { count: result.changed_fields.length },
                    default: 'Configuration backup imported ({count, plural, one {# section changed} other {# sections changed}}). Run a backfill when you are ready.'
                }));
        } catch (e) {
            const text = e instanceof SyntaxError
                ? $_('settings.data.config_backup_invalid_json', { default: 'The selected file is not valid JSON.' })
                : getErrorMessage(e) || $_('settings.data.config_backup_import_error', { default: 'Failed to import configuration backup' });
            notify('error', text);
        } finally {
            importingConfigBackup = false;
        }
    }

    function startBackfillPolling() {
        if (backfillPollInterval) {
            clearInterval(backfillPollInterval);
        }
        void loadBackfillStatus();
        backfillPollInterval = setInterval(() => {
            if (!document.hidden) void loadBackfillStatus();
        }, 2000);
    }

    async function loadBackfillStatus() {
        if (backfillStatusLoading) return;
        backfillStatusLoading = true;
        try {
            const [detections, weather] = await Promise.all([
                getBackfillStatus('detections'),
                getBackfillStatus('weather')
            ]);

            if (detections) {
                const previousJob = backfillJob;
                backfillJob = detections;
                backfillResult = {
                    status: detections.status,
                    processed: safeCount(detections.processed),
                    new_detections: safeCount(detections.new_detections),
                    updated: safeCount(detections.updated),
                    skipped: safeCount(detections.skipped),
                    errors: safeCount(detections.errors),
                    skipped_reasons: detections.skipped_reasons ?? {},
                    error_reasons: detections.error_reasons ?? {},
                    message: detections.message || ''
                };
                const scoped = mergeBackfillTotal(backfillTotalJobId, backfillTotal, detections);
                backfillTotalJobId = scoped.jobId;
                backfillTotal = scoped.total;
                backfilling = detections.status === 'running';
                if (detections.status === 'completed') {
                    if (emitTerminalBackfillToast('detections', detections, previousJob, 'success', 'Backfill complete')) {
                        await loadMaintenanceStats();
                    }
                } else if (detections.status === 'failed') {
                    emitTerminalBackfillToast('detections', detections, previousJob, 'error', 'Backfill failed');
                }
                reconcileBackfillNotification('detections', detections, scoped.total);
            } else {
                backfillJob = null;
                backfillResult = null;
                backfillTotalJobId = null;
                backfillTotal = 0;
                backfilling = false;
                reconcileBackfillNotification('detections', detections, 0);
            }

            if (weather) {
                const previousJob = weatherBackfillJob;
                weatherBackfillJob = weather;
                weatherBackfillResult = {
                    status: weather.status,
                    processed: safeCount(weather.processed),
                    updated: safeCount(weather.updated),
                    skipped: safeCount(weather.skipped),
                    errors: safeCount(weather.errors),
                    error_reasons: weather.error_reasons ?? {},
                    message: weather.message || ''
                };
                const scoped = mergeBackfillTotal(weatherBackfillTotalJobId, weatherBackfillTotal, weather);
                weatherBackfillTotalJobId = scoped.jobId;
                weatherBackfillTotal = scoped.total;
                weatherBackfilling = weather.status === 'running';
                if (weather.status === 'completed') {
                    emitTerminalBackfillToast('weather', weather, previousJob, 'success', 'Weather backfill complete');
                } else if (weather.status === 'failed') {
                    emitTerminalBackfillToast('weather', weather, previousJob, 'error', 'Weather backfill failed');
                }
                reconcileBackfillNotification('weather', weather, scoped.total);
            } else {
                weatherBackfillJob = null;
                weatherBackfillResult = null;
                weatherBackfillTotalJobId = null;
                weatherBackfillTotal = 0;
                weatherBackfilling = false;
                reconcileBackfillNotification('weather', weather, 0);
            }

            const detectionsDone = !backfillJob || backfillJob.status !== 'running';
            const weatherDone = !weatherBackfillJob || weatherBackfillJob.status !== 'running';
            if (detectionsDone && weatherDone && backfillPollInterval) {
                clearInterval(backfillPollInterval);
                backfillPollInterval = null;
            }
        } catch (e) {
            console.error('Failed to load backfill status', e);
            jobDiagnosticsStore.recordError({
                source: 'job',
                component: 'backfill_status',
                stage: 'poll',
                reasonCode: 'status_fetch_failed',
                message: toErrorMessage(e, 'Failed to load backfill status'),
                severity: 'warning',
                context: { route: '/api/backfill/status' }
            });
        } finally {
            backfillStatusLoading = false;
        }
    }

    async function handleAnalyzeUnknowns() {
        analyzingUnknowns = true;
        try {
            const result = await analyzeUnknowns();
            notify('success', result.message);
            if (result.count > 0 || (result.skipped_duplicate ?? 0) > 0 || (result.dropped_full ?? 0) > 0) {
                await analysisQueueStatusStore.refresh();
                const refreshedStatus = analysisQueueStatusStore.analysisStatus;
                const remaining = (refreshedStatus?.pending ?? 0) + (refreshedStatus?.active ?? 0);
                if (analysisTotal === 0 || analysisTotal < remaining) {
                    analysisTotal = remaining;
                }
            }
        } catch (e) {
            notify('error', getErrorMessage(e) || 'Analysis failed');
        } finally {
            analyzingUnknowns = false;
        }
    }

    function applyAnalysisStatus(status: AnalysisStatus): void {
        analysisStatus = status;
        const remaining = status.pending + status.active;
        if (remaining > 0 && (analysisTotal === 0 || analysisTotal < remaining)) {
            analysisTotal = remaining;
        } else if (remaining === 0) {
            analysisTotal = 0;
        }
    }

    // Reads only the live runtime, never the settings form, so a refresh after a
    // compatibility check or a model switch keeps the owner's unsaved edits. The
    // newest request wins, so a slow earlier reply cannot restore a stale provider.
    let classifierStatusRequest = 0;
    let classifierStatusReads = 0;
    // The provider as loadSettings last put it in the form. The shared settings
    // store can be refreshed independently, so it cannot tell whether the form
    // still shows the loaded provider or one the owner has picked since.
    let loadedInferenceProvider: unknown = undefined;
    let loadedSetupSettings: SettingsPayload | null = null;
    let settingsFormLoads = 0;

    async function loadClassifierStatus(): Promise<boolean> {
        const request = ++classifierStatusRequest;
        const formLoad = settingsFormLoads;
        classifierStatusReads += 1;
        try {
            const status = await fetchClassifierStatus();
            if (request === classifierStatusRequest) {
                classifierStatus = status;
                // A status read that started before the form was last loaded, or
                // that lands mid-save, may report a preference older than the form's.
                if (formLoad === settingsFormLoads && !saving) adoptSavedInferenceProvider(status.selected_provider);
            }
            return true;
        } catch (e) {
            console.error('Failed to load classifier status', e);
            return false;
        } finally {
            classifierStatusReads -= 1;
        }
    }

    // Activating a model saves that model's provider on the server. Without this,
    // the form and its saved baseline keep the old provider, and the next save of
    // an unrelated edit writes it back over the new one.
    function adoptSavedInferenceProvider(reportedProvider: unknown): void {
        const update = reconcileSavedInferenceProvider(reportedProvider, loadedInferenceProvider, inferenceProvider);
        if (!update) return;
        loadedInferenceProvider = update.saved;
        inferenceProvider = update.form;
        settingsStore.patch({ inference_provider: update.saved });
    }

    // A re-run overlays this form. Adopt confirmed wizard writes only for fields
    // the owner has not edited here, so an unrelated later save cannot undo setup.
    function reconcileLocalSettingsUpdate(patch: SettingsUpdate): void {
        if (saving || !loadedSetupSettings) return;
        const baseline = loadedSetupSettings;
        const confirmed: Partial<SettingsPayload> = {};
        function adopt<K extends keyof SettingsPayload>(key: K, current: SettingsPayload[K], previous: SettingsPayload[K], write: (value: SettingsPayload[K]) => void) {
            const saved = patch[key as keyof SettingsUpdate];
            if (saved === undefined || saved === null) return;
            const value = saved as SettingsPayload[K];
            if (JSON.stringify(current) === JSON.stringify(previous)) write(value);
            confirmed[key] = value;
        }
        adopt('frigate_url', frigateUrl, baseline.frigate_url, value => frigateUrl = value);
        adopt('mqtt_server', mqttServer, baseline.mqtt_server, value => mqttServer = value);
        adopt('mqtt_port', mqttPort, baseline.mqtt_port, value => mqttPort = value);
        adopt('mqtt_auth', mqttAuth, baseline.mqtt_auth, value => mqttAuth = value);
        adopt('mqtt_username', mqttUsername, baseline.mqtt_username || '', value => mqttUsername = value || '');
        adopt('cameras', selectedCameras, baseline.cameras || [], value => selectedCameras = value);
        adopt('media_cache_high_quality_event_snapshots', cacheHighQualityEventSnapshots, baseline.media_cache_high_quality_event_snapshots ?? false, value => cacheHighQualityEventSnapshots = value);
        adopt('birdnet_enabled', birdnetEnabled, baseline.birdnet_enabled ?? true, value => birdnetEnabled = value);
        adopt('birdnet_url', birdnetUrl, baseline.birdnet_url || '', value => birdnetUrl = value);
        adopt('ebird_enabled', ebirdEnabled, baseline.ebird_enabled ?? false, value => ebirdEnabled = value ?? false);
        adopt('inaturalist_enabled', inaturalistEnabled, baseline.inaturalist_enabled ?? false, value => inaturalistEnabled = value ?? false);
        adopt('birdweather_enabled', birdweatherEnabled, baseline.birdweather_enabled ?? false, value => birdweatherEnabled = value);
        adopt('llm_enabled', aiDraft.llmEnabled, baseline.llm_enabled ?? false, value => aiDraft = { ...aiDraft, llmEnabled: value });
        adopt('telemetry_enabled', telemetryEnabled, baseline.telemetry_enabled ?? true, value => telemetryEnabled = value);
        // Coordinates form one input: never combine half an unsaved pair with setup.
        if (patch.location_latitude !== undefined && patch.location_longitude !== undefined) {
            if (locationLat === (baseline.location_latitude ?? null) && locationLon === (baseline.location_longitude ?? null)) {
                locationLat = patch.location_latitude;
                locationLon = patch.location_longitude;
            }
            confirmed.location_latitude = patch.location_latitude;
            confirmed.location_longitude = patch.location_longitude;
        }
        if (patch.inference_provider !== undefined) adoptSavedInferenceProvider(patch.inference_provider);
        if (patch.mqtt_password && patch.mqtt_password !== '***REDACTED***') {
            mqttPasswordSaved = !mqttPassword;
            confirmed.mqtt_password = '***REDACTED***';
        }
        loadedSetupSettings = { ...baseline, ...confirmed };
        settingsStore.patch(confirmed);
    }

    async function loadRecordingClipCapability() {
        recordingClipCapabilityLoading = true;
        try {
            recordingClipCapability = await fetchRecordingClipCapability();
        } catch (e) {
            console.error('Failed to load recording clip capability', e);
            recordingClipCapability = null;
        } finally {
            recordingClipCapabilityLoading = false;
        }
    }

    // Puts every saved value into the form. Loading uses it after a read; Discard uses it with the
    // copy already held, so throwing changes away needs no request and cannot fail.
    function applySavedSettings(settings: SettingsPayload): void {
        frigateUrl = settings.frigate_url;
        frigateIngestLabels = (settings.frigate_ingest_labels ?? ['bird']).join(', ');
        frigateExternalUrl = settings.frigate_external_url || '';
        mqttServer = settings.mqtt_server;
        mqttPort = settings.mqtt_port;
        mqttAuth = settings.mqtt_auth;
        mqttUsername = settings.mqtt_username || '';
        if (settings.mqtt_password === '***REDACTED***') {
            mqttPasswordSaved = true;
            mqttPassword = '';
        } else {
            mqttPasswordSaved = false;
            mqttPassword = settings.mqtt_password || '';
        }
        birdnetEnabled = settings.birdnet_enabled ?? true;
        birdnetUrl = settings.birdnet_url || '';
        birdnetExternalUrl = settings.birdnet_external_url || '';
        audioTopic = settings.audio_topic || 'birdnet/text';
        cameraAudioMapping = settings.camera_audio_mapping || {};
        if (typeof cameraAudioMapping !== 'object' || Array.isArray(cameraAudioMapping)) {
            cameraAudioMapping = {};
        }
        cameraRoles = settings.camera_roles || {};
        if (typeof cameraRoles !== 'object' || Array.isArray(cameraRoles)) {
            cameraRoles = {};
        }
        gardenCameras = settings.garden_cameras || [];
        gardenMotionCameras = settings.garden_motion_cameras || [];
        gardenLabels = (settings.garden_labels || ['cat', 'dog']).join(', ');
        gardenMotionConfidence = settings.garden_motion_confidence ?? 0.5;
        gardenNotificationsEnabled = settings.garden_notifications_enabled ?? false;
        gardenNotificationChannels = settings.garden_notification_channels ?? [];
        gardenNotificationsUseBirdChannels = settings.garden_notifications_use_bird_channels ?? true;
        gardenNotificationsIncludePhoto = settings.garden_notifications_include_photo ?? true;
        gardenAutomaticNaming = settings.garden_automatic_naming ?? true;
        gardenNamingThreshold = settings.garden_naming_threshold ?? 0.8;
        gardenDomesticBirds = [...(settings.garden_domestic_birds ?? [])];
        nestDedupeMinutes = typeof settings.nest_dedupe_minutes === 'number' && settings.nest_dedupe_minutes > 0
            ? settings.nest_dedupe_minutes
            : 30;
        audioBufferHours = settings.audio_buffer_hours ?? 24;
        audioCorrelationWindowSeconds = settings.audio_correlation_window_seconds ?? 300;
        classificationImageSource = settings.classification_image_source ?? 'frigate_snapshot';
        recordingFrameDelaySeconds = settings.recording_frame_delay_seconds ?? 12;
        clipsEnabled = settings.clips_enabled ?? true;
        recordingClipEnabled = settings.recording_clip_enabled ?? false;
        recordingClipBeforeSeconds = settings.recording_clip_before_seconds ?? 30;
        recordingClipAfterSeconds = settings.recording_clip_after_seconds ?? 90;
        threshold = settings.classification_threshold;
        minConfidence = settings.classification_min_confidence ?? 0.4;
        liveWorkerCount = settings.live_worker_count ?? null;
        backgroundWorkerCount = settings.background_worker_count ?? null;
        trustFrigateSublabel = settings.trust_frigate_sublabel ?? true;
        writeFrigateSublabel = settings.write_frigate_sublabel ?? true;
        const { fontTheme, colorTheme, ...savedAppearanceChoices } = appearanceSection.decode(settings);
        appearanceChoices = savedAppearanceChoices;
        themeStore.setFontTheme(fontTheme);
        themeStore.setColorTheme(colorTheme);
        personalizedRerankEnabled = settings.personalized_rerank_enabled ?? false;
        rangeFilterEnabled = settings.range_filter_enabled ?? false;
        rangeFilterRegionLevel = settings.range_filter_region_level ?? 'county';
        autoVideoClassification = settings.auto_video_classification ?? false;
        videoClassificationDelay = settings.video_classification_delay ?? 30;
        videoClassificationMaxRetries = settings.video_classification_max_retries ?? 3;
        videoClassificationFrames = settings.video_classification_frames ?? 15;
        birdModelRegionOverride = resolveBirdModelRegionOverrideFromSettings(settings.bird_model_region_override);
        birdFinder = parseBirdFinder(settings.bird_crop_accurate_detector);
        birdFinderProvider = settings.bird_crop_inference_provider ?? 'auto';
        imageExecutionMode = settings.image_execution_mode ?? 'subprocess';
        strictNonFiniteOutput = settings.strict_non_finite_output ?? true;
        betaGardenAnimals = settings.beta_garden_animals ?? false;
        inferenceProvider = parseInferenceProvider(settings.inference_provider) ?? 'auto';
        videoCircuitOpen = settings.video_classification_circuit_open ?? false;
        videoCircuitUntil = settings.video_classification_circuit_until ?? null;
        videoCircuitFailures = settings.video_classification_circuit_failures ?? 0;
        selectedCameras = settings.cameras || [];
        retentionDays = settings.retention_days || 0;
        maintenanceMaxConcurrent = settings.maintenance_max_concurrent ?? 1;
        frigateMissingBehavior = normalizeFrigateMissingBehavior(settings.frigate_missing_behavior);
        {
            const autoMediaIntegrityScan = (settings.auto_purge_missing_clips ?? false) || (settings.auto_purge_missing_snapshots ?? false);
            autoPurgeMissingClips = autoMediaIntegrityScan;
            autoPurgeMissingSnapshots = autoMediaIntegrityScan;
        }
        autoAnalyzeUnknowns = settings.auto_analyze_unknowns ?? false;
        // Media cache settings
        cacheClips = settings.media_cache_clips ?? false;
        cacheHighQualityEventSnapshots = settings.media_cache_high_quality_event_snapshots ?? false;
        cacheHighQualityEventSnapshotJpegQuality = settings.media_cache_high_quality_event_snapshot_jpeg_quality ?? 90;
        cacheRetentionDays = settings.media_cache_retention_days ?? 0;
        cachePerSpeciesMaximum = settings.media_cache_per_species_maximum ?? 0;
        cacheMaxSizeMb = settings.media_cache_max_size_mb ?? 0;
        cacheAutomaticMultiBirdScan = settings.media_cache_automatic_multi_bird_scan ?? false;
        cacheBirdScanMode = settings.media_cache_bird_scan_mode ?? 'intensive';
        cachePerSpeciesMinimum = settings.media_cache_per_species_minimum ?? 0;
        // Location settings
        locationLat = settings.location_latitude ?? null;
        locationLon = settings.location_longitude ?? null;
        locationState = settings.location_state ?? '';
        locationCountry = settings.location_country ?? '';
        locationAuto = settings.location_automatic ?? true;
        locationWeatherUnitSystem = ((settings.location_weather_unit_system as 'metric' | 'imperial' | 'british') ?? (settings.location_temperature_unit === 'fahrenheit' ? 'imperial' : 'metric'));
        // BirdWeather settings
        birdweatherEnabled = settings.birdweather_enabled ?? false;
        if (settings.birdweather_station_token === '***REDACTED***') {
            birdweatherStationTokenSaved = true;
            birdweatherStationToken = '';
        } else {
            birdweatherStationTokenSaved = false;
            birdweatherStationToken = settings.birdweather_station_token ?? '';
        }
        haWeatherEnabled = settings.ha_weather_enabled ?? false;
        haWeatherBaseUrl = settings.ha_weather_base_url ?? '';
        if (settings.ha_weather_access_token === '***REDACTED***') {
            haWeatherAccessTokenSaved = true;
            haWeatherAccessToken = '';
        } else {
            haWeatherAccessTokenSaved = false;
            haWeatherAccessToken = settings.ha_weather_access_token ?? '';
        }
        haWeatherEntity = settings.ha_weather_entity ?? '';
        haWeatherTemperatureEntity = settings.ha_weather_temperature_entity ?? '';
        haWeatherWindSpeedEntity = settings.ha_weather_wind_speed_entity ?? '';
        haWeatherWindDirectionEntity = settings.ha_weather_wind_direction_entity ?? '';
        haWeatherCloudCoverEntity = settings.ha_weather_cloud_cover_entity ?? '';
        haWeatherPrecipitationEntity = settings.ha_weather_precipitation_entity ?? '';
        haWeatherRainEntity = settings.ha_weather_rain_entity ?? '';
        haWeatherSnowfallEntity = settings.ha_weather_snowfall_entity ?? '';
        haWeatherIlluminanceEntity = settings.ha_weather_illuminance_entity ?? '';
        // eBird settings
        ebirdEnabled = settings.ebird_enabled ?? false;
        if (settings.ebird_api_key === '***REDACTED***') {
            ebirdApiKeySaved = true;
            ebirdApiKey = '';
        } else {
            ebirdApiKeySaved = false;
            ebirdApiKey = settings.ebird_api_key || '';
        }
        ebirdDefaultRadiusKm = settings.ebird_default_radius_km ?? 25;
        ebirdDefaultDaysBack = settings.ebird_default_days_back ?? 14;
        ebirdMaxResults = settings.ebird_max_results ?? 25;
        ebirdLocale = settings.ebird_locale ?? 'en';
        // iNaturalist settings
        inaturalistEnabled = settings.inaturalist_enabled ?? false;
        if (settings.inaturalist_client_id === '***REDACTED***') {
            inaturalistClientIdSaved = true;
            inaturalistClientId = '';
        } else {
            inaturalistClientIdSaved = false;
            inaturalistClientId = settings.inaturalist_client_id || '';
        }
        if (settings.inaturalist_client_secret === '***REDACTED***') {
            inaturalistClientSecretSaved = true;
            inaturalistClientSecret = '';
        } else {
            inaturalistClientSecretSaved = false;
            inaturalistClientSecret = settings.inaturalist_client_secret || '';
        }
        inaturalistDefaultLat = settings.inaturalist_default_latitude ?? null;
        inaturalistDefaultLon = settings.inaturalist_default_longitude ?? null;
        inaturalistDefaultPlace = settings.inaturalist_default_place_guess ?? '';
        inaturalistConnectedUser = settings.inaturalist_connected_user ?? null;
        // Enrichment settings
        enrichmentDraft = enrichmentSection.decode(settings);
        aiDraft = aiSection.decode(settings);
        // Telemetry
        telemetryEnabled = settings.telemetry_enabled ?? true;
        telemetryHealthEnabled = settings.telemetry_health_enabled ?? false;
        telemetryInstallationId = settings.telemetry_installation_id;
        telemetryPlatform = settings.telemetry_platform;
        telemetryPayloadPreview = settings.telemetry_payload_preview;
        // Authentication + Public access
        authEnabled = settings.auth_enabled ?? false;
        authUsername = settings.auth_username || 'admin';
        authHasPassword = settings.auth_has_password ?? false;
        authPassword = '';
        authPasswordConfirm = '';
        authSessionExpiryHours = settings.auth_session_expiry_hours ?? 168;
        const proxyHosts = savedTrustedProxyHosts(settings.trusted_proxy_hosts);
        const proxyHostsDefault = proxyHosts.length === 1 && proxyHosts[0] === '*';
        trustedProxyHostsSuggested = proxyHostsDefault;
        trustedProxyHosts = proxyHostsDefault ? ['nginx-rp', 'cloudflare-tunnel'] : proxyHosts;
        publicAccessEnabled = settings.public_access_enabled ?? false;
        publicAccessShowCameraNames = settings.public_access_show_camera_names ?? true;
        publicAccessShowAiConversation = settings.public_access_show_ai_conversation ?? false;
        publicAccessAllowClipDownloads = settings.public_access_allow_clip_downloads ?? false;
        publicAccessShowAudio = settings.public_access_show_audio ?? true;
        publicAccessShowSnapshots = settings.public_access_show_snapshots ?? true;
        publicAccessShowClips = settings.public_access_show_clips ?? true;
        publicAccessLocationPrecision = (settings.public_access_location_precision as 'approximate' | 'exact') ?? 'approximate';
        publicAccessHistoricalDaysMode = normalizePublicDaysMode(settings.public_access_historical_days_mode);
        publicAccessHistoricalDays = settings.public_access_historical_days ?? 7;
        publicAccessMediaDaysMode = normalizePublicDaysMode(settings.public_access_media_days_mode);
        publicAccessMediaHistoricalDays = settings.public_access_media_historical_days ?? 7;
        publicAccessRateLimitPerMinute = settings.public_access_rate_limit_per_minute ?? 30;
        publicAccessExternalBaseUrl = settings.public_access_external_base_url ?? '';
        debugUiEnabled = settings.debug_ui_enabled ?? false;

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
        pushoverDevice = settings.notifications_pushover_device ?? '';

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
        emailOnlyOnEnd = settings.notifications_email_only_on_end ?? false;
        emailGmailClientId = settings.notifications_email_gmail_client_id || '';
        if (settings.notifications_email_gmail_client_secret === '***REDACTED***') {
            emailGmailClientSecretSaved = true;
            emailGmailClientSecret = '';
        } else {
            emailGmailClientSecretSaved = false;
            emailGmailClientSecret = settings.notifications_email_gmail_client_secret || '';
        }
        emailOutlookClientId = settings.notifications_email_outlook_client_id || '';
        if (settings.notifications_email_outlook_client_secret === '***REDACTED***') {
            emailOutlookClientSecretSaved = true;
            emailOutlookClientSecret = '';
        } else {
            emailOutlookClientSecretSaved = false;
            emailOutlookClientSecret = settings.notifications_email_outlook_client_secret || '';
        }
        notificationLanguage = settings.notification_language ?? 'en';
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
        instanceUrl = settings.notifications_instance_url || '';
        notifyLinkTarget = settings.notifications_link_target ?? 'yawamf';

        filterSpeciesMode = inferNotificationSpeciesMode(settings);
        filterSpeciesEntries = mergeBlockedSpeciesEntries(notificationSpeciesEntriesForMode(settings, filterSpeciesMode));
        filterWhitelist = filterSpeciesMode === 'whitelist' ? (settings.notifications_filter_species_whitelist || []) : [];
        filterConfidence = settings.notifications_filter_min_confidence ?? 0.7;
        filterAudioOnly = settings.notifications_filter_audio_confirmed_only ?? false;
        notifyMode = savedNotifyMode(settings);
        notifyOnInsert = settings.notifications_notify_on_insert ?? true;
        notifyOnUpdate = settings.notifications_notify_on_update ?? false;
        notifyDelayUntilVideo = settings.notifications_delay_until_video ?? false;
        notifyVideoFallbackTimeout = settings.notifications_video_fallback_timeout ?? 45;
        notifyCooldownMinutes = settings.notifications_notification_cooldown_minutes ?? 0;

        accessibilityDraft = accessibilitySection.decode(settings);
        blockedLabels = [...blockedLabelsBaseline];
        blockedSpecies = [...blockedSpeciesBaseline];
    }

    async function loadSettings(silent = false, shareShellRead = false) {
        if (!silent) loading = true;
        loadingBirdnetSources = true;
        birdnetSourcesError = null;
        try {
            const settings = shareShellRead ? await settingsStore.read(SHARED_SETTINGS_READ_MS) : await fetchSettings();
            loadedSetupSettings = settings;
            // A shared read is the store's own copy; handing it back would restart its age.
            if (!shareShellRead) settingsStore.update(settings);
            applySavedSettings(settings);
            loadedInferenceProvider = settings.inference_provider;
            settingsFormLoads += 1;
            try {
                birdnetSourceOptions = await fetchAudioSources(20);
            } catch (e) {
                birdnetSourceOptions = [];
                birdnetSourcesError = e instanceof Error ? e.message : 'Failed to load BirdNET sources';
                console.error('Failed to load BirdNET source helper data', e);
            } finally {
                loadingBirdnetSources = false;
            }
            const migratedBlockedLabels = await migrateLegacyBlockedLabels(
                settings.blocked_labels || [],
                (query) => searchSpecies(query, 50, true)
            );
            blockedLabels = migratedBlockedLabels.legacyBlockedLabels;
            blockedSpecies = mergeBlockedSpeciesEntries([
                ...((settings.blocked_species || []) as BlockedSpeciesEntry[]),
                ...migratedBlockedLabels.blockedSpecies,
            ]);
            blockedLabelsBaseline = [...blockedLabels];
            blockedSpeciesBaseline = [...blockedSpecies];
            await loadRecordingClipCapability();
            settingsLoadFailed = false;
        } catch (e) {
            loadingBirdnetSources = false;
            // A page-opening read that failed leaves nothing trustworthy to edit; the page says so
            // and offers the read again. A refresh behind a form already shown only reports itself.
            if (silent) notify('error', $_('notifications.settings_load_failed'));
            else settingsLoadFailed = true;
        } finally {
            if (!silent) loading = false;
        }
    }

    async function loadCameras() {
        camerasLoading = true;
        try {
            const config = await fetchFrigateConfig();
            if (config && typeof config === 'object' && 'cameras' in config) {
                const cameras = config.cameras;
                if (cameras && typeof cameras === 'object') {
                    availableCameras = Object.keys(cameras);
                    frigateCameras = Object.keys(cameras);
                    frigateCamerasFailed = false;
                    return;
                }
            }
            frigateCamerasFailed = frigateCameras === null;
        } catch (e) {
            console.error('Failed to load cameras from Frigate', e);
            frigateCamerasFailed = frigateCameras === null;
            if (selectedCameras.length > 0 && availableCameras.length === 0) {
                 availableCameras = [...selectedCameras];
            }
        } finally {
            camerasLoading = false;
        }
    }

    // What a save sends: every field the form edits, in the server's names.
    function buildSettingsPayload(): SettingsUpdate {
        return {
            frigate_url: frigateUrl,
            frigate_ingest_labels: frigateIngestLabels.split(',').map((l) => l.trim()).filter(Boolean),
            frigate_external_url: frigateExternalUrl,
            mqtt_server: mqttServer,
            mqtt_port: mqttPort,
            mqtt_auth: mqttAuth,
            mqtt_username: mqttUsername,
            mqtt_password: mqttPassword,
            birdnet_enabled: birdnetEnabled,
            birdnet_url: birdnetUrl,
            birdnet_external_url: birdnetExternalUrl,
            audio_topic: audioTopic,
            camera_audio_mapping: cameraAudioMapping,
            camera_roles: cameraRoles,
            garden_cameras: gardenCameras,
            garden_motion_cameras: gardenMotionCameras,
            garden_labels: gardenLabels.split(/[,;\n]+/).map(label => label.trim().toLowerCase()).filter(Boolean),
            garden_motion_confidence: gardenMotionConfidence,
            garden_notifications_enabled: gardenNotificationsEnabled,
            garden_notification_channels: gardenNotificationChannels,
            garden_notifications_use_bird_channels: gardenNotificationsUseBirdChannels,
            garden_notifications_include_photo: gardenNotificationsIncludePhoto,
            garden_automatic_naming: gardenAutomaticNaming,
            garden_naming_threshold: gardenNamingThreshold,
            garden_domestic_birds: gardenDomesticBirds,
            nest_dedupe_minutes: nestDedupeMinutes,
            audio_buffer_hours: audioBufferHours,
            audio_correlation_window_seconds: audioCorrelationWindowSeconds,
            classification_image_source: classificationImageSource,
            recording_frame_delay_seconds: recordingFrameDelaySeconds,
            clips_enabled: clipsEnabled,
            recording_clip_enabled: recordingClipEnabled,
            recording_clip_before_seconds: recordingClipBeforeSeconds,
            recording_clip_after_seconds: recordingClipAfterSeconds,
            classification_threshold: threshold,
            classification_min_confidence: minConfidence,
            live_worker_count: liveWorkerCount,
            background_worker_count: backgroundWorkerCount,
            trust_frigate_sublabel: trustFrigateSublabel,
            write_frigate_sublabel: writeFrigateSublabel,
            personalized_rerank_enabled: personalizedRerankEnabled,
            range_filter_enabled: rangeFilterEnabled,
            range_filter_region_level: rangeFilterRegionLevel,
            auto_video_classification: autoVideoClassification,
            video_classification_delay: videoClassificationDelay,
            video_classification_max_retries: videoClassificationMaxRetries,
            video_classification_frames: videoClassificationFrames,
            ...buildBirdModelRegionOverrideSettings(birdModelRegionOverride),
            bird_crop_accurate_detector: birdFinder,
            bird_crop_inference_provider: birdFinderProvider,
            image_execution_mode: imageExecutionMode,
            strict_non_finite_output: strictNonFiniteOutput,
            beta_garden_animals: betaGardenAnimals,
            inference_provider: inferenceProviderForSave(inferenceProvider, settingsStore.settings?.inference_provider),
            cameras: selectedCameras,
            retention_days: retentionDays,
            maintenance_max_concurrent: maintenanceMaxConcurrent,
            frigate_missing_behavior: frigateMissingBehavior,
            auto_purge_missing_clips: autoPurgeMissingClips,
            auto_purge_missing_snapshots: autoPurgeMissingSnapshots,
            auto_analyze_unknowns: autoAnalyzeUnknowns,
            blocked_labels: blockedLabels,
            blocked_species: blockedSpecies,
            media_cache_clips: cacheClips,
            media_cache_high_quality_event_snapshots: cacheHighQualityEventSnapshots,
            // Compatibility field: best-available snapshots always attempt an automatic crop.
            media_cache_high_quality_event_snapshot_bird_crop: cacheHighQualityEventSnapshots,
            media_cache_high_quality_event_snapshot_jpeg_quality: cacheHighQualityEventSnapshotJpegQuality,
            media_cache_retention_days: cacheRetentionDays,
            media_cache_per_species_maximum: cachePerSpeciesMaximum,
            media_cache_max_size_mb: cacheMaxSizeMb,
            media_cache_automatic_multi_bird_scan: cacheAutomaticMultiBirdScan,
            media_cache_bird_scan_mode: cacheBirdScanMode,
            media_cache_per_species_minimum: cachePerSpeciesMinimum,
            location_latitude: locationLat,
            location_longitude: locationLon,
            location_state: locationState || null,
            location_country: locationCountry || null,
            location_automatic: locationAuto,
            location_weather_unit_system: locationWeatherUnitSystem,
            birdweather_enabled: birdweatherEnabled,
            birdweather_station_token: birdweatherStationToken,
            ha_weather_enabled: haWeatherEnabled,
            ha_weather_base_url: haWeatherBaseUrl || null,
            ha_weather_access_token: haWeatherAccessToken,
            ha_weather_entity: haWeatherEntity || null,
            ha_weather_temperature_entity: haWeatherTemperatureEntity || null,
            ha_weather_wind_speed_entity: haWeatherWindSpeedEntity || null,
            ha_weather_wind_direction_entity: haWeatherWindDirectionEntity || null,
            ha_weather_cloud_cover_entity: haWeatherCloudCoverEntity || null,
            ha_weather_precipitation_entity: haWeatherPrecipitationEntity || null,
            ha_weather_rain_entity: haWeatherRainEntity || null,
            ha_weather_snowfall_entity: haWeatherSnowfallEntity || null,
            ha_weather_illuminance_entity: haWeatherIlluminanceEntity.trim() || null,
            ebird_enabled: ebirdEnabled,
            ebird_api_key: ebirdApiKey,
            ebird_default_radius_km: ebirdDefaultRadiusKm,
            ebird_default_days_back: ebirdDefaultDaysBack,
            ebird_max_results: ebirdMaxResults,
            ebird_locale: ebirdLocale,
            inaturalist_enabled: inaturalistEnabled,
            inaturalist_client_id: inaturalistClientId,
            inaturalist_client_secret: inaturalistClientSecret,
            inaturalist_default_latitude: inaturalistDefaultLat,
            inaturalist_default_longitude: inaturalistDefaultLon,
            inaturalist_default_place_guess: inaturalistDefaultPlace,
            ...enrichmentSection.encodePatch(enrichmentDraft),
            ...aiSection.encodePatch(aiDraft),
            telemetry_enabled: telemetryEnabled,
            telemetry_health_enabled: telemetryHealthEnabled,
            auth_enabled: authEnabled,
            auth_username: authUsername,
            auth_password: authPassword || undefined,
            auth_session_expiry_hours: authSessionExpiryHours,
            trusted_proxy_hosts: effectiveTrustedProxyHosts,
            public_access_enabled: publicAccessEnabled,
            public_access_show_camera_names: publicAccessShowCameraNames,
            public_access_show_ai_conversation: publicAccessShowAiConversation,
            public_access_allow_clip_downloads: publicAccessAllowClipDownloads,
            public_access_show_audio: publicAccessShowAudio,
            public_access_show_snapshots: publicAccessShowSnapshots,
            public_access_show_clips: publicAccessShowClips,
            public_access_location_precision: publicAccessLocationPrecision,
            public_access_historical_days_mode: publicAccessHistoricalDaysMode,
            public_access_historical_days: publicAccessHistoricalDays,
            public_access_media_days_mode: publicAccessMediaDaysMode,
            public_access_media_historical_days: publicAccessMediaHistoricalDays,
            public_access_rate_limit_per_minute: publicAccessRateLimitPerMinute,
            public_access_external_base_url: publicAccessExternalBaseUrl.trim() || null,

            // Notifications
            notifications_discord_enabled: discordEnabled,
            notifications_discord_webhook_url: discordWebhook,
            notifications_discord_username: discordUsername,

            notifications_pushover_enabled: pushoverEnabled,
            notifications_pushover_user_key: pushoverUser,
            notifications_pushover_api_token: pushoverToken,
            notifications_pushover_priority: pushoverPriority,
            notifications_pushover_device: pushoverDevice || null,

            notifications_telegram_enabled: telegramEnabled,
            notifications_telegram_bot_token: telegramToken,
            notifications_telegram_chat_id: telegramChatId,

            notifications_email_enabled: emailEnabled,
            notifications_email_only_on_end: emailOnlyOnEnd,
            notifications_email_use_oauth: emailUseOAuth,
            notifications_email_oauth_provider: emailOAuthProvider,
            notifications_email_gmail_client_id: emailGmailClientId || null,
            notifications_email_gmail_client_secret: emailGmailClientSecret || undefined,
            notifications_email_outlook_client_id: emailOutlookClientId || null,
            notifications_email_outlook_client_secret: emailOutlookClientSecret || undefined,
            notifications_email_smtp_host: emailSmtpHost,
            notifications_email_smtp_port: emailSmtpPort,
            notifications_email_smtp_username: emailSmtpUsername,
            notifications_email_smtp_password: emailSmtpPassword,
            notifications_email_smtp_use_tls: emailSmtpUseTls,
            notifications_email_from_email: emailFromEmail,
            notifications_email_to_email: emailToEmail,
            notifications_email_include_snapshot: emailIncludeSnapshot,
            notifications_instance_url: instanceUrl,
            notifications_link_target: notifyLinkTarget,

            notification_language: notificationLanguage,
            notifications_filter_species_mode: filterSpeciesMode,
            notifications_filter_species_whitelist: filterSpeciesMode === 'whitelist' ? filterWhitelist : [],
            notifications_filter_species_whitelist_structured: filterSpeciesMode === 'whitelist' ? filterSpeciesEntries : [],
            notifications_filter_species_blacklist_structured: filterSpeciesMode === 'blacklist' ? filterSpeciesEntries : [],
            notifications_filter_min_confidence: filterConfidence,
            notifications_filter_audio_confirmed_only: filterAudioOnly,
            notifications_mode: notifyMode,
            notifications_notify_on_insert: notifyOnInsert,
            notifications_notify_on_update: notifyOnUpdate,
            notifications_delay_until_video: notifyDelayUntilVideo,
            notifications_video_fallback_timeout: notifyVideoFallbackTimeout,
            notifications_notification_cooldown_minutes: notifyCooldownMinutes,

            ...accessibilitySection.encodePatch(accessibilityDraft),
            ...appearanceSection.encodePatch(appearanceDraft)
        };
    }

    // Values checked here before sending, in the same shape the server uses for a refusal.
    function locallyRefusedFields(): SettingsFieldError[] {
        const refused: SettingsFieldError[] = [];
        if (!Number.isFinite(recordingFrameDelaySeconds) || recordingFrameDelaySeconds < 1 || recordingFrameDelaySeconds > 120) {
            refused.push(rangeFieldError('recording_frame_delay_seconds', 1, 120));
        }
        if (!Number.isFinite(gardenMotionConfidence) || gardenMotionConfidence < 0.5 || gardenMotionConfidence > 0.95) {
            refused.push(rangeFieldError('garden_motion_confidence', 50, 95, '%'));
        }
        if (!Number.isFinite(gardenNamingThreshold) || gardenNamingThreshold < 0.7 || gardenNamingThreshold > 0.99) {
            refused.push(rangeFieldError('garden_naming_threshold', 70, 99, '%'));
        }
        const authSettingsError = validateAuthSettingsSave({
            authEnabled,
            authHasPassword,
            authPassword,
            authPasswordConfirm
        });
        if (authSettingsError) {
            const problem = passwordProblemMessage(authSettingsError);
            refused.push({ field: 'auth_password', key: problem.key, fallback: problem.default });
        }
        return refused;
    }

    function refuse(errors: SettingsFieldError[], payload: SettingsUpdate): void {
        fieldErrors = errors;
        refusedPayload = payload as Record<string, unknown>;
        saveProblem = { key: 'settings.save_bar.refused', fallback: 'Nothing was saved. Correct the highlighted values, then save again.' };
    }

    async function saveSettings() {
        saving = true;
        saveProblem = null;
        const payload = buildSettingsPayload();
        const refusedHere = locallyRefusedFields();
        if (refusedHere.length > 0) {
            refuse(refusedHere, payload);
            saving = false;
            return;
        }
        if (!(await confirmRetentionChange())) {
            saving = false;
            return;
        }
        try {
            await updateSettings(payload);
            fieldErrors = [];
            // Public access flags are also used outside Settings (guest gating, etc.)
            await authStore.loadStatus();
            // Sync local state to handle server-side normalization (e.g. stripped slashes)
            await loadSettings(true);
            notify('success', $_('notifications.settings_saved'));
            // A saved provider or worker change re-plans the runtime.
            await Promise.all([loadMaintenanceStats(), loadCacheStats(), loadClassifierStatus()]);
        } catch (e) {
            if (e instanceof SettingsSaveRejected && e.fieldErrors.length > 0) {
                refuse(e.fieldErrors, payload);
            } else {
                fieldErrors = [];
                saveProblem = saveFailure(e);
            }
        } finally {
            saving = false;
        }
    }

    // A failure that names no field: say nothing was saved and what to try. A server error's own
    // text ("Internal Server Error") is not a reason a person can act on, so it is never shown.
    function saveFailure(error: unknown): { key: string; values?: Record<string, string>; fallback: string } {
        const status = error instanceof ApiRequestError || error instanceof SettingsSaveRejected ? error.status : null;
        const reason = error instanceof Error ? error.message.trim() : '';
        if (status !== null && status >= 400 && status < 500 && reason && !/^HTTP \d+$/.test(reason)) {
            return { key: 'settings.save_bar.refused_reason', values: { reason }, fallback: 'Nothing was saved: {reason}' };
        }
        return {
            key: 'settings.save_bar.failed',
            fallback: 'Nothing was saved because YA-WAMF did not store the settings. Check that the backend is running, then try Save changes again.'
        };
    }

    // Throws away every unsaved edit by putting the saved copy back into the form.
    function discardChanges(): void {
        const saved = settingsStore.settings;
        if (!saved) return;
        applySavedSettings(saved);
        fieldErrors = [];
        saveProblem = null;
        // The save bar holding focus goes away; the content it described is where focus belongs.
        void tick().then(() => document.querySelector<HTMLElement>('[data-settings-content]')?.focus());
    }

    // Opens the tab holding a refused field and puts focus on its input once the tab has loaded.
    async function openRefusedField(field: string): Promise<void> {
        const tab = settingsFieldTab(field);
        if (tab) handleTabChange(tab);
        const inputId = settingsFieldPlace(field)?.inputId;
        if (!inputId) return;
        for (let frame = 0; frame < FIELD_WAIT_FRAMES; frame += 1) {
            await tick();
            const input = document.getElementById(inputId);
            if (input) {
                input.scrollIntoView({ block: 'center' });
                input.focus({ preventScroll: true });
                return;
            }
            await new Promise((resolve) => requestAnimationFrame(resolve));
        }
    }

    async function prepareInaturalistOAuth(): Promise<void> {
        // OAuth must use the credentials currently visible in the form. Persist
        // only this integration so unrelated unsaved settings remain untouched.
        await updateSettings({
            inaturalist_enabled: true,
            inaturalist_client_id: inaturalistClientId,
            inaturalist_client_secret: inaturalistClientSecret
        });
        const refreshed = await fetchSettings();
        settingsStore.update(refreshed);
        inaturalistEnabled = refreshed.inaturalist_enabled ?? true;
        inaturalistClientIdSaved = refreshed.inaturalist_client_id === '***REDACTED***';
        inaturalistClientSecretSaved = refreshed.inaturalist_client_secret === '***REDACTED***';
        if (inaturalistClientIdSaved) inaturalistClientId = '';
        if (inaturalistClientSecretSaved) inaturalistClientSecret = '';
    }

    function setTheme(t: Theme) {
        themeStore.setTheme(t);
    }

    function updateAppearance({ fontTheme, colorTheme, ...choices }: Partial<AppearanceDraft>): void {
        if (fontTheme) themeStore.setFontTheme(fontTheme);
        if (colorTheme) themeStore.setColorTheme(colorTheme);
        appearanceChoices = { ...appearanceChoices, ...choices };
    }

    async function setLanguage(lang: string): Promise<void> {
        if (await setAppLocale(lang)) return;
        notify('error', $_('common.language_load_error', {
                default: 'That language could not be loaded. Check your connection and try again.'
            }));
    }

</script>

{#snippet pageTabs()}
    <SettingsTabs {activeTab} {debugUiEnabled} ontabchange={handleTabChange} />
{/snippet}

<SettingsPage
    title={$_('settings.title')}
    subtitle={$_('settings.subtitle')}
    {loading}
    loadFailure={settingsLoadFailed
        ? $_('settings.load_failed', { default: 'Your settings could not be read, so nothing is shown for editing. Check that the YA-WAMF backend is running, then try again.' })
        : null}
    onRetryLoad={() => void loadSettings()}
    {saving}
    onSave={saveSettings}
    onDiscard={discardChanges}
    unsaved={{ count: unsavedSummary.count, tabs: unsavedSummary.tabs.map((tab) => ({ id: tab, label: tabLabel(tab) })) }}
    onOpenTab={handleTabChange}
    {saveProblem}
    refusedFields={standingErrors.map((error) => {
        const place = settingsFieldPlace(error.field);
        const tab = settingsFieldTab(error.field);
        const label = place ? $_(place.labelKey) : $_('settings.save_bar.other_field', { default: 'Another setting' });
        // The same label can appear on two tabs ("Port"), so the tab is named with it.
        return { field: error.field, label: tab ? `${label} (${tabLabel(tab)})` : label };
    })}
    onOpenField={openRefusedField}
    tabs={pageTabs}
>
    {#snippet children()}
            <!-- Connection Tab -->
            {#if activeTab === 'connection'}
                <LazyRoute loader={loadConnectionSettings} label={$_('settings.tabs.connection')}>
                {#snippet content(ConnectionSettings)}
                <ConnectionSettings
                    bind:frigateUrl
                    bind:frigateIngestLabels
                    bind:frigateExternalUrl
                    bind:mqttServer
                    bind:mqttPort
                    bind:mqttAuth
                    bind:mqttUsername
                    bind:mqttPassword
                    bind:mqttPasswordSaved
                    bind:selectedCameras
                    bind:gardenCameras
                    bind:gardenMotionCameras
                    {betaGardenAnimals}
                    bind:cameraRoles
                    bind:nestDedupeMinutes
                    bind:classificationImageSource
                    bind:recordingFrameDelaySeconds
                    bind:clipsEnabled
                    bind:recordingClipEnabled
                    bind:recordingClipBeforeSeconds
                    bind:recordingClipAfterSeconds
                    bind:telemetryEnabled
                    bind:telemetryHealthEnabled
                    {frigateCameras}
                    {frigateCamerasFailed}
                    {recordingClipCapability}
                    {recordingClipCapabilityLoading}
                    {camerasLoading}
                    {telemetryInstallationId}
                    {telemetryPlatform}
                    {telemetryPayloadPreview}
                    {versionInfo}
                    {loadCameras}
                />
                {/snippet}
                </LazyRoute>
            {/if}

            <!-- Detection Tab -->
            {#if activeTab === 'detection'}
                <LazyRoute loader={loadDetectionSettings} label={$_('settings.tabs.detection')}>
                {#snippet content(DetectionSettings)}
                <DetectionSettings
                    bind:threshold
                    bind:minConfidence
                    bind:liveWorkerCount
                    bind:backgroundWorkerCount
                    bind:trustFrigateSublabel
                    bind:writeFrigateSublabel
                    bind:personalizedRerankEnabled
                    bind:autoVideoClassification
                    bind:videoClassificationDelay
                    bind:videoClassificationMaxRetries
                    bind:videoClassificationFrames
                    bind:birdModelRegionOverride
                    bind:birdFinder
                    bind:birdFinderProvider
                    bind:imageExecutionMode
                    bind:inferenceProvider
                    {classifierStatus}
                    onrefreshclassifierstatus={loadClassifierStatus}
                    bind:blockedLabels
                    bind:blockedSpecies
                    {videoCircuitOpen}
                    {videoCircuitUntil}
                    {videoCircuitFailures}
                    onopenlocationsettings={() => openIntegrationField('#location-lat', '#setting-location-mode + div button[aria-pressed="false"]')}
                    bind:rangeFilterEnabled
                    bind:rangeFilterRegionLevel
                    onopenebirdsettings={() => openIntegrationField('#ebird-api-key', '[aria-labelledby="setting-ebird-enabled"]')}
                    onopenactivitylog={() => handleTabChange('health')}
                    onopenmanualobservation={onNavigate ? () => onNavigate('/observations/new') : undefined}
                />
                {/snippet}
                </LazyRoute>
            {/if}

            <!-- Notifications Tab -->
            {#if activeTab === 'notifications'}
                <LazyRoute loader={loadNotificationSettings} label={$_('settings.tabs.notifications')}>
                {#snippet content(NotificationSettings)}
                <NotificationSettings
                    bind:notifyMinConfidence={filterConfidence}
                    bind:notifyAudioOnly={filterAudioOnly}
                    bind:filterSpeciesMode
                    bind:filterSpeciesEntries
                    bind:legacySpeciesWhitelist={filterWhitelist}
                    bind:notifyMode
                    bind:notifyOnInsert
                    bind:notifyOnUpdate
                    bind:notifyDelayUntilVideo
                    bind:notifyVideoFallbackTimeout
                    bind:notifyCooldownMinutes
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
                    bind:pushoverDevice
                    bind:telegramEnabled
                    bind:telegramBotToken={telegramToken}
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
                    bind:linkTarget={notifyLinkTarget}
                    {frigateExternalUrl}
                    onOpenIntegrations={() => handleTabChange('integrations')}
                    gardenBeta={betaGardenAnimals}
                    gardenStatusAvailable={settingsStore.settings?.beta_garden_animals === true}
                    bind:gardenNotificationsEnabled
                    bind:gardenUseBirdChannels={gardenNotificationsUseBirdChannels}
                    bind:gardenNotificationChannels
                    bind:gardenIncludePhoto={gardenNotificationsIncludePhoto}
                    {sendTestEmail}
                    {initiateGmailOAuth}
                    {initiateOutlookOAuth}
                    {disconnectEmailOAuth}
                    onActionFeedback={handleActionFeedback}
                />
                {/snippet}
                </LazyRoute>
            {/if}

            <!-- Health Tab -->
            {#if activeTab === 'health'}
                <!-- The health page builds the System card itself, with its verdict inside it. -->
                <LazyRoute loader={loadHealthTab} label={$_('settings.tabs.health')} props={{ onNavigate }} />
            {/if}

            <!-- Integrations Tab -->
            {#if activeTab === 'integrations'}
                <LazyRoute loader={loadIntegrationSettings} label={$_('settings.tabs.integrations')}>
                {#snippet content(IntegrationSettings)}
                <IntegrationSettings
                    weatherUnitSystem={locationWeatherUnitSystem}
                    bind:birdnetEnabled
                    bind:birdnetUrl
                    bind:birdnetExternalUrl
                    bind:audioTopic
                    bind:audioBufferHours
                    bind:audioCorrelationWindowSeconds
                    bind:cameraAudioMapping
                    {birdnetSourceOptions}
                    {loadingBirdnetSources}
                    {birdnetSourcesError}
                    {availableCameras}
                    bind:birdweatherEnabled
                    bind:birdweatherStationToken
                    bind:birdweatherStationTokenSaved
                    bind:haWeatherEnabled
                    bind:haWeatherBaseUrl
                    bind:haWeatherAccessToken
                    bind:haWeatherAccessTokenSaved
                    bind:haWeatherEntity
                    bind:haWeatherTemperatureEntity
                    bind:haWeatherWindSpeedEntity
                    bind:haWeatherWindDirectionEntity
                    bind:haWeatherCloudCoverEntity
                    bind:haWeatherPrecipitationEntity
                    bind:haWeatherRainEntity
                    bind:haWeatherSnowfallEntity
                    bind:haWeatherIlluminanceEntity
                    bind:ebirdEnabled
                    bind:ebirdApiKey
                    bind:ebirdApiKeySaved
                    bind:ebirdDefaultRadiusKm
                    bind:ebirdDefaultDaysBack
                    bind:ebirdMaxResults
                    bind:ebirdLocale
                    bind:inaturalistEnabled
                    bind:inaturalistClientId
                    bind:inaturalistClientSecret
                    bind:inaturalistClientIdSaved
                    bind:inaturalistClientSecretSaved
                    bind:inaturalistDefaultLat
                    bind:inaturalistDefaultLon
                    bind:inaturalistDefaultPlace
                    bind:inaturalistConnectedUser
                    bind:locationAuto
                    bind:locationLat
                    bind:locationLon
                    bind:locationState
                    bind:locationCountry
                    bind:locationWeatherUnitSystem
                    {prepareInaturalistOAuth}
                    initiateInaturalistOAuth={initiateInaturalistOAuth}
                    disconnectInaturalistOAuth={disconnectInaturalistOAuth}
                    refreshInaturalistStatus={async () => {
                        await settingsStore.load();
                        await loadSettings(true);
                    }}
                    exportEbirdCsv={exportEbirdCsv}
                    onActionFeedback={handleActionFeedback}
                    savedLocation={settingsStore.settings
                        ? { latitude: settingsStore.settings.location_latitude ?? null, longitude: settingsStore.settings.location_longitude ?? null }
                        : null}
                />
                {/snippet}
                </LazyRoute>
            {/if}

            <!-- Enrichment Tab -->
            {#if activeTab === 'enrichment'}
                <LazyRoute loader={loadEnrichmentTab} label={$_('settings.tabs.enrichment')} props={enrichmentDraft} />
            {/if}

            <!-- AI Tab -->
            {#if activeTab === 'ai'}
                <LazyRoute
                    loader={loadAiTab}
                    label={$_('settings.tabs.ai', { default: 'AI' })}
                    props={{ draft: aiDraft, onchange: (edit: Partial<AiDraft>) => (aiDraft = editAiDraft(aiDraft, edit)) }}
                />
            {/if}

            <!-- Security Tab -->
            {#if activeTab === 'security'}
                {#if authStore.httpsWarning}
                    <div class="mb-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100" data-https-warning>
                        <svg xmlns="http://www.w3.org/2000/svg" class="mt-0.5 h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <p>
                            <strong class="font-semibold">{$_('settings.security.https_warning_title', { default: 'Passwords travel unencrypted.' })}</strong>
                            {$_('settings.security.https_warning', { default: 'Sign-in is on, but this page is served over HTTP, so passwords and sessions can be read on the network. Serve YA-WAMF over HTTPS, for example behind your reverse proxy.' })}
                        </p>
                    </div>
                {/if}
                <LazyRoute loader={loadAuthenticationSettings} label={$_('settings.tabs.security')}>
                {#snippet content(AuthenticationSettings)}
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
                    bind:publicAccessShowAiConversation
                    bind:publicAccessAllowClipDownloads
                    bind:publicAccessShowAudio
                    bind:publicAccessShowSnapshots
                    bind:publicAccessShowClips
                    bind:publicAccessLocationPrecision
                    bind:publicAccessHistoricalDaysMode
                    bind:publicAccessHistoricalDays
                    bind:publicAccessMediaDaysMode
                    bind:publicAccessMediaHistoricalDays
                    bind:publicAccessRateLimitPerMinute
                    bind:publicAccessExternalBaseUrl
                    retentionDays={retentionDays}
                    addTrustedProxyHost={addTrustedProxyHost}
                    removeTrustedProxyHost={removeTrustedProxyHost}
                    acceptTrustedProxySuggestions={acceptTrustedProxySuggestions}
                />
                {/snippet}
                </LazyRoute>
            {/if}

            <!-- Data Tab -->
            {#if activeTab === 'data'}
                <LazyRoute loader={loadDataSettings} label={$_('settings.tabs.data')}>
                {#snippet content(DataSettings)}
                <DataSettings
                    bind:retentionDays
                    bind:maintenanceMaxConcurrent
                    bind:frigateMissingBehavior
                    bind:autoPurgeMissingClips
                    bind:autoPurgeMissingSnapshots
                    bind:autoAnalyzeUnknowns
                    bind:cacheClips
                    bind:cacheHighQualityEventSnapshots
                    bind:cacheHighQualityEventSnapshotJpegQuality
                    bind:cacheRetentionDays
                    bind:cachePerSpeciesMaximum
                    bind:cacheMaxSizeMb
                    bind:cacheAutomaticMultiBirdScan
                    bind:cacheBirdScanMode
                    bind:cachePerSpeciesMinimum
                    bind:backfillDateRange
                    bind:backfillStartDate
                    bind:backfillEndDate
                    {backfillCustomError}
                    {backfillCustomValid}
                    {maintenanceStats}
                    {retentionNote}
                    {cacheStats}
                    {cacheStatsError}
                    {cacheStatsLoading}
                    onRetryCacheStats={loadCacheStats}
                    {classifierStatus}
                    {cleaningUp}
                    {clearingFavorites}
                    {purgingMissingMedia}
                    {cleaningCache}
                    {backfilling}
                    {backfillResult}
                    {backfillTotal}
                    {weatherBackfilling}
                    {weatherBackfillResult}
                    {weatherBackfillTotal}
                    {taxonomyStatus}
                    {syncingTaxonomy}
                    {timezoneRepairPreview}
                    {previewingTimezoneRepair}
                    {applyingTimezoneRepair}
                    {resettingDatabase}
                    {clearingFeedback}
                    {exportingConfigBackup}
                    {importingConfigBackup}
                    {analyzingUnknowns}
                    {analysisStatus}
                    {analysisTotal}
                    {handleCleanup}
                    {handleClearFavorites}
                    {handlePurgeMissingMedia}
                    {handleCacheCleanup}
                    {handleStartTaxonomySync}
                    {handlePreviewTimezoneRepair}
                    {handleApplyTimezoneRepair}
                    {handleBackfill}
                    {handleWeatherBackfill}
                    {handleExportConfigBackup}
                    {handleImportConfigBackup}
                    {handleAnalyzeUnknowns}
                    {handleResetDatabase}
                    {handleClearFeedback}
                />
                {/snippet}
                </LazyRoute>
            {/if}

            <!-- Appearance Tab -->
            {#if activeTab === 'appearance'}
                <LazyRoute
                    loader={loadAppearanceTab}
                    label={$_('settings.tabs.appearance')}
                    props={{
                        currentTheme,
                        currentLocale: $locale || 'en',
                        draft: appearanceDraft,
                        onchange: updateAppearance,
                        setTheme,
                        setLanguage
                    }}
                />
            {/if}

            <!-- Accessibility Tab -->
            {#if activeTab === 'accessibility'}
                <LazyRoute
                    loader={loadAccessibilityTab}
                    label={$_('settings.tabs.accessibility')}
                    props={{
                        draft: accessibilityDraft,
                        onchange: (patch: Partial<AccessibilityDraft>) => (accessibilityDraft = { ...accessibilityDraft, ...patch })
                    }}
                />
            {/if}

            {#if activeTab === 'beta'}
                <!-- One card per beta feature. A new feature is another <li> holding its own BetaFeatureCard. -->
                <div class="space-y-4" data-beta-page>
                    <header class="space-y-1 px-1" aria-labelledby="beta-page-title">
                        <h3 id="beta-page-title" class="font-display text-xl font-bold text-slate-900 dark:text-white">{$_('settings.beta.title', { default: 'Beta features' })}</h3>
                        <p class="max-w-prose text-sm text-slate-600 dark:text-slate-400" data-beta-intro>
                            {$_('settings.beta.intro', { default: 'Features still being tested. Each one is off until you turn it on, and may change or be removed. Turning a feature off keeps what it has already recorded. Switches here take effect when you save changes.' })}
                        </p>
                    </header>
                    <ul class="space-y-4" aria-labelledby="beta-page-title" data-beta-feature-list>
                        <li>
                            <LazyRoute loader={loadGardenBetaSettings} label={$_('settings.tabs.beta')}>
                            {#snippet content(GardenBetaSettings)}
                            <GardenBetaSettings
                                bind:enabled={betaGardenAnimals}
                                cameras={gardenCameras}
                                motionCameras={gardenMotionCameras}
                                bind:labels={gardenLabels}
                                bind:motionConfidence={gardenMotionConfidence}
                                notificationsEnabled={gardenNotificationsEnabled}
                                onOpenNotifications={() => handleTabChange('notifications')}
                                onOpenLocation={() => openIntegrationField('#location-lat', '#setting-location-mode + div button[aria-pressed="false"]')}
                                bind:automaticNaming={gardenAutomaticNaming}
                                bind:namingThreshold={gardenNamingThreshold}
                                bind:domesticBirds={gardenDomesticBirds}
                                savedMotionConfidence={settingsStore.settings?.garden_motion_confidence}
                                onNavigate={onNavigate ? (path) => onNavigate(path) : undefined}
                                onOpenCameras={openCameraSettings}
                            />
                            {/snippet}
                            </LazyRoute>
                        </li>
                    </ul>
                </div>
            {/if}

            {#if activeTab === 'debug'}
                {#snippet debugIcon()}
                    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h6m-5 0v5l-5 9a2 2 0 0 0 1.74 3h10.52A2 2 0 0 0 19 17l-5-9V3m-6 11h8" /></svg>
                {/snippet}
                <SettingsCard
                    accent
                    iconSnippet={debugIcon}
                    title={$_('settings.debug.title')}
                    description={$_('settings.debug.subtitle')}
                >
                    <SettingsRow
                        labelId="setting-strict-non-finite-output"
                        label={$_('settings.debug.strict_non_finite_output', { default: 'Strict non-finite output handling' })}
                        description={$_('settings.debug.strict_non_finite_output_desc', { default: 'When enabled, all-non-finite classifier outputs are rejected and trigger runtime recovery. Disable only for controlled debugging.' })}
                    >
                        <SettingsToggle
                            checked={strictNonFiniteOutput}
                            labelledBy="setting-strict-non-finite-output"
                            srLabel={$_('settings.debug.strict_non_finite_output', { default: 'Strict non-finite output handling' })}
                            onchange={(value) => (strictNonFiniteOutput = value)}
                        />
                    </SettingsRow>

                    <AdvancedSection
                        id="debug-model-evaluation"
                        title={$_('settings.debug.model_eval_title')}
                        description={$_('settings.debug.model_eval_desc')}
                    >
                        <div class="flex items-center justify-between gap-4">
                            <p class="text-sm font-medium text-slate-600 dark:text-slate-400">
                                {$_('settings.debug.model_eval_action_desc')}
                            </p>
                            <button
                                type="button"
                                onclick={() => onNavigate && onNavigate('/diagnostics/model-eval')}
                                class="min-h-11 shrink-0 rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white transition-colors hover:bg-slate-700 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white dark:focus-visible:ring-offset-slate-950"
                            >
                                {$_('settings.debug.model_eval_open')}
                            </button>
                        </div>
                    </AdvancedSection>
                </SettingsCard>
            {/if}
    {/snippet}
</SettingsPage>
