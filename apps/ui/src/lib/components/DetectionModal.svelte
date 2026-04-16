<script lang="ts">
    import Map from './Map.svelte';
    import {
        getSnapshotUrl,
        fetchSnapshotStatus,
        generateHighQualityBirdCropSnapshot,
        analyzeDetection,
        updateDetectionSpecies,
        hideDetection,
        deleteDetection,
        favoriteDetection,
        unfavoriteDetection,
        searchSpecies,
        fetchAudioContext,
        createInaturalistDraft,
        submitInaturalistObservation,
        fetchSpeciesInfo,
        fetchEbirdNearby,
        fetchEbirdNotable,
        fetchClassifierStatus,
        fetchDetectionConversation,
        sendDetectionConversationMessage,
        type SearchResult,
        type AudioContextDetection,
        type InaturalistDraft,
        type SpeciesInfo,
        type EbirdNearbyResult,
        type EbirdNotableResult,
        type ConversationTurn,
        type SnapshotStatusResponse
    } from '../api';
    import type { Detection } from '../api';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import VideoAnalysisFilmReel from './VideoAnalysisFilmReel.svelte';
    import { detectionsStore, type ReclassificationProgress } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { getBirdNames } from '../naming';
    import { _ } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import { onDestroy, onMount } from 'svelte';
    import { trapFocus } from '../utils/focus-trap';
    import { FRIGATE_LOGO_URL } from '../assets';
    import { getDetectionClassificationSource } from '../detection-classification-source';
    import { formatDateTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import { getManualTagSearchOptions } from '../search/manual-tag-search';
    import {
        formatPrecipitation,
        formatWindSpeed,
        getTemperatureUnitForSystem,
        resolveWeatherUnitSystem
    } from '../utils/weather-units';
    import { renderMarkdown } from '../utils/markdown';
    import { getVideoFailureInsight, hasFrigateMediaIssue } from '../utils/frigate-errors';
    import { classifyInferenceProvider } from '../utils/inference-provider';

    interface Props {
        detection: Detection;
        classifierLabels: string[];
        llmReady: boolean;
        showVideoButton?: boolean;
        onClose: () => void;
        onReclassify?: (detection: Detection) => void;
        onPlayVideo?: (frigateEvent: string, playIntent?: 'auto' | 'user') => void;
        onFetchFullVisit?: (detection: Detection) => void;
        onDeleteSuccess?: (frigateEvent: string, detectionTime?: string) => void | Promise<void>;
        onHideSuccess?: (frigateEvent: string, detectionTime?: string) => void | Promise<void>;
        onViewSpecies: (speciesName: string) => void;
        readOnly?: boolean;
        fullVisitAvailable?: boolean;
        fullVisitFetched?: boolean;
        fullVisitFetchState?: 'idle' | 'fetching' | 'ready' | 'failed';
    }

    let {
        detection,
        classifierLabels,
        llmReady,
        showVideoButton = false,
        onClose,
        onReclassify,
        onPlayVideo,
        onFetchFullVisit,
        onDeleteSuccess,
        onHideSuccess,
        onViewSpecies,
        readOnly = false,
        fullVisitAvailable = false,
        fullVisitFetched = false,
        fullVisitFetchState = 'idle'
    }: Props = $props();
    let currentClassificationSource = $derived(getDetectionClassificationSource(detection));

    // State
    let modalElement = $state<HTMLElement | null>(null);
    let previousBodyPosition = '';
    let previousBodyTop = '';
    let previousBodyWidth = '';
    let previousBodyOverflow = '';
    let previousHtmlOverflow = '';
    let scrollLockY = 0;
    let scrollLocked = false;
    let analyzingAI = $state(false);
    let audioContextOpen = $state(false);
    let audioContextLoading = $state(false);
    let audioContextLoaded = $state(false);
    let audioContext = $state<AudioContextDetection[]>([]);
    let audioContextError = $state<string | null>(null);
    let weatherDetailsOpen = $state(false);
    let inatPanelOpen = $state(false);
    let inatLoading = $state(false);
    let inatSubmitting = $state(false);
    let inatError = $state<string | null>(null);
    let inatDraft = $state<InaturalistDraft | null>(null);
    let inatNotes = $state('');
    let inatLat = $state<number | null>(null);
    let inatLon = $state<number | null>(null);
    let inatPlace = $state('');
    let inatPreview = $state(false);

    // Enrichment state
    let speciesInfo = $state<SpeciesInfo | null>(null);
    let speciesInfoLoading = $state(false);
    let speciesInfoError = $state<string | null>(null);
    let ebirdNearby = $state<EbirdNearbyResult | null>(null);
    let ebirdNearbyLoading = $state(false);
    let ebirdNearbyError = $state<string | null>(null);
    let ebirdNotable = $state<EbirdNotableResult | null>(null);
    let ebirdNotableLoading = $state(false);
    let ebirdNotableError = $state<string | null>(null);
    let lastEnrichmentKey = $state<string | null>(null);

    $effect(() => {
        if (modalElement) {
            return trapFocus(modalElement);
        }
    });

    function lockDocumentScroll() {
        if (scrollLocked || typeof document === 'undefined' || typeof window === 'undefined') return;
        const body = document.body;
        const html = document.documentElement;
        scrollLockY = window.scrollY;
        previousBodyPosition = body.style.position;
        previousBodyTop = body.style.top;
        previousBodyWidth = body.style.width;
        previousBodyOverflow = body.style.overflow;
        previousHtmlOverflow = html.style.overflow;
        body.style.position = 'fixed';
        body.style.top = `-${scrollLockY}px`;
        body.style.width = '100%';
        body.style.overflow = 'hidden';
        html.style.overflow = 'hidden';
        scrollLocked = true;
    }

    function unlockDocumentScroll() {
        if (!scrollLocked || typeof document === 'undefined' || typeof window === 'undefined') return;
        const body = document.body;
        const html = document.documentElement;
        body.style.position = previousBodyPosition;
        body.style.top = previousBodyTop;
        body.style.width = previousBodyWidth;
        body.style.overflow = previousBodyOverflow;
        html.style.overflow = previousHtmlOverflow;
        window.scrollTo(0, scrollLockY);
        scrollLocked = false;
    }

    function withCacheBust(url: string, token: number): string {
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}v=${token}`;
    }

    const syncDarkMode = () => {
        if (typeof document === 'undefined') return;
        isDarkMode = document.documentElement.classList.contains('dark');
    };

    onMount(() => {
        syncDarkMode();
        if (typeof document === 'undefined') return;
        const observer = new MutationObserver(syncDarkMode);
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        const syncDiagnosticsToggle = () => {
            if (typeof window === 'undefined') return;
            aiDiagnosticsEnabled = window.localStorage.getItem('ai_diagnostics_enabled') === '1';
        };
        syncDiagnosticsToggle();
        const onToggleChanged = () => syncDiagnosticsToggle();
        window.addEventListener('ai-diagnostics-enabled-changed', onToggleChanged as any);
        return () => {
            observer.disconnect();
            window.removeEventListener('ai-diagnostics-enabled-changed', onToggleChanged as any);
        };
    });

    onMount(() => {
        lockDocumentScroll();
        return () => {
            unlockDocumentScroll();
        };
    });

    $effect(() => {
        const eventId = detection?.frigate_event;
        if (!eventId || !hasOwnerDetectionActions) {
            snapshotStatus = null;
            snapshotStatusLoading = false;
            return;
        }

        let cancelled = false;
        snapshotStatusLoading = true;

        void (async () => {
            try {
                const status = await fetchSnapshotStatus(eventId);
                if (!cancelled && detection.frigate_event === eventId) {
                    snapshotStatus = status;
                }
            } catch {
                if (!cancelled) {
                    snapshotStatus = null;
                }
            } finally {
                if (!cancelled) {
                    snapshotStatusLoading = false;
                }
            }
        })();

        return () => {
            cancelled = true;
        };
    });

    const hasMarkdownHeadings = (value: string | null) => {
        if (!value) return false;
        return /(^|\n)#{1,6}\s+/.test(value) || /(^|\n)[A-Z][A-Za-z0-9\s/&()\-]+:\s*$/.test(value);
    };

    type MarkdownStyleSample = {
        heading: Record<string, string> | null;
        paragraph: Record<string, string> | null;
        listItem: Record<string, string> | null;
        blockquote: Record<string, string> | null;
        code: Record<string, string> | null;
        pre: Record<string, string> | null;
        link: Record<string, string> | null;
    };

    const buildSample = (value: string | null) => {
        if (!value) return '';
        return value.replace(/\s+/g, ' ').trim().slice(0, 240);
    };

    const describeElement = (element: Element | null) => {
        if (!element || typeof window === 'undefined') return null;
        const style = getComputedStyle(element as HTMLElement);
        return {
            tag: element.tagName.toLowerCase(),
            color: style.color,
            backgroundColor: style.backgroundColor,
            fontSize: style.fontSize,
            fontWeight: style.fontWeight,
            lineHeight: style.lineHeight,
            marginTop: style.marginTop,
            marginBottom: style.marginBottom,
            textTransform: style.textTransform,
            letterSpacing: style.letterSpacing,
            textDecorationLine: style.textDecorationLine
        };
    };

    const countMarkdownNodes = (container: HTMLElement | null) => {
        if (!container) return { headings: 0, paragraphs: 0, listItems: 0, blockquotes: 0, code: 0, pre: 0, links: 0 };
        return {
            headings: container.querySelectorAll('h1,h2,h3,h4,h5,h6').length,
            paragraphs: container.querySelectorAll('p').length,
            listItems: container.querySelectorAll('li').length,
            blockquotes: container.querySelectorAll('blockquote').length,
            code: container.querySelectorAll('code').length,
            pre: container.querySelectorAll('pre').length,
            links: container.querySelectorAll('a').length
        };
    };

    const sampleMarkdownStyles = (container: HTMLElement | null): MarkdownStyleSample => {
        if (!container) {
            return {
                heading: null,
                paragraph: null,
                listItem: null,
                blockquote: null,
                code: null,
                pre: null,
                link: null
            };
        }
        return {
            heading: describeElement(container.querySelector('h1, h2, h3, h4, h5, h6')),
            paragraph: describeElement(container.querySelector('p')),
            listItem: describeElement(container.querySelector('li')),
            blockquote: describeElement(container.querySelector('blockquote')),
            code: describeElement(container.querySelector('code')),
            pre: describeElement(container.querySelector('pre')),
            link: describeElement(container.querySelector('a'))
        };
    };

    const collectAiDiagnostics = () => {
        if (!modalElement || typeof window === 'undefined') return;
        const latestAssistant = [...conversationTurns].reverse().find((turn) => turn.role === 'assistant')?.content ?? null;
        const panelContent = modalElement.querySelector('.ai-panel__content.ai-markdown') as HTMLElement | null;
        const panelHeading = panelContent?.querySelector('h1, h2, h3, h4, h5, h6') as HTMLElement | null;
        const panelSurface = modalElement.querySelector('.ai-panel.ai-surface') as HTMLElement | null;
        const bubbleContent = modalElement.querySelector('.ai-bubble--assistant .ai-bubble__content.ai-markdown') as HTMLElement | null;
        const bubbleHeading = bubbleContent?.querySelector('h1, h2, h3, h4, h5, h6') as HTMLElement | null;
        const bubbleSurface = modalElement.querySelector('.ai-bubble--assistant') as HTMLElement | null;
        const root = document.documentElement;
        const body = document.body;

        aiDiagnostics = {
            theme: root.classList.contains('dark') ? 'dark' : 'light',
            rootClasses: root.className,
            bodyClasses: body?.className ?? '',
            modalHasDarkAncestor: Boolean(modalElement.closest('.dark')),
            modalClasses: modalElement.className,
            modalDataTheme: modalElement.getAttribute('data-theme') ?? '',
            analysisTextColor: panelContent ? getComputedStyle(panelContent).color : 'n/a',
            analysisHeadingColor: panelHeading ? getComputedStyle(panelHeading).color : 'n/a',
            analysisSurfaceColor: panelSurface ? getComputedStyle(panelSurface).color : 'n/a',
            analysisSurfaceBackground: panelSurface ? getComputedStyle(panelSurface).backgroundImage || getComputedStyle(panelSurface).backgroundColor : 'n/a',
            analysisSurfaceBorder: panelSurface ? getComputedStyle(panelSurface).borderColor : 'n/a',
            conversationTextColor: bubbleContent ? getComputedStyle(bubbleContent).color : 'n/a',
            conversationHeadingColor: bubbleHeading ? getComputedStyle(bubbleHeading).color : 'n/a',
            conversationSurfaceColor: bubbleSurface ? getComputedStyle(bubbleSurface).color : 'n/a',
            conversationSurfaceBackground: bubbleSurface ? getComputedStyle(bubbleSurface).backgroundImage || getComputedStyle(bubbleSurface).backgroundColor : 'n/a',
            conversationSurfaceBorder: bubbleSurface ? getComputedStyle(bubbleSurface).borderColor : 'n/a',
            analysisMarkdownCounts: countMarkdownNodes(panelContent),
            conversationMarkdownCounts: countMarkdownNodes(bubbleContent),
            analysisMarkdownSampleStyles: sampleMarkdownStyles(panelContent),
            conversationMarkdownSampleStyles: sampleMarkdownStyles(bubbleContent),
            analysisHasHeadings: hasMarkdownHeadings(aiAnalysis),
            conversationHasHeadings: hasMarkdownHeadings(latestAssistant),
            analysisSample: buildSample(aiAnalysis),
            conversationSample: buildSample(latestAssistant)
        };
    };

    
    const copyAiFullBundle = async () => {
        collectAiDiagnostics();
        const latestAssistant = [...conversationTurns].reverse().find((turn) => turn.role === 'assistant')?.content ?? null;
        const payload = JSON.stringify(
            {
                diagnostics: aiDiagnostics,
                analysis: aiAnalysis ?? '',
                conversation_latest_assistant: latestAssistant ?? '',
                prompts: {
                    analysis_prompt_template: settingsStore.settings?.llm_analysis_prompt_template ?? '',
                    conversation_prompt_template: settingsStore.settings?.llm_conversation_prompt_template ?? ''
                }
            },
            null,
            2
        );
        await navigator.clipboard.writeText(payload);
    };

    let aiAnalysis = $state<string | null>(null);
    let conversationTurns = $state<ConversationTurn[]>([]);
    let conversationInput = $state('');
    let conversationLoading = $state(false);
    let conversationSending = $state(false);
    let conversationError = $state<string | null>(null);
    let lastEventId = $state<string | null>(null);
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);
    let pendingManualTagId = $state<string | null>(null);
    let favoritePending = $state(false);
    let manualHqBirdCropPending = $state(false);
    let snapshotStatus = $state<SnapshotStatusResponse | null>(null);
    let snapshotStatusLoading = $state(false);
    let snapshotRefreshToken = $state(Date.now());
    let tagSearchQuery = $state('');
    let searchResults = $state<SearchResult[]>([]);
    let isSearching = $state(false);
    let videoErrorDetailsOpen = $state(false);
    let aiDiagnostics = $state<{
        theme: string;
        rootClasses: string;
        bodyClasses: string;
        modalHasDarkAncestor: boolean;
        modalClasses: string;
        modalDataTheme: string;
        analysisTextColor: string;
        analysisHeadingColor: string;
        analysisSurfaceColor: string;
        analysisSurfaceBackground: string;
        analysisSurfaceBorder: string;
        conversationTextColor: string;
        conversationHeadingColor: string;
        conversationSurfaceColor: string;
        conversationSurfaceBackground: string;
        conversationSurfaceBorder: string;
        analysisMarkdownCounts: Record<string, number>;
        conversationMarkdownCounts: Record<string, number>;
        analysisMarkdownSampleStyles: MarkdownStyleSample;
        conversationMarkdownSampleStyles: MarkdownStyleSample;
        analysisHasHeadings: boolean;
        conversationHasHeadings: boolean;
        analysisSample: string;
        conversationSample: string;
    } | null>(null);
    const debugUiEnabled = $derived(settingsStore.settings?.debug_ui_enabled ?? false);
    let isDarkMode = $state(false);
    let aiDiagnosticsEnabled = $state(false);

    

    // Reclassification progress
    let reclassifyProgress = $derived(
        detectionsStore.progressMap.get(detection.frigate_event) || null
    );
    let canPlayVideo = $derived(showVideoButton && !!onPlayVideo && (detection.has_clip || fullVisitFetched) && !reclassifyProgress);
    let showFetchFullVisitAction = $derived(!!onFetchFullVisit && fullVisitAvailable && !fullVisitFetched && !reclassifyProgress);
    let fullVisitFetchLabel = $derived.by(() => {
        if (fullVisitFetchState === 'fetching') {
            return $_('video_player.fetching_full_visit', { default: 'Fetching...' });
        }
        if (fullVisitFetchState === 'failed') {
            return $_('video_player.fetch_full_visit_retry', { default: 'Retry full clip' });
        }
        return $_('video_player.fetch_full_visit', { default: 'Fetch full clip' });
    });
    let awaitingReclassifyOverlay = $state(false);
    let videoAnalysisStatus = $derived(detection.video_classification_status ?? null);
    let videoAnalysisActive = $derived(videoAnalysisStatus === 'processing' || videoAnalysisStatus === 'pending');
    let placeholderVideoAnalysisProgress = $derived.by(() => ({
        eventId: detection.frigate_event,
        currentFrame: 0,
        totalFrames: Math.max(1, Math.floor(settingsStore.settings?.video_classification_frames ?? 15)),
        frameIndex: 0,
        clipTotal: Math.max(1, Math.floor(settingsStore.settings?.video_classification_frames ?? 15)),
        modelName: null,
        frameResults: [],
        status: 'running' as const,
        startedAt: 0,
        lastUpdateAt: 0,
        results: []
    }));
    let modalVideoAnalysisProgress = $derived(reclassifyProgress ?? placeholderVideoAnalysisProgress);
    let showMediaSlotVideoAnalysis = $derived(!reclassifyProgress && videoAnalysisActive && !awaitingReclassifyOverlay);
    let videoInferenceProvider = $state<string | null>(null);
    let videoInferenceBackend = $state<string | null>(null);
    let videoInferenceBadge = $derived(
        classifyInferenceProvider(videoInferenceProvider, videoInferenceBackend)
    );
    let completedVideoInferenceBadge = $derived(
        classifyInferenceProvider(
            detection.video_classification_provider ?? null,
            detection.video_classification_backend ?? null
        )
    );

    // Naming logic
    const showCommon = $derived(settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true);
    const preferSci = $derived(settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false);
    const naming = $derived(getBirdNames(detection, showCommon, preferSci));
    const primaryName = $derived(naming.primary);
    const subName = $derived(naming.secondary);
    const audioContextSpecies = $derived.by(() => {
        const seen = new Set<string>();
        const values: string[] = [];
        const add = (candidate: unknown) => {
            if (typeof candidate !== 'string') return;
            const normalized = candidate.trim();
            if (!normalized) return;
            const key = normalized.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            values.push(normalized);
        };
        add(detection.audio_species);
        for (const species of detection.audio_context_species ?? []) {
            add(species);
        }
        return values;
    });
    const hasAudioContext = $derived(detection.audio_confirmed || audioContextSpecies.length > 0);
    const audioNearbySummary = $derived(audioContextSpecies.join(', '));
    const hasWeather = $derived(
        detection.temperature !== undefined && detection.temperature !== null ||
        !!detection.weather_condition ||
        detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null ||
        detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null ||
        detection.weather_precipitation !== undefined && detection.weather_precipitation !== null ||
        detection.weather_rain !== undefined && detection.weather_rain !== null ||
        detection.weather_snowfall !== undefined && detection.weather_snowfall !== null
    );
    const inatEnabled = $derived(settingsStore.settings?.inaturalist_enabled ?? authStore.inaturalistEnabled ?? false);
    const inatConnectedUser = $derived(settingsStore.settings?.inaturalist_connected_user ?? null);
    const canShowInat = $derived(!readOnly && authStore.canModify && inatEnabled && (!!inatConnectedUser || inatPreview));
    const hasOwnerDetectionActions = $derived(authStore.hasOwnerAccess && !readOnly);
    const snapshotImageUrl = $derived.by(() => withCacheBust(getSnapshotUrl(detection.frigate_event), snapshotRefreshToken));
    const showManualHqBirdCropAction = $derived(
        hasOwnerDetectionActions
        && !showMediaSlotVideoAnalysis
        && !reclassifyProgress
        && Boolean(snapshotStatus?.can_generate_hq_bird_crop)
    );

    const UNKNOWN_SPECIES_LABELS = new Set(['unknown', 'unknown bird', 'background']);
    const isUnknownSpecies = $derived(UNKNOWN_SPECIES_LABELS.has((detection.display_name || '').trim().toLowerCase()));

    const enrichmentModeSetting = $derived(settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment');
    const enrichmentSingleProviderSetting = $derived(settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia');
    const enrichmentSummaryProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_summary_source ?? authStore.enrichmentSummarySource ?? 'wikipedia')
    );
    const enrichmentSightingsProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_sightings_source ?? authStore.enrichmentSightingsSource ?? 'disabled')
    );
    const enrichmentSeasonalityProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_seasonality_source ?? authStore.enrichmentSeasonalitySource ?? 'disabled')
    );
    const enrichmentRarityProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_rarity_source ?? authStore.enrichmentRaritySource ?? 'disabled')
    );
    const enrichmentLinksProviders = $derived(
        enrichmentModeSetting === 'single'
            ? [enrichmentSingleProviderSetting]
            : (settingsStore.settings?.enrichment_links_sources ?? authStore.enrichmentLinksSources ?? ['wikipedia', 'inaturalist'])
    );
    const enrichmentLinksProvidersNormalized = $derived(
        enrichmentLinksProviders.map((provider) => String(provider || '').toLowerCase())
    );
    const ebirdEnabled = $derived(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled ?? false);
    const ebirdRadius = $derived(settingsStore.settings?.ebird_default_radius_km ?? 25);
    const ebirdDaysBack = $derived(settingsStore.settings?.ebird_default_days_back ?? 14);
    const showEbirdNearby = $derived(
        enrichmentSightingsProvider === 'ebird' || enrichmentSeasonalityProvider === 'ebird'
    );
    const showEbirdNotable = $derived(enrichmentRarityProvider === 'ebird');
    const frigateIssueBadgeVisible = $derived(hasFrigateMediaIssue(detection));
    const videoFailureInsight = $derived.by(() => getVideoFailureInsight(detection, $_));

    function formatEbirdDate(dateStr?: string | null) {
        if (!dateStr) return '—';
        return formatDateTime(dateStr);
    }

    onMount(() => {
        try {
            const params = new URLSearchParams(window.location.search);
            const queryPreview = params.get('inat_preview');
            const storedPreview = window.localStorage.getItem('inat_preview');
            inatPreview = queryPreview === '1' || storedPreview === '1';
        } catch {
            inatPreview = false;
        }
    });

    $effect(() => {
        if (!detection?.frigate_event) return;
        if (detection.frigate_event !== lastEventId) {
            lastEventId = detection.frigate_event;
            videoErrorDetailsOpen = false;
            aiAnalysis = llmReady ? (detection.ai_analysis || null) : null;
            inatPanelOpen = false;
            inatDraft = null;
            inatNotes = '';
            inatLat = null;
            inatLon = null;
            inatPlace = '';
            conversationTurns = [];
            conversationInput = '';
            conversationError = null;
            if (aiAnalysis && llmReady && authStore.canViewAiConversation) {
                loadConversation();
            }
        }
    });

    $effect(() => {
        if (!llmReady) {
            aiAnalysis = null;
            conversationTurns = [];
            conversationInput = '';
            conversationError = null;
        }
    });

    async function loadSpeciesInfo(speciesName: string) {
        speciesInfoLoading = true;
        speciesInfoError = null;
        try {
            speciesInfo = await fetchSpeciesInfo(speciesName);
        } catch (e: any) {
            speciesInfoError = e?.message || 'Failed to load species info';
        } finally {
            speciesInfoLoading = false;
        }
    }

    async function loadEbirdNearby(speciesName: string, scientificName?: string) {
        ebirdNearbyLoading = true;
        ebirdNearbyError = null;
        try {
            const res = await fetchEbirdNearby(speciesName, scientificName);
            if (res.status === 'error') {
                ebirdNearbyError = (res as any).message || 'Failed to load eBird sightings';
                ebirdNearby = null;
            } else {
                ebirdNearby = res;
            }
        } catch (e: any) {
            ebirdNearbyError = e?.message || 'Failed to load eBird sightings';
        } finally {
            ebirdNearbyLoading = false;
        }
    }

    async function loadEbirdNotable() {
        ebirdNotableLoading = true;
        ebirdNotableError = null;
        try {
            const res = await fetchEbirdNotable();
            if (res.status === 'error') {
                ebirdNotableError = (res as any).message || 'Failed to load eBird notable sightings';
                ebirdNotable = null;
            } else {
                ebirdNotable = res;
            }
        } catch (e: any) {
            ebirdNotableError = e?.message || 'Failed to load eBird notable sightings';
        } finally {
            ebirdNotableLoading = false;
        }
    }

    async function loadConversation() {
        if (!llmReady || !aiAnalysis || !authStore.canViewAiConversation) return;
        conversationLoading = true;
        conversationError = null;
        try {
            conversationTurns = await fetchDetectionConversation(detection.frigate_event);
        } catch (e: any) {
            conversationError = e?.message || $_('detection.ai.conversation_error');
        } finally {
            conversationLoading = false;
        }
    }

    async function sendConversation() {
        const message = conversationInput.trim();
        if (!message || conversationSending) return;
        conversationSending = true;
        conversationError = null;
        try {
            conversationTurns = await sendDetectionConversationMessage(detection.frigate_event, message);
            conversationInput = '';
        } catch (e: any) {
            conversationError = e?.message || $_('detection.ai.conversation_error');
        } finally {
            conversationSending = false;
        }
    }

    $effect(() => {
        if (!detection?.display_name || isUnknownSpecies) return;
        const enrichmentKey = [
            detection.display_name,
            enrichmentSummaryProvider,
            enrichmentSightingsProvider,
            enrichmentSeasonalityProvider,
            enrichmentRarityProvider,
            ebirdEnabled
        ].join('|');
        if (enrichmentKey === lastEnrichmentKey) return;
        lastEnrichmentKey = enrichmentKey;

        speciesInfo = null;
        speciesInfoError = null;
        ebirdNearby = null;
        ebirdNearbyError = null;
        ebirdNotable = null;
        ebirdNotableError = null;

        if (enrichmentSummaryProvider !== 'disabled') {
            void loadSpeciesInfo(detection.display_name);
        }

        const needsEbirdNearby = ebirdEnabled && showEbirdNearby;
        const needsEbirdNotable = ebirdEnabled && showEbirdNotable;
        if (needsEbirdNearby) {
            void loadEbirdNearby(detection.display_name, detection.scientific_name);
        }
        if (needsEbirdNotable) {
            void loadEbirdNotable();
        }
    });

    async function openInatPanel() {
        inatPanelOpen = !inatPanelOpen;
        if (!inatPanelOpen || !detection?.frigate_event) {
            return;
        }
        if (inatDraft && inatDraft.event_id === detection.frigate_event) {
            return;
        }
        inatLoading = true;
        inatError = null;
        try {
            if (inatPreview && !inatConnectedUser) {
                const defaults = settingsStore.settings;
                const observed = detection.detection_time ? new Date(detection.detection_time).toISOString() : new Date().toISOString();
                inatDraft = {
                    event_id: detection.frigate_event,
                    species_guess: primaryName,
                    observed_on_string: observed,
                    time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
                    latitude: defaults?.inaturalist_default_latitude ?? null,
                    longitude: defaults?.inaturalist_default_longitude ?? null,
                    place_guess: defaults?.inaturalist_default_place_guess ?? null,
                    snapshot_url: getSnapshotUrl(detection.frigate_event)
                };
            } else {
                inatDraft = await createInaturalistDraft(detection.frigate_event);
            }
            inatNotes = '';
            const defaults = settingsStore.settings;
            inatLat = inatDraft.latitude ?? defaults?.inaturalist_default_latitude ?? defaults?.location_latitude ?? null;
            inatLon = inatDraft.longitude ?? defaults?.inaturalist_default_longitude ?? defaults?.location_longitude ?? null;
            inatPlace = inatDraft.place_guess ?? defaults?.inaturalist_default_place_guess ?? '';
        } catch (e: any) {
            inatError = e?.message || 'Failed to load iNaturalist draft';
        } finally {
            inatLoading = false;
        }
    }

    async function submitInat() {
        if (!inatDraft || (inatPreview && !inatConnectedUser)) return;
        inatSubmitting = true;
        inatError = null;
        try {
            await submitInaturalistObservation({
                event_id: inatDraft.event_id,
                notes: inatNotes || undefined,
                latitude: inatLat ?? undefined,
                longitude: inatLon ?? undefined,
                place_guess: inatPlace || undefined
            });
            inatPanelOpen = false;
            inatNotes = '';
            inatLat = inatDraft.latitude ?? null;
            inatLon = inatDraft.longitude ?? null;
            inatPlace = inatDraft.place_guess ?? '';
        } catch (e: any) {
            inatError = e?.message || 'Failed to submit to iNaturalist';
        } finally {
            inatSubmitting = false;
        }
    }

    // Handle search input
    let searchTimeout: any;
    $effect(() => {
        const query = tagSearchQuery.trim();
        if (query.length === 0) {
            clearTimeout(searchTimeout);
            isSearching = true;
            (async () => {
                try {
                    searchResults = await searchSpecies('', 20, true);
                } catch (e) {
                    console.error("Search failed", e);
                    searchResults = classifierLabels.slice(0, 20).map(l => ({
                        id: l, display_name: l, common_name: null, scientific_name: null
                    }));
                } finally {
                    isSearching = false;
                }
            })();
            return;
        }

        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(async () => {
            isSearching = true;
            try {
                // Use backend search for rich taxonomy results
                const searchOptions = getManualTagSearchOptions(query);
                searchResults = await searchSpecies(query, searchOptions.limit, searchOptions.hydrateMissing);
            } catch (e) {
                console.error("Search failed", e);
                // Fallback to local filtering
                searchResults = classifierLabels
                    .filter(l => String(l).toLowerCase().includes(query.toLowerCase()))
                    .map(l => ({ id: String(l), display_name: String(l), common_name: null, scientific_name: null }));
            } finally {
                isSearching = false;
            }
        }, 300);
    });

    onDestroy(() => {
        if (searchTimeout) {
            clearTimeout(searchTimeout);
            searchTimeout = null;
        }
    });

    function getResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;

        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }

        return { primary: common || scientific || fallback, secondary: null };
    }

    function formatWindDirection(deg?: number | null): string {
        if (deg === null || deg === undefined || Number.isNaN(deg)) return '';
        const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
        const index = Math.round(((deg % 360) / 45)) % 8;
        return directions[index];
    }

    function formatPrecip(value?: number | null): string {
        return formatPrecipitation(value, weatherUnitSystem, {
            metric: $_('common.unit_mm', { default: 'mm' }),
            imperial: $_('common.unit_in', { default: 'in' })
        });
    }

    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));

    function formatAudioOffset(offsetSeconds: number): string {
        const abs = Math.abs(offsetSeconds);
        const mins = Math.floor(abs / 60);
        const secs = abs % 60;
        const label = mins > 0 ? `${mins}m` : `${secs}s`;
        if (offsetSeconds === 0) return '0s';
        return `${offsetSeconds > 0 ? '+' : '-'}${label}`;
    }

    async function toggleAudioContext(event: MouseEvent) {
        event.stopPropagation();
        audioContextOpen = !audioContextOpen;
        if (audioContextOpen && !audioContextLoaded && !audioContextLoading) {
            audioContextLoading = true;
            audioContextError = null;
            try {
                audioContext = await fetchAudioContext(
                    detection.detection_time,
                    detection.camera_name,
                    300,
                    6
                );
                audioContextLoaded = true;
            } catch (e) {
                audioContextError = $_('common.error');
            } finally {
                audioContextLoading = false;
            }
        }
    }

    async function handleAIAnalysis(force: boolean = false) {
        if (readOnly) return;
        if (!detection) return;
        if (!llmReady) return;
        analyzingAI = true;
        if (force) {
            aiAnalysis = null; // Clear existing analysis when forcing regeneration
            // Reset the conversation thread so the UI reflects the new analysis context.
            conversationTurns = [];
            conversationInput = '';
            conversationError = null;
            conversationLoading = false;
            conversationSending = false;
        }

        try {
            const result = await analyzeDetection(detection.frigate_event, force);
            aiAnalysis = result.analysis;
            detection.ai_analysis = result.analysis;
            detection.ai_analysis_timestamp = result.analysis_timestamp;
            detectionsStore.updateDetection({
                ...detection,
                ai_analysis: result.analysis,
                ai_analysis_timestamp: result.analysis_timestamp,
            });
            await loadConversation();
        } catch (e: any) {
            aiAnalysis = $_('detection.ai.error', { values: { message: e.message || 'Analysis failed' } });
        } finally {
            analyzingAI = false;
        }
    }

    async function handleManualTag(selection: SearchResult) {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly) return;
        if (!detection) return;
        if (updatingTag) return;

        const requestedSpecies = selection.id;
        updatingTag = true;
        pendingManualTagId = requestedSpecies;
        try {
            const result = await updateDetectionSpecies(detection.frigate_event, requestedSpecies);
            const appliedSpecies = result.new_species || result.species || requestedSpecies;
            const nextDetection = {
                ...detection,
                display_name: appliedSpecies,
                category_name: selection.scientific_name ?? selection.display_name ?? requestedSpecies,
                manual_tagged: true,
                scientific_name: selection.scientific_name ?? detection.scientific_name,
                common_name: selection.common_name ?? detection.common_name,
                ai_analysis: null,
                ai_analysis_timestamp: null,
            };
            detection.display_name = appliedSpecies;
            detection.category_name = nextDetection.category_name;
            detection.manual_tagged = true;
            detection.scientific_name = nextDetection.scientific_name;
            detection.common_name = nextDetection.common_name;
            detection.ai_analysis = null;
            detection.ai_analysis_timestamp = null;
            detectionsStore.updateDetection(nextDetection);
            showTagDropdown = false;
            tagSearchQuery = '';
            aiAnalysis = null; // Reset AI analysis for new species
            const names = getResultNames(selection);
            const successLabel = names.primary || appliedSpecies;
            toastStore.success(
                `${$_('notifications.event_reclassify', { default: 'Reclassification complete' })}: ${successLabel}`
            );
        } catch (e: any) {
            toastStore.error($_('notifications.reclassify_failed', { values: { message: e?.message || 'Unknown error' } }));
        } finally {
            pendingManualTagId = null;
            updatingTag = false;
        }
    }

    async function handleHide() {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly) return;
        if (!detection) return;
        try {
            const result = await hideDetection(detection.frigate_event);
            if (result.is_hidden) {
                detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
                await onHideSuccess?.(detection.frigate_event, detection.detection_time);
                onClose();
            }
        } catch (e: any) {
            alert($_('notifications.reclassify_failed', { values: { message: e.message } }));
        }
    }

    async function handleDelete() {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly) return;
        if (!detection) return;
        if (!confirm($_('actions.confirm_delete', { values: { species: detection.display_name } }))) return;

        try {
            await deleteDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            await onDeleteSuccess?.(detection.frigate_event, detection.detection_time);
            onClose();
        } catch (e: any) {
            alert($_('notifications.reclassify_failed', { values: { message: e.message } }));
        }
    }

    async function handleFavoriteToggle() {
        if (readOnly) return;
        if (!detection) return;
        favoritePending = true;
        try {
            if (detection.is_favorite) {
                await unfavoriteDetection(detection.frigate_event);
                detection.is_favorite = false;
                detectionsStore.updateDetection({ ...detection, is_favorite: false });
                toastStore.success($_('detection.favorite_removed', { default: 'Removed from favorites' }));
            } else {
                await favoriteDetection(detection.frigate_event);
                detection.is_favorite = true;
                detectionsStore.updateDetection({ ...detection, is_favorite: true });
                toastStore.success($_('detection.favorite_added', { default: 'Added to favorites' }));
            }
        } catch (e: any) {
            toastStore.error(e?.message || $_('common.error', { default: 'Action failed' }));
        } finally {
            favoritePending = false;
        }
    }

    async function handleManualHqBirdCrop(event: Event) {
        event.preventDefault();
        event.stopPropagation();
        if (!authStore.hasOwnerAccess || readOnly || !detection || manualHqBirdCropPending) return;

        manualHqBirdCropPending = true;
        try {
            const result = await generateHighQualityBirdCropSnapshot(detection.frigate_event);
            snapshotStatus = result;
            snapshotRefreshToken = Date.now();
            if (result.status === 'generated_hq_bird_crop') {
                toastStore.success($_('detection.manual_hq_bird_crop_success', { default: 'Generated HQ bird crop' }));
            } else if (result.status === 'already_hq_bird_crop') {
                toastStore.info($_('detection.manual_hq_bird_crop_already', { default: 'HQ bird crop already applied' }));
            } else {
                toastStore.info($_('detection.manual_hq_bird_crop_unavailable', { default: 'HQ bird crop unavailable; kept full HQ snapshot' }));
            }
        } catch (e: any) {
            toastStore.error(e?.message || $_('common.error', { default: 'Action failed' }));
        } finally {
            manualHqBirdCropPending = false;
            if (authStore.hasOwnerAccess && !readOnly) {
                try {
                    snapshotStatus = await fetchSnapshotStatus(detection.frigate_event);
                } catch {
                    // Keep the last known status if the refresh probe fails.
                }
            }
        }
    }

    function handleFetchFullVisitClick(event: Event) {
        event.preventDefault();
        event.stopPropagation();
        onFetchFullVisit?.(detection);
    }

    function handleReclassifyClick() {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly || !onReclassify) return;
        awaitingReclassifyOverlay = true;
        onReclassify(detection);
    }

    $effect(() => {
        if (reclassifyProgress) {
            awaitingReclassifyOverlay = false;
            return;
        }
        if (!videoAnalysisActive) {
            awaitingReclassifyOverlay = false;
        }
    });

    async function refreshVideoInferenceProvider() {
        const persistedProvider = detection.video_classification_provider ?? null;
        const persistedBackend = detection.video_classification_backend ?? null;
        if (persistedProvider || persistedBackend) {
            videoInferenceProvider = persistedProvider;
            videoInferenceBackend = persistedBackend;
            return;
        }
        try {
            const status = await fetchClassifierStatus();
            videoInferenceProvider = status.active_provider ?? null;
            videoInferenceBackend = status.inference_backend ?? null;
        } catch {
            videoInferenceProvider = null;
            videoInferenceBackend = null;
        }
    }

    $effect(() => {
        void refreshVideoInferenceProvider();
    });

    $effect(() => {
        const shouldPoll = Boolean(showMediaSlotVideoAnalysis || reclassifyProgress);
        if (!shouldPoll) return;

        let cancelled = false;
        const poll = async () => {
            if (cancelled) return;
            await refreshVideoInferenceProvider();
        };
        void poll();
        const handle = setInterval(() => {
            void poll();
        }, 5000);

        return () => {
            cancelled = true;
            clearInterval(handle);
        };
    });

    function handleSpeciesInfo() {
        onViewSpecies(detection.display_name);
        onClose();
    }
</script>

<style>
    .ai-surface {
        position: relative;
        overflow: hidden;
        padding: 1.25rem;
        border-radius: 1.25rem;
        background: linear-gradient(145deg, rgba(20, 184, 166, 0.08), rgba(14, 116, 144, 0.06));
        border: 1px solid rgba(20, 184, 166, 0.22);
        color: rgb(30 41 59);
        box-shadow: 0 12px 28px rgba(15, 118, 110, 0.15);
    }

    .ai-surface::before {
        content: '';
        position: absolute;
        inset: 0;
        pointer-events: none;
        border-radius: inherit;
        opacity: 0.85;
        background:
            radial-gradient(900px 420px at 18% 0%, rgba(20, 184, 166, 0.12), transparent 60%),
            radial-gradient(680px 420px at 92% 95%, rgba(14, 116, 144, 0.10), transparent 55%);
    }

    .ai-surface > * {
        position: relative;
        z-index: 1;
    }

    :global(.dark) .ai-surface,
    :global([data-theme='dark']) .ai-surface {
        /* Softer dark surface: keep the teal identity, reduce the "hard slab" look. */
        background: linear-gradient(145deg, rgba(15, 118, 110, 0.20), rgba(30, 41, 59, 0.78));
        border-color: rgba(45, 212, 191, 0.35);
        color: rgb(241 245 249);
        box-shadow: 0 14px 30px rgba(2, 6, 23, 0.42);
    }

    :global(.dark) .ai-surface::before,
    :global([data-theme='dark']) .ai-surface::before {
        opacity: 0.95;
        background:
            radial-gradient(980px 440px at 16% 0%, rgba(94, 234, 212, 0.14), transparent 62%),
            radial-gradient(760px 520px at 88% 90%, rgba(56, 189, 248, 0.10), transparent 58%),
            radial-gradient(520px 420px at 50% 50%, rgba(2, 6, 23, 0.22), transparent 60%);
    }

    /* Blue Tit theme — light */
    :global(.theme-bluetit:not(.dark)) .ai-surface {
        background: linear-gradient(145deg, rgba(37, 99, 235, 0.08), rgba(29, 78, 216, 0.05));
        border-color: rgba(37, 99, 235, 0.22);
        box-shadow: 0 12px 28px rgba(37, 99, 235, 0.14);
    }
    :global(.theme-bluetit:not(.dark)) .ai-surface::before {
        background:
            radial-gradient(900px 420px at 18% 0%, rgba(37, 99, 235, 0.12), transparent 60%),
            radial-gradient(680px 420px at 92% 95%, rgba(29, 78, 216, 0.10), transparent 55%);
    }

    /* Blue Tit theme — dark */
    :global(.theme-bluetit.dark) .ai-surface {
        background: linear-gradient(145deg, rgba(29, 78, 216, 0.22), rgba(15, 23, 42, 0.80));
        border-color: rgba(96, 165, 250, 0.35);
        box-shadow: 0 14px 30px rgba(2, 6, 23, 0.44);
    }
    :global(.theme-bluetit.dark) .ai-surface::before {
        background:
            radial-gradient(980px 440px at 16% 0%, rgba(96, 165, 250, 0.14), transparent 62%),
            radial-gradient(760px 520px at 88% 90%, rgba(251, 191, 36, 0.10), transparent 58%),
            radial-gradient(520px 420px at 50% 50%, rgba(2, 6, 23, 0.22), transparent 60%);
    }

    .ai-panel {
        position: relative;
    }

    .ai-panel__label {
        font-size: 0.6rem;
        letter-spacing: 0.25em;
        text-transform: uppercase;
        font-weight: 800;
        color: rgb(13 148 136);
        margin-bottom: 0.75rem;
    }

    :global(.dark) .ai-panel__label,
    :global([data-theme='dark']) .ai-panel__label {
        color: rgb(94 234 212);
    }

    :global(.theme-bluetit:not(.dark)) .ai-panel__label { color: rgb(29 78 216); }
    :global(.theme-bluetit.dark) .ai-panel__label { color: rgb(96 165 250); }

    :global(.dark) .ai-panel__content,
    :global([data-theme='dark']) .ai-panel__content {
        color: inherit;
    }

    :global(.ai-markdown-surface) {
        color: inherit;
    }

    :global(.ai-markdown-surface) {
        color: rgb(30 41 59);
    }

    :global(.dark .ai-markdown-surface),
    :global([data-theme='dark'] .ai-markdown-surface) {
        color: rgb(241 245 249);
    }

    :global(.ai-markdown-surface h1) {
        margin: 0.75rem 0 0.4rem;
        font-size: 1.0rem;
        letter-spacing: 0.02em;
        text-transform: none;
        font-weight: 900;
        color: rgb(13 148 136);
    }

    :global(.dark .ai-markdown-surface h1),
    :global([data-theme='dark'] .ai-markdown-surface h1) {
        color: rgb(94 234 212);
    }

    :global(.ai-markdown-surface h2) {
        margin: 0.7rem 0 0.35rem;
        font-size: 0.95rem;
        letter-spacing: 0.015em;
        text-transform: none;
        font-weight: 850;
        color: rgb(13 148 136);
    }

    :global(.dark .ai-markdown-surface h2),
    :global([data-theme='dark'] .ai-markdown-surface h2) {
        color: rgb(94 234 212);
    }

    :global(.ai-markdown-surface h3) {
        margin: 0.65rem 0 0.3rem;
        font-size: 0.9rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 800;
        color: rgb(13 148 136);
    }

    :global(.dark .ai-markdown-surface h3),
    :global([data-theme='dark'] .ai-markdown-surface h3) {
        color: rgb(94 234 212);
    }

    :global(.ai-markdown-surface h4) {
        margin: 0.6rem 0 0.25rem;
        font-size: 0.86rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 800;
        color: rgb(13 148 136);
    }

    :global(.dark .ai-markdown-surface h4),
    :global([data-theme='dark'] .ai-markdown-surface h4) {
        color: rgb(94 234 212);
    }

    :global(.ai-markdown-surface h5),
    :global(.ai-markdown-surface h6) {
        margin: 0.55rem 0 0.2rem;
        font-size: 0.82rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 750;
        color: rgb(13 148 136);
    }

    :global(.dark .ai-markdown-surface h5),
    :global(.dark .ai-markdown-surface h6),
    :global([data-theme='dark'] .ai-markdown-surface h5),
    :global([data-theme='dark'] .ai-markdown-surface h6) {
        color: rgb(94 234 212);
    }

    :global(.ai-markdown-surface p) {
        margin: 0.3rem 0;
        font-size: 0.88rem;
        line-height: 1.55;
        color: inherit;
    }

    :global(.dark .ai-markdown-surface p),
    :global([data-theme='dark'] .ai-markdown-surface p) {
        color: inherit;
    }

    :global(.ai-markdown-surface ul) {
        margin: 0.35rem 0 0.65rem;
        padding-left: 1.2rem;
        list-style: disc;
        list-style-position: outside;
    }

    :global(.ai-markdown-surface ol) {
        margin: 0.35rem 0 0.65rem;
        padding-left: 1.3rem;
        list-style: decimal;
        list-style-position: outside;
    }

    :global(.ai-markdown-surface ul ul),
    :global(.ai-markdown-surface ol ol),
    :global(.ai-markdown-surface ul ol),
    :global(.ai-markdown-surface ol ul) {
        margin: 0.2rem 0 0.4rem;
    }

    :global(.ai-markdown-surface li) {
        margin: 0.25rem 0;
        font-size: 0.88rem;
        color: inherit;
    }

    :global(.ai-markdown-surface li::marker) {
        color: rgba(13, 148, 136, 0.55);
    }

    :global(.dark .ai-markdown-surface li::marker),
    :global([data-theme='dark'] .ai-markdown-surface li::marker) {
        color: rgba(94, 234, 212, 0.55);
    }

    :global(.dark .ai-markdown-surface li),
    :global([data-theme='dark'] .ai-markdown-surface li) {
        color: inherit;
    }

    :global(.ai-markdown-surface strong) {
        font-weight: 700;
        color: rgb(15 118 110);
    }

    :global(.dark .ai-markdown-surface strong),
    :global([data-theme='dark'] .ai-markdown-surface strong) {
        color: rgb(153 246 228);
    }

    :global(.ai-markdown-surface em) {
        color: rgba(30, 41, 59, 0.8);
    }

    :global(.dark .ai-markdown-surface em),
    :global([data-theme='dark'] .ai-markdown-surface em) {
        color: rgba(226, 232, 240, 0.82);
    }

    :global(.ai-markdown-surface code) {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.75rem;
        padding: 0.1rem 0.3rem;
        border-radius: 0.4rem;
        background: rgba(15, 118, 110, 0.1);
        color: rgb(15 118 110);
    }

    :global(.dark .ai-markdown-surface code),
    :global([data-theme='dark'] .ai-markdown-surface code) {
        background: rgba(45, 212, 191, 0.25);
        color: rgb(153 246 228);
    }

    :global(.ai-markdown-surface pre) {
        margin: 0.5rem 0 0.75rem;
        padding: 0.75rem 0.9rem;
        border-radius: 0.75rem;
        background: rgba(15, 118, 110, 0.08);
        border: 1px solid rgba(15, 118, 110, 0.12);
        overflow-x: auto;
    }

    :global(.dark .ai-markdown-surface pre),
    :global([data-theme='dark'] .ai-markdown-surface pre) {
        background: rgba(15, 23, 42, 0.6);
        border-color: rgba(45, 212, 191, 0.2);
    }

    :global(.ai-markdown-surface pre code) {
        display: block;
        padding: 0;
        background: transparent;
        color: inherit;
        font-size: 0.78rem;
        line-height: 1.55;
    }

    :global(.ai-markdown-surface blockquote) {
        margin: 0.5rem 0 0.75rem;
        padding: 0.5rem 0.9rem;
        border-left: 3px solid rgba(20, 184, 166, 0.5);
        background: rgba(20, 184, 166, 0.08);
        border-radius: 0.6rem;
        color: inherit;
    }

    :global(.dark .ai-markdown-surface blockquote),
    :global([data-theme='dark'] .ai-markdown-surface blockquote) {
        background: rgba(20, 184, 166, 0.18);
        color: inherit;
        border-left-color: rgba(94, 234, 212, 0.7);
    }

    :global(.ai-markdown-surface a) {
        color: rgb(13 148 136);
        text-decoration: underline;
        text-decoration-thickness: 1px;
        text-underline-offset: 2px;
    }

    :global(.dark .ai-markdown-surface a),
    :global([data-theme='dark'] .ai-markdown-surface a) {
        color: rgb(94 234 212);
    }

    :global(.ai-markdown-surface hr) {
        border: none;
        height: 1px;
        margin: 0.6rem 0 0.8rem;
        background: rgba(148, 163, 184, 0.35);
    }

    :global(.dark .ai-markdown-surface hr),
    :global([data-theme='dark'] .ai-markdown-surface hr) {
        background: rgba(71, 85, 105, 0.5);
    }

    :global(.ai-markdown-surface table) {
        width: 100%;
        border-collapse: collapse;
        margin: 0.5rem 0 0.75rem;
        font-size: 0.82rem;
    }

    :global(.ai-markdown-surface th),
    :global(.ai-markdown-surface td) {
        padding: 0.35rem 0.5rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.25);
        text-align: left;
    }

    :global(.dark .ai-markdown-surface th),
    :global(.dark .ai-markdown-surface td),
    :global([data-theme='dark'] .ai-markdown-surface th),
    :global([data-theme='dark'] .ai-markdown-surface td) {
        border-bottom-color: rgba(71, 85, 105, 0.45);
    }

    :global(.ai-markdown-surface th) {
        font-weight: 700;
        color: rgb(15 118 110);
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-size: 0.7rem;
    }

    :global(.dark .ai-markdown-surface th),
    :global([data-theme='dark'] .ai-markdown-surface th) {
        color: rgb(153 246 228);
    }

    :global(.ai-markdown-surface > :first-child) {
        margin-top: 0;
    }

    :global(.ai-markdown-surface > :last-child) {
        margin-bottom: 0;
    }

    .ai-bubble {
        position: relative;
        padding: 0.75rem 0.9rem;
        border-radius: 1rem;
        border: 1px solid transparent;
        background: rgba(241, 245, 249, 0.9);
        color: rgb(30 41 59);
        box-shadow: 0 8px 16px rgba(15, 23, 42, 0.08);
    }

    :global(.dark) .ai-bubble,
    :global([data-theme='dark']) .ai-bubble {
        background: rgba(15, 23, 42, 0.72);
        color: rgb(241 245 249);
    }

    .ai-bubble.ai-surface {
        padding: 1.1rem 1.2rem;
        border-color: rgba(20, 184, 166, 0.22);
        background: linear-gradient(145deg, rgba(20, 184, 166, 0.08), rgba(14, 116, 144, 0.06));
        box-shadow: 0 12px 28px rgba(15, 118, 110, 0.15);
    }

    :global(.dark) .ai-bubble.ai-surface,
    :global([data-theme='dark']) .ai-bubble.ai-surface {
        background: linear-gradient(145deg, rgba(15, 118, 110, 0.18), rgba(30, 41, 59, 0.78));
        border-color: rgba(45, 212, 191, 0.35);
        /* Match the main .ai-surface dark-mode foreground for consistent contrast. */
        color: rgb(241 245 249);
        box-shadow: 0 14px 30px rgba(2, 6, 23, 0.42);
    }

    .ai-bubble--assistant {
        border-color: rgba(20, 184, 166, 0.35);
    }

    /* Blue Tit theme — ai-bubble */
    :global(.theme-bluetit:not(.dark)) .ai-bubble.ai-surface {
        border-color: rgba(37, 99, 235, 0.22);
        background: linear-gradient(145deg, rgba(37, 99, 235, 0.08), rgba(29, 78, 216, 0.05));
        box-shadow: 0 12px 28px rgba(37, 99, 235, 0.14);
    }
    :global(.theme-bluetit.dark) .ai-bubble.ai-surface {
        background: linear-gradient(145deg, rgba(29, 78, 216, 0.20), rgba(15, 23, 42, 0.80));
        border-color: rgba(96, 165, 250, 0.35);
    }
    :global(.theme-bluetit:not(.dark)) .ai-bubble--assistant {
        border-color: rgba(37, 99, 235, 0.35);
    }
    :global(.theme-bluetit.dark) .ai-bubble--assistant {
        border-color: rgba(96, 165, 250, 0.40);
    }

    .ai-bubble--user {
        border-color: rgba(148, 163, 184, 0.3);
        background: rgba(226, 232, 240, 0.7);
    }

    :global(.dark) .ai-bubble--user,
    :global([data-theme='dark']) .ai-bubble--user {
        background: rgba(30, 41, 59, 0.8);
    }

    .ai-bubble__role {
        font-size: 0.58rem;
        letter-spacing: 0.26em;
        text-transform: uppercase;
        font-weight: 800;
        color: rgb(100 116 139);
        margin-bottom: 0.4rem;
    }

    .ai-bubble__content {
        font-size: 0.88rem;
        line-height: 1.55;
        white-space: pre-wrap;
    }

    .ai-bubble--assistant .ai-bubble__content {
        white-space: normal;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface h1),
    :global(.ai-bubble--assistant .ai-markdown-surface h2),
    :global(.ai-bubble--assistant .ai-markdown-surface h3),
    :global(.ai-bubble--assistant .ai-markdown-surface h4),
    :global(.ai-bubble--assistant .ai-markdown-surface h5),
    :global(.ai-bubble--assistant .ai-markdown-surface h6) {
        margin-top: 0.5rem;
        margin-bottom: 0.2rem;
        letter-spacing: 0.08em;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface p) {
        margin: 0.2rem 0;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface ul),
    :global(.ai-bubble--assistant .ai-markdown-surface ol) {
        margin: 0.25rem 0 0.55rem;
    }

    .ai-bubble--assistant :global(.ai-markdown-surface p),
    .ai-bubble--assistant :global(.ai-markdown-surface li) {
        color: inherit;
    }

    :global(.dark) .ai-bubble__role,
    :global([data-theme='dark']) .ai-bubble__role {
        color: rgb(148 163 184);
    }

    .ai-thread {
        border-radius: 1.25rem;
        padding: 0.9rem;
        border: 1px solid rgba(148, 163, 184, 0.16);
        background: rgba(248, 250, 252, 0.6);
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.06);
    }

    :global(.dark) .ai-thread,
    :global([data-theme='dark']) .ai-thread {
        border-color: rgba(45, 212, 191, 0.18);
        background: rgba(2, 6, 23, 0.22);
        box-shadow: 0 10px 22px rgba(2, 6, 23, 0.28);
    }
</style>



<div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm overflow-y-auto overscroll-contain"
    data-theme={isDarkMode ? 'dark' : 'light'}
    onclick={(e) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    }}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
>
    <div
        bind:this={modalElement}
        data-theme={isDarkMode ? 'dark' : 'light'}
        class="relative bg-white dark:bg-slate-800 rounded-3xl shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col border border-white/20 overflow-hidden"
        role="document"
        tabindex="-1"
    >

        <!-- Reclassification Overlay (covers entire modal content) -->
        {#if reclassifyProgress}
            <ReclassificationOverlay progress={reclassifyProgress} />
        {/if}

        <div class="flex-1 overflow-hidden flex flex-col lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
	            <div class="relative bg-slate-100 dark:bg-slate-700 aspect-video shrink-0 lg:aspect-auto lg:h-full lg:border-r lg:border-slate-200/70 dark:lg:border-slate-700/60 overflow-hidden">
                    {#if showMediaSlotVideoAnalysis}
                        <div class="absolute inset-0 bg-gradient-to-br from-indigo-50 via-white to-slate-100 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800"></div>
                        <div class="relative z-10 h-full flex flex-col justify-between p-4 sm:p-5">
                            <div class="flex items-start justify-between gap-3">
                                <div class="min-w-0">
                                    <p class="text-[10px] font-black uppercase tracking-[0.2em] text-indigo-600 dark:text-indigo-400">
                                        {$_('detection.video_analysis.title')}
                                    </p>
                                    <p class="text-sm sm:text-base font-black text-slate-900 dark:text-white truncate">
                                        {primaryName}
                                    </p>
                                    {#if subName && subName !== primaryName}
                                        <p class="text-[11px] italic text-slate-500 dark:text-slate-400 truncate">{subName}</p>
                                    {/if}
                                </div>
                                <div class="shrink-0 flex items-center gap-2 rounded-full px-2.5 py-1 bg-white/85 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-700/70">
                                    <span class="inline-block h-2 w-2 rounded-full bg-indigo-500 motion-safe:animate-pulse"></span>
                                    <span class="text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-slate-300">
                                        {$_('detection.video_analysis.in_progress')}
                                    </span>
                                </div>
                                {#if videoInferenceBadge.kind}
                                    <div class="shrink-0 flex items-center gap-1.5 rounded-full px-2.5 py-1 bg-white/85 dark:bg-slate-900/80 border border-slate-200/80 dark:border-slate-700/70">
                                        <span class="{videoInferenceBadge.kind === 'gpu' ? 'text-emerald-600 dark:text-emerald-300' : 'text-sky-600 dark:text-sky-300'}" aria-hidden="true">
                                            {#if videoInferenceBadge.kind === 'gpu'}
                                                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                                                    <path d="M10 2.5 16.5 9 10 15.5 3.5 9 10 2.5Zm0 2.12L5.62 9 10 13.38 14.38 9 10 4.62Z" />
                                                </svg>
                                            {:else}
                                                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6">
                                                    <rect x="4.5" y="5.5" width="11" height="9" rx="1.5" />
                                                    <path d="M8 2.75v2M12 2.75v2M8 15.25v2M12 15.25v2M2.75 8h2M2.75 12h2M15.25 8h2M15.25 12h2" stroke-linecap="round" />
                                                </svg>
                                            {/if}
                                        </span>
                                        <span class="text-[10px] font-black uppercase tracking-widest text-slate-700 dark:text-slate-200">
                                            {videoInferenceBadge.label}
                                        </span>
                                    </div>
                                {/if}
                            </div>

                            <div class="my-3 sm:my-4">
                                <VideoAnalysisFilmReel progress={modalVideoAnalysisProgress} variant="detail" />
                            </div>

                            <div class="flex items-center justify-between gap-3 text-[10px] font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                                <span>{formatDateTime(detection.detection_time)}</span>
                                <span>{detection.camera_name}</span>
                            </div>
                        </div>
                    {:else}
                        <img src={snapshotImageUrl} alt={detection.display_name} class="w-full h-full object-cover" />
    	                <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent"></div>
    	                {#if authStore.canModify && !readOnly}
    	                    <button
    	                        type="button"
    	                        onclick={handleFavoriteToggle}
    	                        disabled={favoritePending}
    	                        class="absolute top-4 left-4 z-30 inline-flex h-10 w-10 items-center justify-center rounded-full border shadow-lg backdrop-blur-sm transition-all disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 {detection.is_favorite ? 'bg-amber-500/90 border-amber-300 text-white hover:bg-amber-500' : 'bg-black/45 border-white/35 text-white hover:bg-black/60'}"
    	                        title={detection.is_favorite ? $_('detection.favorite_remove', { default: 'Remove favorite' }) : $_('detection.favorite_add', { default: 'Add favorite' })}
    	                        aria-label={detection.is_favorite ? $_('detection.favorite_remove', { default: 'Remove favorite' }) : $_('detection.favorite_add', { default: 'Add favorite' })}
    	                    >
    	                        {#if favoritePending}
    	                            <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"></span>
    	                        {:else}
    	                            <svg class="w-4 h-4" viewBox="0 0 24 24" fill={detection.is_favorite ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.8">
    	                                <path stroke-linecap="round" stroke-linejoin="round" d="M11.05 2.927c.3-.921 1.603-.921 1.902 0l2.02 6.217a1 1 0 00.95.69h6.54c.969 0 1.371 1.24.588 1.81l-5.29 3.844a1 1 0 00-.364 1.118l2.02 6.217c.3.921-.755 1.688-1.539 1.118l-5.29-3.844a1 1 0 00-1.175 0l-5.29 3.844c-.783.57-1.838-.197-1.539-1.118l2.02-6.217a1 1 0 00-.364-1.118L.98 11.644c-.783-.57-.38-1.81.588-1.81h6.54a1 1 0 00.95-.69l2.02-6.217z" />
    	                            </svg>
    	                        {/if}
    	                    </button>
    	                {/if}
                        {#if showManualHqBirdCropAction}
                            <button
                                type="button"
                                onclick={handleManualHqBirdCrop}
                                disabled={manualHqBirdCropPending || snapshotStatusLoading}
                                class="absolute top-4 right-16 z-30 inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/35 bg-black/45 text-white shadow-lg backdrop-blur-sm transition-all hover:bg-black/60 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-300/70"
                                title={$_('detection.manual_hq_bird_crop', { default: 'Generate HQ bird crop' })}
                                aria-label={$_('detection.manual_hq_bird_crop', { default: 'Generate HQ bird crop' })}
                            >
                                {#if manualHqBirdCropPending}
                                    <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"></span>
                                {:else}
                                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                        <path d="M5 8a2 2 0 0 1 2-2h2l1.2-1.6A1 1 0 0 1 11 4h2a1 1 0 0 1 .8.4L15 6h2a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V8Z" stroke-linecap="round" stroke-linejoin="round"></path>
                                        <circle cx="12" cy="11.5" r="3.25"></circle>
                                        <path d="M8 20l2-2"></path>
                                        <path d="M16 20l-2-2"></path>
                                    </svg>
                                {/if}
                            </button>
                        {/if}
    	                <div class="absolute bottom-0 left-0 right-0 p-5">
    	                    <h3 class="text-xl font-black text-white drop-shadow-lg leading-tight truncate">{primaryName}</h3>
    	                    {#if subName && subName !== primaryName}
    	                        <p class="text-white/70 text-sm italic drop-shadow -mt-0.5 mb-0.5 truncate">{subName}</p>
    	                    {/if}
                        <p class="text-white/50 text-[10px] uppercase font-bold tracking-widest mt-2">
                            {formatDateTime(detection.detection_time)}
                        </p>
                        <div class="bottom-4 left-4 z-30 flex items-end gap-2 mt-3">
                        {#if canPlayVideo}
                            <div class="flex items-center gap-2">
                                {#if fullVisitFetched}
                                    <div
                                        class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-teal-500/95 text-white shadow-xl shadow-teal-900/30 border border-teal-300/30 backdrop-blur-sm"
                                        title={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                                        aria-label={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                                    >
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                            <path d="M7 3H5a2 2 0 00-2 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                                            <path d="M13 3h2a2 2 0 012 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                                            <path d="M17 13v2a2 2 0 01-2 2h-2" stroke-linecap="round" stroke-linejoin="round"></path>
                                            <path d="M7 17H5a2 2 0 01-2-2v-2" stroke-linecap="round" stroke-linejoin="round"></path>
                                        </svg>
                                    </div>
                                {/if}
                                <button
                                    type="button"
                                    onclick={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        onPlayVideo?.(detection.frigate_event, 'user');
                                    }}
                                    onpointerdown={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                    }}
                                    ontouchstart={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                    }}
                                    aria-label={$_('detection.play_video', { values: { species: primaryName } })}
                                    class="pointer-events-auto inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/25 bg-black/55 text-white shadow-xl backdrop-blur-sm transition-all duration-150 hover:bg-teal-500/90 focus:outline-none focus:ring-2 focus:ring-teal-400/70"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                        <path d="M8 5v14l11-7z"/>
                                    </svg>
                                </button>
                            </div>
                        {/if}
                        {#if showFetchFullVisitAction}
                            <div class="bottom-4 left-4 z-30 flex items-end gap-2 mt-3">
                                <button
                                    type="button"
                                    onclick={handleFetchFullVisitClick}
                                    onpointerdown={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                    }}
                                    ontouchstart={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                    }}
                                    disabled={fullVisitFetchState === 'fetching'}
                                    aria-label={fullVisitFetchLabel}
                                    class="pointer-events-auto inline-flex items-center gap-2 rounded-full border border-white/25 bg-black/55 px-4 py-2 text-[11px] font-black uppercase tracking-widest text-white shadow-xl backdrop-blur-sm transition-all duration-150 hover:bg-teal-500/90 disabled:cursor-wait disabled:opacity-75 focus:outline-none focus:ring-2 focus:ring-teal-400/70"
                                >
                                    {#if fullVisitFetchState === 'fetching'}
                                        <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin"></span>
                                    {:else}
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                            <path d="M10 3v8"></path>
                                            <path d="M7 8l3 3 3-3"></path>
                                            <path d="M4 14h12"></path>
                                        </svg>
                                    {/if}
                                    <span>{fullVisitFetchLabel}</span>
                                </button>
                            </div>
                        {/if}
                        </div>
                    </div>
                    {/if}

                    {#if frigateIssueBadgeVisible}
                        <div class="absolute top-4 right-4 z-30">
                            <div
                                class="inline-flex h-9 w-9 items-center justify-center rounded-full border border-rose-200/85 bg-rose-100/92 text-rose-700 shadow-lg shadow-rose-500/10 backdrop-blur-sm dark:border-rose-300/20 dark:bg-rose-400/12 dark:text-rose-200"
                                title={videoFailureInsight.summary}
                                aria-label={videoFailureInsight.summary}
                            >
                                <img src={FRIGATE_LOGO_URL} alt="" aria-hidden="true" class="h-4 w-4 rounded-[3px] bg-white/95 p-0.5 object-contain" />
                            </div>
                        </div>
                    {/if}

        <button
            onclick={onClose}
            class="absolute top-4 right-4 z-40 w-8 h-8 rounded-full bg-black/40 text-white flex items-center justify-center hover:bg-black/60 transition-colors"
            aria-label={$_('common.close')}
        >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
        </button>

        {#if debugUiEnabled && aiDiagnosticsEnabled}
            <button
                type="button"
                onclick={copyAiFullBundle}
                class="absolute top-4 right-14 z-40 w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-100 flex items-center justify-center hover:bg-emerald-500/35 transition-colors"
                title={$_('detection.ai.copy_diagnostics_bundle', { default: 'Copy AI diagnostics bundle' })}
                aria-label={$_('detection.ai.copy_diagnostics_bundle', { default: 'Copy AI diagnostics bundle' })}
            >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H6a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-2M8 7a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2" />
                </svg>
            </button>
        {/if}
            </div>

            <div class="flex-1 overflow-y-auto p-6 space-y-6 {showTagDropdown ? 'blur-sm pointer-events-none select-none' : ''}">
            <!-- Detection ID -->
            <div class="flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50">
                <span class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('detection.id')}</span>
                <span class="text-[10px] font-mono text-slate-700 dark:text-slate-300 break-all text-right">{detection.frigate_event}</span>
            </div>
            <!-- Confidence Bar -->
            {#if currentClassificationSource !== 'manual'}
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{$_('detection.confidence')}</span>
                        <span class="text-sm font-black text-slate-900 dark:text-white">
                            {((detection.score || 0) * 100).toFixed(1)}%
                        </span>
                    </div>
                    <div class="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                        <div
                            class="h-full rounded-full transition-all duration-700 {(detection.score || 0) >= 0.8 ? 'bg-emerald-500' : 'bg-teal-500'}"
                            style="width: {(detection.score || 0) * 100}%"
                        ></div>
                    </div>
                </div>
            {/if}

            <!-- Video Classification Results -->
            {#if detection.video_classification_status === 'completed' || (detection.video_classification_label && detection.video_classification_label !== detection.display_name)}
                <div class="p-4 rounded-2xl bg-indigo-50/80 dark:bg-indigo-500/10 border border-indigo-200/80 dark:border-indigo-500/20 animate-in fade-in slide-in-from-top-2">
                    <div class="flex items-center justify-between mb-2">
                        <p class="text-[10px] font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-[0.2em]">
                            {$_('detection.video_analysis.title')}
                        </p>
                        {#if detection.video_classification_score}
                            <span class="px-2 py-0.5 bg-indigo-500 text-white text-[9px] font-black rounded uppercase">
                                {$_('detection.video_analysis.match', { values: { score: (detection.video_classification_score * 100).toFixed(0) } })}
                            </span>
                        {/if}
                    </div>
                    <p class="text-sm font-bold text-slate-800 dark:text-slate-200">
                        {detection.video_classification_label === detection.scientific_name && detection.common_name
                            ? detection.common_name
                            : detection.video_classification_label}
                    </p>
                    {#if detection.video_result_blocked}
                        <p class="text-[10px] font-bold text-amber-600 dark:text-amber-400 mt-0.5">
                            {$_('detection.video_analysis.blocked_label', { default: 'Matched a blocked species — not applied' })}
                        </p>
                    {/if}
                    <div class="flex flex-wrap items-center gap-2 mt-1">
                        <p class="text-[10px] text-slate-500 italic leading-tight">
                            {$_('detection.video_analysis.verified_desc')}
                        </p>
                        {#if completedVideoInferenceBadge.kind}
                            <div class="flex items-center gap-1.5 px-1.5 py-0.5 rounded border border-indigo-200/50 dark:border-indigo-500/30 bg-white/60 dark:bg-slate-900/40">
                                {#if completedVideoInferenceBadge.kind === 'gpu'}
                                    <svg class="h-3 w-3 text-indigo-500" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                        <path d="M10 2.5 16.5 9 10 15.5 3.5 9 10 2.5Zm0 2.12L5.62 9 10 13.38 14.38 9 10 4.62Z" />
                                    </svg>
                                    <span class="text-[9px] font-black text-indigo-700 dark:text-indigo-300 uppercase tracking-wider" title={detection.video_classification_provider ?? undefined}>
                                        {completedVideoInferenceBadge.label}
                                    </span>
                                {:else}
                                    <svg class="h-3 w-3 text-slate-400" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                                        <rect x="4.5" y="5.5" width="11" height="9" rx="1.5" />
                                        <path d="M8 2.75v2M12 2.75v2M8 15.25v2M12 15.25v2M2.75 8h2M2.75 12h2M15.25 8h2M15.25 12h2" stroke-linecap="round" />
                                    </svg>
                                    <span class="text-[9px] font-black text-slate-600 dark:text-slate-300 uppercase tracking-wider" title={detection.video_classification_provider ?? detection.video_classification_backend ?? undefined}>
                                        {completedVideoInferenceBadge.label}
                                    </span>
                                {/if}
                            </div>
                        {/if}
                        {#if detection.video_classification_model_name}
                            <div class="flex items-center gap-1.5 px-1.5 py-0.5 rounded border border-slate-200/70 dark:border-slate-600/60 bg-white/60 dark:bg-slate-900/40">
                                <svg class="h-3 w-3 text-slate-500 dark:text-slate-300" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                                    <path d="M4.5 5.75 10 2.75l5.5 3v8.5L10 17.25l-5.5-3v-8.5Z" />
                                    <path d="M10 2.75v14.5M4.5 5.75 10 9l5.5-3.25" stroke-linecap="round" stroke-linejoin="round" />
                                </svg>
                                <span
                                    class="text-[9px] font-black text-slate-600 dark:text-slate-200 tracking-wide"
                                    title={detection.video_classification_model_id ?? detection.video_classification_model_name}
                                >
                                    {detection.video_classification_model_name}
                                </span>
                            </div>
                        {/if}
                    </div>
                </div>
            {:else if (detection.video_classification_status === 'processing' || detection.video_classification_status === 'pending') && !showMediaSlotVideoAnalysis}
                 <div class="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/70 dark:border-slate-700/50 flex items-center gap-3 animate-pulse">
                    <div class="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
                    <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{$_('detection.video_analysis.in_progress')}</span>
                 </div>
            {:else if detection.video_classification_status === 'failed'}
                <div class="p-4 rounded-2xl bg-rose-50/80 dark:bg-rose-500/10 border border-rose-200/70 dark:border-rose-500/20 animate-in fade-in slide-in-from-top-2">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <p class="text-[10px] font-black text-rose-600 dark:text-rose-400 uppercase tracking-[0.2em] mb-1">
                                {$_('detection.video_analysis.failed_title')}
                            </p>
                            <p class="text-xs text-slate-700 dark:text-slate-300">
                                {videoFailureInsight.summary}
                            </p>
                        </div>
                        {#if videoFailureInsight.isFrigateRelated}
                            <div
                                class="shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-full border border-rose-200/85 bg-rose-100/92 text-rose-700 dark:border-rose-300/20 dark:bg-rose-400/12 dark:text-rose-200"
                                title={$_('detection.frigate_badge', { default: 'Frigate' })}
                                aria-label={$_('detection.frigate_badge', { default: 'Frigate' })}
                            >
                                <img src={FRIGATE_LOGO_URL} alt="" aria-hidden="true" class="h-3.5 w-3.5 rounded-[3px] bg-white/95 p-0.5 object-contain" />
                            </div>
                        {/if}
                    </div>
                    <details class="mt-3 rounded-xl border border-rose-200/80 dark:border-rose-400/25 bg-white/75 dark:bg-slate-900/40 px-3 py-2" bind:open={videoErrorDetailsOpen}>
                        <summary class="cursor-pointer select-none text-[11px] font-bold text-rose-700 dark:text-rose-300">
                            {videoErrorDetailsOpen
                                ? $_('detection.video_analysis.error_details.hide', { default: 'Hide error details' })
                                : $_('detection.video_analysis.error_details.show', { default: 'Show error details' })}
                        </summary>
                        <div class="mt-2 space-y-2 text-[11px] text-slate-700 dark:text-slate-300">
                            <p class="font-mono text-[10px] text-slate-600 dark:text-slate-400">
                                {$_('detection.video_analysis.error_details.error_code', { default: 'Error code: {code}', values: { code: videoFailureInsight.errorCode } })}
                            </p>
                            <div>
                                <p class="font-bold text-slate-800 dark:text-slate-200">
                                    {$_('detection.video_analysis.error_details.why', { default: 'Why this can happen' })}
                                </p>
                                <ul class="mt-1 list-disc pl-5 space-y-1">
                                    {#each videoFailureInsight.causes as cause}
                                        <li>{cause}</li>
                                    {/each}
                                </ul>
                            </div>
                            <div>
                                <p class="font-bold text-slate-800 dark:text-slate-200">
                                    {$_('detection.video_analysis.error_details.checks', { default: 'What to check' })}
                                </p>
                                <ul class="mt-1 list-disc pl-5 space-y-1">
                                    {#each videoFailureInsight.checks as check}
                                        <li>{check}</li>
                                    {/each}
                                </ul>
                            </div>
                        </div>
                    </details>
                </div>
            {/if}

            <!-- Metadata -->
            <div class="grid grid-cols-2 gap-4">
                <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50">
                    <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span class="text-sm font-bold text-slate-700 dark:text-slate-300 truncate">{detection.camera_name}</span>
                </div>
                {#if detection.temperature !== undefined && detection.temperature !== null}
                    <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50">
                        <svg class="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                        <span class="text-sm font-bold text-slate-700 dark:text-slate-300">
                            {formatTemperature(detection.temperature, temperatureUnit)}
                        </span>
                    </div>
                {/if}
                {#if detection.frigate_score != null}
                    <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50">
                        <svg class="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        <span class="text-sm font-bold text-slate-700 dark:text-slate-300">
                            {$_('detection.frigate_score', { values: { score: Math.round(detection.frigate_score * 100) } })}
                        </span>
                    </div>
                {/if}
            </div>

            {#if hasAudioContext}
                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 dark:border-teal-500/20 space-y-3">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-xl bg-teal-500/20 flex items-center justify-center">
                            <svg class="w-5 h-5 text-teal-600 dark:text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
                            </svg>
                        </div>
                        <div class="min-w-0">
                            <p class="text-[10px] font-black uppercase tracking-widest text-teal-600/70 dark:text-teal-400/70">
                                {detection.audio_confirmed
                                    ? $_('detection.audio_match')
                                    : (audioNearbySummary
                                        ? $_('detection.audio_possible_nearby', { default: 'Possible Nearby Audio Match' })
                                        : $_('detection.audio_no_direct_match', { default: 'No Direct Audio Confirmation' }))}
                            </p>
                            <p class="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">
                                {detection.audio_confirmed
                                    ? (detection.audio_species || $_('detection.birdnet_confirmed'))
                                    : (audioNearbySummary
                                        ? $_('detection.audio_nearby', { values: { species: audioNearbySummary }, default: 'Nearby audio: {species}' })
                                        : $_('detection.audio_no_match_desc', { default: 'No nearby BirdNET species in the matching window' }))}
                                {#if detection.audio_score && detection.audio_confirmed}
                                    <span class="ml-1 opacity-60">({(detection.audio_score * 100).toFixed(0)}%)</span>
                                {/if}
                            </p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onclick={toggleAudioContext}
                        class="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-slate-100/70 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 text-[11px] font-bold uppercase tracking-widest text-slate-600 dark:text-slate-300"
                        aria-label={$_('detection.audio_context')}
                    >
                        <span class="flex items-center gap-2">
                            <svg class="w-3 h-3 transition-transform {audioContextOpen ? '-rotate-90' : 'rotate-0'}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                            </svg>
                            {$_('detection.audio_context')}
                        </span>
                        <span class="text-[9px] font-black text-slate-400">{audioContextOpen ? $_('common.hide') : $_('common.show')}</span>
                    </button>
                    {#if audioContextOpen}
                        <div class="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 p-3 space-y-2">
                            {#if audioContextLoading}
                                <p class="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{$_('detection.audio_context_loading')}</p>
                            {:else if audioContextError}
                                <p class="text-[10px] font-semibold uppercase tracking-widest text-rose-500">{audioContextError}</p>
                            {:else if audioContext.length === 0}
                                <p class="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{$_('detection.audio_context_empty')}</p>
                            {:else}
                                {#each audioContext as audio}
                                    <div class="flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
                                        <div class="min-w-0">
                                            <p class="font-semibold truncate">{audio.species}</p>
                                            <p class="text-[10px] uppercase tracking-widest text-slate-400">
                                                {(audio.confidence * 100).toFixed(0)}%
                                                {#if audio.sensor_id}
                                                    <span class="ml-1 opacity-70">{audio.sensor_id}</span>
                                                {/if}
                                            </p>
                                        </div>
                                        <div class="text-[10px] font-black text-slate-500 dark:text-slate-400">
                                            {formatAudioOffset(audio.offset_seconds)}
                                        </div>
                                    </div>
                                {/each}
                            {/if}
                        </div>
                    {/if}
                </div>
            {/if}

            {#if hasWeather}
                <div class="p-4 rounded-2xl bg-sky-50/80 dark:bg-slate-900/40 border border-sky-100/80 dark:border-slate-700/60 space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-3 min-w-0">
                            <div class="w-10 h-10 rounded-xl bg-sky-500/20 flex items-center justify-center flex-shrink-0">
                                <svg class="w-5 h-5 text-sky-600 dark:text-sky-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                </svg>
                            </div>
                            <div class="min-w-0">
                                <p class="text-[10px] font-black uppercase tracking-widest text-sky-600/70 dark:text-sky-300/70 mb-0.5">
                                    {$_('detection.weather_title')}
                                </p>
                                <p class="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">
                                    {detection.weather_condition || $_('detection.weather_unknown')}
                                </p>
                            </div>
                        </div>
                        {#if detection.temperature !== undefined && detection.temperature !== null}
                            <div class="text-sm font-black text-slate-800 dark:text-slate-100">
                                {formatTemperature(detection.temperature, temperatureUnit)}
                            </div>
                        {/if}
                    </div>
                    <button
                        type="button"
                        onclick={(event) => { event.stopPropagation(); weatherDetailsOpen = !weatherDetailsOpen; }}
                        class="w-full flex items-center justify-between px-3 py-2 rounded-xl bg-slate-100/70 dark:bg-slate-800/60 border border-slate-200/60 dark:border-slate-700/60 text-[11px] font-bold uppercase tracking-widest text-slate-600 dark:text-slate-300"
                        aria-label={$_('detection.weather_details')}
                    >
                        <span class="flex items-center gap-2">
                            <svg class="w-3 h-3 transition-transform {weatherDetailsOpen ? '-rotate-90' : 'rotate-0'}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                            </svg>
                            {$_('detection.weather_details')}
                        </span>
                        <span class="text-[9px] font-black text-slate-400">{weatherDetailsOpen ? $_('common.hide') : $_('common.show')}</span>
                    </button>
                    {#if weatherDetailsOpen}
                        <div class="grid grid-cols-2 gap-2">
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h11a3 3 0 100-6M2 12h13a3 3 0 110 6H9" />
                                    </svg>
                                    {$_('detection.weather_wind')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {#if detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null}
                                        {formatWindSpeed(detection.weather_wind_speed, weatherUnitSystem, {
                                            metric: $_('common.unit_kmh', { default: 'km/h' }),
                                            imperial: $_('common.unit_mph', { default: 'mph' })
                                        })} {formatWindDirection(detection.weather_wind_direction)}
                                    {:else}
                                        —
                                    {/if}
                                </p>
                            </div>
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                    </svg>
                                    {$_('detection.weather_cloud')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {#if detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null}
                                        {Math.round(detection.weather_cloud_cover)}%
                                    {:else}
                                        —
                                    {/if}
                                </p>
                            </div>
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                    </svg>
                                    {$_('detection.weather_title')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {detection.weather_condition || $_('detection.weather_unknown')}
                                </p>
                            </div>
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v18m9-9H3m15.364-6.364l-12.728 12.728m0-12.728l12.728 12.728" />
                                    </svg>
                                    {$_('detection.weather_rain')} / {$_('detection.weather_snow')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {#if detection.weather_rain !== undefined && detection.weather_rain !== null || detection.weather_snowfall !== undefined && detection.weather_snowfall !== null}
                                        {formatPrecip(detection.weather_rain)} / {formatPrecip(detection.weather_snowfall)}
                                    {:else}
                                        —
                                    {/if}
                                </p>
                            </div>
                        </div>
                    {/if}
                </div>
            {/if}

            {#if !isUnknownSpecies && (speciesInfoLoading || speciesInfo || speciesInfoError || showEbirdNearby || showEbirdNotable)}
                <div class="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                    {#if enrichmentSummaryProvider !== 'disabled'}
                        <div class="group relative overflow-hidden rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white/50 dark:bg-slate-900/30 p-5 hover:bg-white/80 dark:hover:bg-slate-900/50 transition-all duration-300">
                            <div class="absolute inset-0 bg-gradient-to-br from-teal-500/5 via-transparent to-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                            
                            <div class="relative flex items-center justify-between gap-3 mb-3">
                                <div class="flex items-center gap-2">
                                    <div class="p-1.5 rounded-lg bg-teal-500/10 text-teal-600 dark:text-teal-400">
                                        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                    </div>
                                    <p class="text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">{$_('actions.species_info')}</p>
                                </div>
                                {#if speciesInfo}
                                    {@const summaryLabel = speciesInfo.summary_source || speciesInfo.source || 'Source'}
                                    {#if speciesInfo.summary_source_url}
                                        <a
                                            href={speciesInfo.summary_source_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[9px] font-black uppercase tracking-wider text-slate-500 hover:text-teal-600 dark:hover:text-teal-400 hover:border-teal-500/30 transition-colors shadow-sm"
                                        >
                                            {summaryLabel}
                                            <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                            </svg>
                                        </a>
                                    {:else}
                                        <span class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-[9px] font-black uppercase tracking-wider text-slate-500">
                                            {summaryLabel}
                                        </span>
                                    {/if}
                                {/if}
                            </div>

                            <div class="relative">
                                {#if speciesInfoLoading}
                                    <div class="flex flex-col gap-2">
                                        <div class="h-3 w-3/4 bg-slate-200 dark:bg-slate-700 rounded animate-pulse"></div>
                                        <div class="h-3 w-full bg-slate-200 dark:bg-slate-700 rounded animate-pulse"></div>
                                        <div class="h-3 w-5/6 bg-slate-200 dark:bg-slate-700 rounded animate-pulse"></div>
                                    </div>
                                {:else if speciesInfoError}
                                    <div class="flex items-center gap-2 p-3 rounded-xl bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400">
                                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                        </svg>
                                        <p class="text-xs font-semibold">{speciesInfoError}</p>
                                    </div>
                                {:else if speciesInfo}
                                    {@const summaryText = speciesInfo.extract || speciesInfo.description}
                                    {#if summaryText}
                                        <p class="text-sm text-slate-600 dark:text-slate-300 leading-relaxed line-clamp-4">
                                            {summaryText}
                                        </p>
                                    {:else}
                                        <p class="text-xs text-slate-500 italic">{$_('species_detail.no_info')}</p>
                                    {/if}
                                    {#if speciesInfo.scientific_name || speciesInfo.conservation_status}
                                        <div class="flex flex-wrap gap-2 mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/50">
                                            {#if speciesInfo.scientific_name}
                                                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 dark:bg-slate-800 text-[10px] font-bold text-slate-600 dark:text-slate-400 italic">
                                                    <svg class="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 20l4-16m2 16l4-16M6 9h14M4 15h14" />
                                                    </svg>
                                                    {speciesInfo.scientific_name}
                                                </span>
                                            {/if}
                                            {#if speciesInfo.conservation_status}
                                                <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 dark:bg-emerald-900/20 text-[10px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-wide">
                                                    <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                    </svg>
                                                    {speciesInfo.conservation_status}
                                                </span>
                                            {/if}
                                        </div>
                                    {/if}
                                {/if}
                            </div>
                        </div>
                    {/if}

                    {#if showEbirdNearby}
                        <div class="group relative overflow-hidden rounded-2xl border border-sky-200/60 dark:border-sky-800/40 bg-sky-50/30 dark:bg-sky-900/10 p-5 hover:bg-sky-50/50 dark:hover:bg-sky-900/20 transition-all duration-300">
                            <div class="flex items-center justify-between gap-3 mb-4">
                                <div class="flex items-center gap-2">
                                    <div class="p-1.5 rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">
                                        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                                        </svg>
                                    </div>
                                    <div class="flex flex-col">
                                        <p class="text-[10px] font-black uppercase tracking-[0.2em] text-sky-700 dark:text-sky-400">{$_('species_detail.recent_sightings')}</p>
                                        <div class="flex items-center gap-1.5 mt-0.5">
                                            <span class="text-[9px] font-bold text-sky-600/60 dark:text-sky-500/60 uppercase tracking-wider">eBird</span>
                                            <span class="w-0.5 h-0.5 rounded-full bg-sky-300"></span>
                                            <span class="text-[9px] font-medium text-slate-400">{ebirdRadius}km · {ebirdDaysBack}d</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {#if !ebirdEnabled}
                                <div class="text-center py-4 rounded-xl bg-white/50 dark:bg-slate-900/30 border border-dashed border-sky-200 dark:border-sky-800/30">
                                    <p class="text-xs font-medium text-slate-500">{$_('detection.ebird_enable_sightings')}</p>
                                    <a href="/settings#integrations" class="inline-block mt-2 text-[10px] font-bold text-sky-600 hover:text-sky-700 hover:underline">{$_('detection.ebird_configure_settings')}</a>
                                </div>
                            {:else if ebirdNearbyLoading}
                                <div class="space-y-3">
                                    {#each [1, 2, 3] as _}
                                        <div class="flex justify-between gap-4">
                                            <div class="h-3 w-2/3 bg-sky-100 dark:bg-sky-900/30 rounded animate-pulse"></div>
                                            <div class="h-3 w-1/4 bg-sky-100 dark:bg-sky-900/30 rounded animate-pulse"></div>
                                        </div>
                                    {/each}
                                </div>
                            {:else if ebirdNearbyError}
                                <div class="flex items-center gap-2 p-3 rounded-xl bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-800/30">
                                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                    <p class="text-xs font-semibold">{ebirdNearbyError}</p>
                                </div>
                            {:else if (ebirdNearby?.results?.length || 0) === 0}
                                <div class="text-center py-6">
                                    <p class="text-sm text-slate-400 font-medium">{$_('detection.ebird_none_nearby')}</p>
                                    <p class="text-[10px] text-slate-400/60 mt-1">{$_('detection.ebird_try_radius')}</p>
                                </div>
                            {:else if ebirdNearby}
                                {#if ebirdNearby.results.some(r => r.lat && r.lng)}
                                    <div class="h-48 mb-4 rounded-xl overflow-hidden border border-sky-100 dark:border-sky-900/30 shadow-sm relative z-0">
                                        <Map
                                            markers={ebirdNearby.results
                                                .filter(r => r.lat && r.lng)
                                                .map(r => ({
                                                    lat: r.lat!,
                                                    lng: r.lng!,
                                                    title: r.location_name || 'Unknown Location',
                                                    popupText: (() => {
                                                        const t = get(_);
                                                        const countLabel = t('species_detail.count_label', { default: 'Count' });
                                                        return `<div class="font-sans"><p class="font-bold text-sm mb-1">${r.location_name}</p><p class="text-xs opacity-75">${formatEbirdDate(r.observed_at)}</p><p class="text-xs font-bold mt-1">${countLabel}: ${r.how_many ?? '?'}</p></div>`;
                                                    })()
                                                }))}
                                            userLocation={authStore.canModify && settingsStore.settings?.location_latitude && settingsStore.settings?.location_longitude ? [settingsStore.settings.location_latitude, settingsStore.settings.location_longitude] : null}
                                            zoom={10}
                                            obfuscate={!authStore.canModify}
                                        />
                                    </div>
                                {/if}
                                <div class="space-y-2">
                                    {#each ebirdNearby.results.slice(0, 5) as obs}
                                        <div class="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-sky-100 dark:border-sky-900/30 hover:border-sky-300 dark:hover:border-sky-700/50 transition-colors">
                                            <div class="min-w-0">
                                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">{obs.location_name || $_('common.unknown_location')}</p>
                                                <div class="flex items-center gap-2 mt-0.5">
                                                    <p class="text-[10px] font-medium text-slate-400">{formatEbirdDate(obs.observed_at)}</p>
                                                    {#if obs.obs_valid}
                                                        <span
                                                            class="w-1 h-1 rounded-full bg-emerald-400"
                                                            title={$_('detection.ebird.valid_observation', { default: 'Valid observation' })}
                                                        ></span>
                                                    {/if}
                                                </div>
                                            </div>
                                            {#if obs.how_many}
                                                <span class="flex-shrink-0 px-2 py-1 rounded-lg bg-sky-100 dark:bg-sky-900/40 text-[10px] font-black text-sky-700 dark:text-sky-300">
                                                    x{obs.how_many}
                                                </span>
                                            {/if}
                                        </div>
                                    {/each}
                                </div>
                            {/if}
                        </div>
                    {/if}

                    {#if showEbirdNotable}
                        <div class="group relative overflow-hidden rounded-2xl border border-amber-200/60 dark:border-amber-800/40 bg-amber-50/30 dark:bg-amber-900/10 p-5 hover:bg-amber-50/50 dark:hover:bg-amber-900/20 transition-all duration-300">
                            <div class="flex items-center justify-between gap-3 mb-4">
                                <div class="flex items-center gap-2">
                                    <div class="p-1.5 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                        <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
                                        </svg>
                                    </div>
                                    <div class="flex flex-col">
                                        <p class="text-[10px] font-black uppercase tracking-[0.2em] text-amber-700 dark:text-amber-400">{$_('detection.ebird_notable_title')}</p>
                                        <div class="flex items-center gap-1.5 mt-0.5">
                                            <span class="text-[9px] font-bold text-amber-600/60 dark:text-amber-500/60 uppercase tracking-wider">{$_('detection.ebird_notable_badge')}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {#if !ebirdEnabled}
                                <div class="text-center py-4 rounded-xl bg-white/50 dark:bg-slate-900/30 border border-dashed border-amber-200 dark:border-amber-800/30">
                                    <p class="text-xs font-medium text-slate-500">{$_('detection.ebird_enable_notable')}</p>
                                </div>
                            {:else if ebirdNotableLoading}
                                <div class="space-y-3">
                                    {#each [1, 2] as _}
                                        <div class="h-12 w-full bg-amber-100 dark:bg-amber-900/30 rounded-xl animate-pulse"></div>
                                    {/each}
                                </div>
                            {:else if ebirdNotableError}
                                <p class="text-xs text-rose-600">{ebirdNotableError}</p>
                            {:else if (ebirdNotable?.results?.length || 0) === 0}
                                <div class="text-center py-4">
                                    <p class="text-sm text-slate-400 font-medium">{$_('detection.ebird_none_notable')}</p>
                                </div>
                            {:else if ebirdNotable}
                                <div class="space-y-2">
                                    {#each ebirdNotable.results.slice(0, 5) as obs}
                                        <div class="flex items-center gap-3 p-2.5 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-amber-100 dark:border-amber-900/30 hover:border-amber-300 dark:hover:border-amber-700/50 transition-colors">
                                            {#if obs.thumbnail_url}
                                                <img src={obs.thumbnail_url} alt={obs.common_name || 'Bird'} class="w-10 h-10 rounded-lg object-cover bg-slate-200 dark:bg-slate-700 shrink-0" loading="lazy" />
                                            {/if}
                                            <div class="min-w-0 flex-1">
                                                <p class="text-xs font-bold text-slate-800 dark:text-slate-200 truncate">{obs.common_name || obs.scientific_name || $_('common.unknown_species')}</p>
                                                <p class="text-[10px] font-medium text-slate-400 truncate">{obs.location_name || $_('common.unknown_location')}</p>
                                            </div>
                                            <div class="text-right shrink-0">
                                                <p class="text-[10px] font-bold text-amber-600 dark:text-amber-400">{formatEbirdDate(obs.observed_at)}</p>
                                            </div>
                                        </div>
                                    {/each}
                                </div>
                            {/if}
                        </div>
                    {/if}
                </div>
            {/if}

            {#if canShowInat}
                <div class="p-4 rounded-2xl bg-emerald-50/70 dark:bg-slate-900/40 border border-emerald-100/80 dark:border-slate-700/60 space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-3">
                            <div class="w-9 h-9 rounded-xl bg-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-300">
                                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v4m0 0a4 4 0 110 8m0-8a4 4 0 10-4 4m4-4v4m0 0a4 4 0 010 8m0-8a4 4 0 10-4 4" />
                                </svg>
                            </div>
                            <div>
                                <p class="text-[10px] font-black uppercase tracking-widest text-emerald-600/80 dark:text-emerald-300/80">{$_('detection.inat.title')}</p>
                                {#if inatConnectedUser}
                                    <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{$_('detection.inat.connected', { values: { user: inatConnectedUser } })}</p>
                                {:else if inatPreview}
                                    <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{$_('detection.inat.preview_note')}</p>
                                {/if}
                            </div>
                        </div>
                        <button
                            type="button"
                            onclick={openInatPanel}
                            class="px-3 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white transition-all"
                            aria-label={$_('detection.inat.open_label')}
                        >
                            {inatPanelOpen ? $_('detection.inat.close') : $_('detection.inat.open')}
                        </button>
                    </div>

                    {#if inatPanelOpen}
                        <div class="space-y-3">
                            {#if inatLoading}
                                <div class="text-xs font-semibold text-emerald-600/80">{$_('detection.inat.loading')}</div>
                            {:else}
                                {#if inatError}
                                    <div class="text-xs font-semibold text-rose-600">{inatError}</div>
                                {/if}
                                {#if inatDraft}
                                    <div class="grid grid-cols-2 gap-3 text-[11px] text-slate-600 dark:text-slate-300">
                                        <div class="rounded-xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                            <p class="text-[9px] font-black uppercase tracking-widest text-slate-400">{$_('detection.inat.species')}</p>
                                            <p class="font-semibold text-slate-700 dark:text-slate-200">{inatDraft.species_guess}</p>
                                        </div>
                                        <div class="rounded-xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                            <p class="text-[9px] font-black uppercase tracking-widest text-slate-400">{$_('detection.inat.observed')}</p>
                                            <p class="font-semibold text-slate-700 dark:text-slate-200">{formatDateTime(inatDraft.observed_on_string)}</p>
                                        </div>
                                    </div>
                                    <div class="grid grid-cols-2 gap-3">
                                        <div>
                                            <label for="inat-lat" class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.latitude')}</label>
                                            <input
                                                id="inat-lat"
                                                type="number"
                                                step="0.0001"
                                                bind:value={inatLat}
                                                class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                            />
                                        </div>
                                        <div>
                                            <label for="inat-lon" class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.longitude')}</label>
                                            <input
                                                id="inat-lon"
                                                type="number"
                                                step="0.0001"
                                                bind:value={inatLon}
                                                class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                            />
                                        </div>
                                    </div>
                                    <div>
                                        <label for="inat-place" class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.place')}</label>
                                        <input
                                            id="inat-place"
                                            type="text"
                                            bind:value={inatPlace}
                                            class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                        />
                                    </div>
                                    <div>
                                        <label for="inat-notes" class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.notes')}</label>
                                        <textarea
                                            id="inat-notes"
                                            rows="3"
                                            bind:value={inatNotes}
                                            class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                        ></textarea>
                                    </div>
                                    <button
                                        type="button"
                                        onclick={submitInat}
                                        disabled={inatSubmitting || (inatPreview && !inatConnectedUser)}
                                        class="w-full py-2 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-black uppercase tracking-widest disabled:opacity-50"
                                    >
                                        {inatSubmitting ? $_('detection.inat.submitting') : $_('detection.inat.submit')}
                                    </button>
                                {/if}
                            {/if}
                        </div>
                    {/if}
                </div>
            {/if}

            <!-- AI Analysis -->
            {#if llmReady && aiAnalysis}
                <div class="space-y-3">
                    <div class="ai-panel ai-surface">
                        <div class="ai-panel__label">{$_('detection.ai.insight')}</div>
                        <div class="ai-panel__content ai-markdown ai-markdown-surface">
                            {@html renderMarkdown(aiAnalysis)}
                        </div>
                    </div>
                    {#if authStore.canModify && llmReady}
                        <button
                            onclick={() => handleAIAnalysis(true)}
                            disabled={analyzingAI}
                            class="w-full py-2 px-4 bg-teal-500/10 hover:bg-teal-500/20 text-teal-600 dark:text-teal-400 font-semibold text-sm rounded-xl transition-all flex items-center justify-center gap-2 border border-teal-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                            title={$_('detection.ai.regenerate_warning', { default: 'Regenerate analysis (clears AI conversation history for this detection)' })}
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            {analyzingAI ? $_('detection.ai.regenerating') : $_('detection.ai.regenerate')}
                        </button>
                        {#if conversationTurns.length > 0}
                            <p class="text-[10px] font-semibold text-slate-500 dark:text-slate-400">
                                {$_('detection.ai.regenerate_clears_chat_note', { default: 'Note: Regenerating clears the AI conversation history for this detection.' })}
                            </p>
                        {/if}
                    {/if}
                </div>
            {:else if llmReady && !analyzingAI && authStore.canModify}
                <button
                    onclick={() => handleAIAnalysis()}
                    class="w-full py-3 px-4 bg-teal-500/10 hover:bg-teal-500/20 text-teal-600 dark:text-teal-400 font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-teal-500/20"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    {$_('detection.ai.ask')}
                </button>
            {:else if analyzingAI}
                <div class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold rounded-xl flex items-center justify-center gap-3 animate-pulse">
                    <div class="w-4 h-4 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                    {$_('detection.ai.analyzing')}
                </div>
            {/if}

            {#if llmReady && aiAnalysis && authStore.canViewAiConversation}
                <div class="space-y-3">
                    <p class="text-[10px] font-black text-slate-500 uppercase tracking-[0.2em]">
                        {$_('detection.ai.conversation_title')}
                    </p>
                    <div class="ai-thread">
                    {#if conversationLoading}
                        <div class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold rounded-xl flex items-center justify-center gap-3 animate-pulse">
                            <div class="w-4 h-4 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                            {$_('detection.ai.conversation_loading')}
                        </div>
                    {:else if conversationError}
                        <div class="rounded-xl border border-rose-200 dark:border-rose-800/40 bg-rose-50 dark:bg-rose-900/20 p-3 text-xs text-rose-600 dark:text-rose-300">
                            {conversationError}
                        </div>
                    {:else if conversationTurns.length === 0}
                        <p class="text-xs text-slate-500 dark:text-slate-400">
                            {$_('detection.ai.conversation_empty')}
                        </p>
                    {:else}
                        <div class="space-y-2">
                            {#each conversationTurns as turn}
                                <div class={`ai-bubble ${turn.role === 'assistant' ? 'ai-bubble--assistant ai-surface' : 'ai-bubble--user'}`}>
                                    <div class="ai-bubble__role">
                                        {turn.role === 'assistant' ? $_('detection.ai.assistant') : $_('detection.ai.user')}
                                    </div>
                                    {#if turn.role === 'assistant'}
                                        <div class="ai-bubble__content ai-markdown ai-markdown-surface">
                                            {@html renderMarkdown(turn.content)}
                                        </div>
                                    {:else}
                                        <div class="ai-bubble__content">{turn.content}</div>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                    {/if}

                    {#if authStore.canModify}
                        <div class="space-y-2">
                            <textarea
                                rows="2"
                                bind:value={conversationInput}
                                placeholder={$_('detection.ai.conversation_placeholder')}
                                class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 text-xs font-medium text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500"
                            ></textarea>
                            <button
                                type="button"
                                onclick={sendConversation}
                                disabled={!conversationInput.trim() || conversationSending}
                                class="w-full py-2 px-4 rounded-xl bg-teal-500 hover:bg-teal-600 text-white text-xs font-black uppercase tracking-widest disabled:opacity-50"
                            >
                                {conversationSending ? $_('detection.ai.sending') : $_('detection.ai.send')}
                            </button>
                        </div>
                    {/if}
                    </div>

                    
                </div>
            {/if}

            <!-- Actions -->
            {#if hasOwnerDetectionActions}
                <div class="flex gap-2">
                    <button
                        onclick={handleReclassifyClick}
                        class="flex-1 py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors"
                    >
                        {$_('actions.reclassify')}
                    </button>

                    <div class="relative flex-1">
                        <button
                            onclick={() => showTagDropdown = !showTagDropdown}
                            disabled={updatingTag}
                            class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50"
                        >
                            {updatingTag ? $_('common.saving') : $_('actions.manual_tag')}
                        </button>
                    </div>
                </div>
            {/if}

	            <!-- Bottom Actions -->
            <div class="flex gap-2 pt-2">
	                {#if hasOwnerDetectionActions}
	                    <button
	                        onclick={handleDelete}
	                        class="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 hover:bg-red-100 transition-colors"
	                        title={$_('actions.delete_detection')}
                    >
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                    </button>
                    <button
                        onclick={handleHide}
                        class="p-3 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-600 hover:bg-slate-200 transition-colors"
                        title={$_('actions.hide_detection')}
                    >
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                        </svg>
                    </button>
                {/if}
                <button
                    onclick={handleSpeciesInfo}
                    class="flex-1 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/20"
                >
                    {$_('actions.species_info')}
                </button>
            </div>
            </div>
        </div>

        {#if hasOwnerDetectionActions && showTagDropdown}
            <div
                class="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 overscroll-contain touch-none"
                onclick={(e) => {
                    if (e.target === e.currentTarget && !updatingTag) {
                        showTagDropdown = false;
                    }
                }}
                onkeydown={(e) => {
                    if ((e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget && !updatingTag) {
                        e.preventDefault();
                        showTagDropdown = false;
                    }
                }}
                role="button"
                tabindex="0"
            >
                <div
                    class="w-full max-w-md mx-2 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden animate-in fade-in zoom-in-95 touch-pan-y"
                    aria-busy={updatingTag}
                >
                    <div class="px-5 py-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
                        <h4 class="text-sm font-black text-slate-800 dark:text-slate-100 uppercase tracking-widest">
                            {$_('actions.manual_tag')}
                        </h4>
                        <button
                            type="button"
                            onclick={() => showTagDropdown = false}
                            disabled={updatingTag}
                            class="text-xs font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                        >
                            {$_('common.cancel')}
                        </button>
                    </div>
                    <div class="p-4 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
                        <input
                            type="text"
                            bind:value={tagSearchQuery}
                            disabled={updatingTag}
                            placeholder={$_('detection.tagging.search_placeholder')}
                            class="w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none"
                        />
                    </div>
                    <div class="max-h-72 overflow-y-auto overscroll-contain p-1">
                        {#each searchResults as result}
                            {@const names = getResultNames(result)}
                            {@const isPending = updatingTag && pendingManualTagId === result.id}
                            <button
                                type="button"
                                onclick={() => handleManualTag(result)}
                                disabled={updatingTag}
                                class="w-full px-4 py-2.5 text-left text-sm font-medium rounded-lg transition-all touch-manipulation hover:bg-teal-50 dark:hover:bg-teal-900/20 hover:text-teal-600 dark:hover:text-teal-400 disabled:opacity-60 disabled:cursor-wait {result.id === detection.display_name ? 'bg-teal-500/10 text-teal-600 font-bold' : 'text-slate-600 dark:text-slate-300'}"
                            >
                                <span class="block text-sm leading-tight">
                                    {names.primary}
                                    {#if isPending}
                                        <span class="ml-2 inline-flex items-center gap-1 text-[10px] uppercase tracking-wider text-teal-500">
                                            <span class="inline-block h-2 w-2 rounded-full border border-current border-t-transparent animate-spin"></span>
                                            {$_('common.saving')}
                                        </span>
                                    {/if}
                                </span>
                                {#if names.secondary}
                                    <span class="block text-[11px] text-slate-400 dark:text-slate-400 italic">{names.secondary}</span>
                                {/if}
                            </button>
                        {/each}
                        {#if searchResults.length === 0}
                            <p class="px-4 py-6 text-sm text-slate-400 italic text-center">
                                {isSearching ? $_('common.loading') : $_('detection.tagging.no_results')}
                            </p>
                        {/if}
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
