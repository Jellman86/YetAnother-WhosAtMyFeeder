<script lang="ts">
    import CaptureWall from '../components/CaptureWall.svelte';
    import SpeciesChecks from '../components/SpeciesChecks.svelte';
    import { buildShowcaseRows, SPOTLIGHT_PORTRAITS } from '../leaderboard/showcase';
    import { wallTiles } from '../leaderboard/wall';
    import { onDestroy, tick, untrack } from 'svelte';
    import {
        analyzeLeaderboardGraph,
        fetchDetectionsActivityHeatmapSpan,
        fetchEvents,
        type Detection,
        fetchDetectionsTimelineSpan,
        fetchLeaderboardAnalysis,
        fetchLeaderboardPortraits,
        fetchLeaderboardSpecies,
        type LeaderboardPortrait,
        fetchSpecies,
        fetchSpeciesInfo,
        fetchAudioSpeciesLeaderboard,
        type AudioSpeciesLeaderboardItem,
        type DetectionsActivityHeatmapResponse,
        type DetectionsTimelineSpanResponse,
        type LeaderboardSpan,
        type SpeciesCount,
        type SpeciesInfo
    } from '../api';
    import { chartjs, toggleChartSlice, type CanvasChartConfig, type MixedCanvasChartConfig } from '../actions/chartjs';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { defaultLeaderboardChartPreferences } from '../leaderboard/chart-defaults';
    import { buildLeaderboardAnalysisPromptConfig } from '../leaderboard/analysis-config';
    import {
        activityTimestampForMode,
        countForMode,
        deltaForMode,
        trendForMode,
        type SourceMode
    } from '../leaderboard/source-metrics';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { themeStore } from '../stores/theme.svelte';
    import { getBirdNames } from '../naming';
    import { formatTemperature } from '../utils/temperature';
    import { formatDateTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import {
        convertWindSpeed,
        getTemperatureUnitForSystem,
        resolveWeatherUnitSystem
    } from '../utils/weather-units';
    import { logger } from '../utils/logger';
    import { toLocalYMD } from '../utils/date-only';
    import { _, locale } from 'svelte-i18n';
    import { refreshCoordinator } from '../stores/refresh_coordinator.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { StaleTracker } from '../utils/stale_tracker';
    import type { ChartDataset, Plugin } from 'chart.js';
    import { doughnutInsightPlugin } from '../actions/chartjs-doughnut';
    import type { TemperatureUnit } from '../utils/temperature';
    import { evidenceFor, isCorroborated, isUnlikelyHere, trendMeasured, type SpeciesEvidence } from '../leaderboard/evidence';
    import { busiestHourOfDay } from '../leaderboard/heatmap';
    import ActivityHeatmap from '../components/ActivityHeatmap.svelte';
    import { otherSeriesColor, speciesSeriesColor, SPECIES_SERIES_SLOTS } from '../leaderboard/species-palette';

    type LeaderboardRow = {
        species: string;
        scientific_name?: string | null;
        common_name?: string | null;
        taxa_id?: number | null;
        count: number;
        prev_count?: number | null;
        heard_prev_count?: number | null;
        delta?: number | null;
        percent?: number | null;
        first_seen?: string | null;
        last_seen?: string | null;
        avg_confidence?: number | null;
        camera_count?: number | null;
        /** Detections a person named or confirmed in the window; null where the route does not count them. */
        confirmed_count?: number | null;
        /** Whether eBird birders reported it near the feeder recently; null when unknown. */
        reported_nearby?: boolean | null;
    };
    type TrendMode = 'off' | 'smooth' | 'both';
    type AudioLoadState = 'disabled' | 'loading' | 'ready' | 'error';

    // A leaderboard row enriched for the table: naming + merged BirdNET "heard" data.
    type LeaderboardTableRow = LeaderboardRow & {
        displayName: string;
        subName: string | null;
        heard_count: number;
        heard_delta: number | null;
        heard_percent: number | null;
        heard_avg: number | null;
        heard_last: string | null;
        audio_only: boolean;
    };

    let species: LeaderboardRow[] = $state([]);
    let audioSpecies = $state<AudioSpeciesLeaderboardItem[]>([]);
    let audioLoadState = $state<AudioLoadState>('disabled');
    let sourceMode = $state<SourceMode>('seen');
    let loading = $state(true);
    let pageElement: HTMLDivElement | undefined;
    let refreshHeight = $state(0);
    let error = $state<string | null>(null);
    let span = $state<LeaderboardSpan>('month');
    let leaderboardWindow = $state<{ start: string; end: string } | null>(null);
    let historyStart = $state<string | null>(null);
    let countsAreVisits = $state(false);
    let previousWindowComplete = $state(false);
    let audioPreviousWindowComplete = $state(false);
    let audioHistoryStart = $state<string | null>(null);
    // The history the current trend would need: the camera's, BirdNET's, or the later of the two.
    let trendHistoryStart = $derived(
        sourceMode === 'seen'
            ? historyStart
            : sourceMode === 'heard'
              ? audioHistoryStart
              : [historyStart, audioHistoryStart].filter((value): value is string => Boolean(value)).sort().at(-1) ?? null
    );
    let nearbyCheck = $state<{ radiusKm: number; daysBack: number } | null>(null);
    // A window whose predecessor began before the first detection has nothing to be compared
    // with; every species would read as rising. The trend is only claimed when it was measured.
    let trendAvailable = $derived(
        span !== 'all'
            && trendMeasured(sourceMode, { seen: previousWindowComplete, heard: audioPreviousWindowComplete })
    );
    let hiddenTimelineSeries = $state<string[]>([]);
    let includeUnknownBird = $state(false);
    let selectedSpecies = $state<string | null>(null);
    let timeline = $state<DetectionsTimelineSpanResponse | null>(null);
    let activityHeatmap = $state<DetectionsActivityHeatmapResponse | null>(null);
    let speciesInfoCache = $state<Record<string, SpeciesInfo>>({});
    let speciesInfoPending = $state<Record<string, boolean>>({});
    let chartEl = $state<HTMLCanvasElement | null>(null);
    let donutChartEl = $state<HTMLCanvasElement | null>(null);
    let hiddenDonutState = $state({ theme: '', indices: [] as number[] });
    let hiddenDonutSpecies = $derived(hiddenDonutState.theme === `${themeStore.isDark}-${themeStore.colorTheme}-${authStore.reducedMotion}` ? hiddenDonutState.indices : []);

    function toggleDonutSlice(index: number) {
        const visible = toggleChartSlice(donutChartEl, index);
        if (visible === null) return;
        hiddenDonutState = {
            theme: `${themeStore.isDark}-${themeStore.colorTheme}-${authStore.reducedMotion}`,
            indices: visible ? hiddenDonutSpecies.filter((item) => item !== index) : [...hiddenDonutSpecies, index],
        };
    }
    let leaderboardAnalysis = $state<string | null>(null);
    let leaderboardAnalysisTimestamp = $state<string | null>(null);
    let leaderboardAnalysisLoading = $state(false);
    let leaderboardAnalysisError = $state<string | null>(null);
    let leaderboardConfigKey = $state<string | null>(null);
    let llmReady = $state(false);
    let showTemperature = $state(false);
    let showWind = $state(false);
    let showPrecip = $state(false);
    let chartViewMode = $state<'auto' | 'line' | 'bar'>('bar');
    let trendMode = $state<TrendMode>('off');
    let leaderboardAbortController: AbortController | null = null;
    let leaderboardLoadGeneration = 0;
    const speciesInfoAbortController = new AbortController();
    const MAX_SPECIES_INFO_CONCURRENCY = 3;
    const MAX_SPECIES_INFO_CACHE_ENTRIES = 100;
    let activeSpeciesInfoRequests = 0;
    const speciesInfoWaiters: Array<() => void> = [];
    let destroyed = false;
    const speciesInfoLocale = $derived((($locale || 'en') as string).split(/[-_]/)[0].toLowerCase());

    function getSpeciesInfoCacheKey(speciesName: string, language: string): string {
        return `${language}:${speciesName}`;
    }

    function getCachedSpeciesInfo(speciesName?: string | null): SpeciesInfo | null {
        if (!speciesName) return null;
        return speciesInfoCache[getSpeciesInfoCacheKey(speciesName, speciesInfoLocale)] || null;
    }

    const enrichmentModeSetting = $derived(settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment');
    const enrichmentSingleProviderSetting = $derived(settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia');
    const enrichmentSummaryProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_summary_source ?? authStore.enrichmentSummarySource ?? 'wikipedia')
    );
    const summaryEnabled = $derived(enrichmentSummaryProvider !== 'disabled');
    const canUseLeaderboardAnalysis = $derived(llmReady && authStore.canModify);
    const birdnetEnabled = $derived(
        (settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false) && authStore.canViewAudio
    );

    $effect(() => {
        llmReady = settingsStore.llmReady;
        if (!llmReady) {
            leaderboardAnalysis = null;
            leaderboardAnalysisTimestamp = null;
            leaderboardAnalysisError = null;
        }
    });

    let leaderboardSpecies = $derived(() => {
        if (includeUnknownBird) return species;
        return species.filter((s) => s.species !== "Unknown Bird");
    });

    // Derived processed species with naming logic
    let processedSpecies = $derived(() => {
        const showCommon = settingsStore.displayCommonNames;
        const preferSci = settingsStore.scientificNamePrimary;

        return leaderboardSpecies().map(item => {
            const naming = getBirdNames(item, showCommon, preferSci);
            return {
                ...item,
                displayName: naming.primary,
                subName: naming.secondary
            };
        });
    });

    // Derived sorted species
    let sortedSpecies = $derived(() => {
        const sorted = [...processedSpecies()];
        sorted.sort((a, b) => (b.count || 0) - (a.count || 0));
        return sorted;
    });

    // Stats
    let totalCount = $derived(leaderboardSpecies().reduce((sum, s) => sum + (s.count || 0), 0));
    let maxCount = $derived(Math.max(...leaderboardSpecies().map(s => s.count || 0), 1));

    let topByCount = $derived(sortedSpecies()[0]);

    let leaderboardRows = $derived(leaderboardTableRows(sourceMode));
    let sourceLeader = $derived(leaderboardRows[0] ?? null);
    // This feeder's own photograph of each leading species, fetched beside the standings and
    // never blocking them; a species without one shows its reference image, labelled.
    let portraits = $state<LeaderboardPortrait[]>([]);
    $effect(() => {
        const requestedSpan = span;
        const publicVersion = authStore.isGuest ? detectionsStore.publicHistoryVersion : 0;
        void publicVersion;
        const controller = new AbortController();
        portraits = [];
        void fetchLeaderboardPortraits(requestedSpan, controller.signal, SPOTLIGHT_PORTRAITS)
            .then((response) => {
                if (!controller.signal.aborted) portraits = response.portraits;
            })
            .catch((error) => {
                if (controller.signal.aborted) return;
                logger.warn('Leaderboard portraits unavailable', { message: getErrorMessage(error) });
            });
        return () => controller.abort();
    });
    let showcaseRows = $derived(
        buildShowcaseRows(leaderboardRows, {
            sourceMode,
            portraits,
            isFlagged: (row) => isUnlikelyHere(evidenceFor(row, { audioKnown }), row.reported_nearby),
            referenceFor: (name) => ({
                url: getCachedSpeciesInfo(name)?.thumbnail_url ?? null,
                source: getCachedSpeciesInfo(name)?.source ?? null
            })
        })
    );
    function showcaseCountLabel(count: number): string {
        if (sourceMode === 'both') {
            return countsAreVisits
                ? $_('leaderboard.showcase_visits_and_calls', { values: { count }, default: 'visits and calls' })
                : $_('leaderboard.showcase_detections_and_calls', { values: { count }, default: 'detections and calls' });
        }
        if (countsAreVisits) {
            return count === 1
                ? $_('leaderboard.showcase_visit', { default: 'visit' })
                : $_('leaderboard.showcase_visits', { values: { count }, default: 'visits' });
        }
        return count === 1
            ? $_('leaderboard.showcase_detection', { default: 'detection' })
            : $_('leaderboard.showcase_detections', { values: { count }, default: 'detections' });
    }
    // The opener: a contact sheet of this feeder's own visits in the window. It loads beside the
    // standings and never blocks them; a failed load simply leaves the wall out.
    const WALL_CAPTURES = 400;
    // A capture is matched to its species by name, scientific name or taxon, so the list carries those.
    const WALL_FIELDS = 'frigate_event,detection_time,display_name,score,camera_name,has_clip,has_snapshot,is_hidden,observation_source,scientific_name,taxa_id';
    // A guest's photographs share the request budget with everything else the page asks for.
    const GUEST_WALL_TILES = 24;
    // The captures are kept with the span they were fetched for, so a wall never shows one window
    // under another's heading while the next load is in flight.
    let wallFetched = $state<{ span: LeaderboardSpan | null; detections: Detection[] }>({ span: null, detections: [] });
    // Dates select whole days, so the captures are cut to the window's own start and end.
    let wallDetections = $derived.by(() => {
        if (wallFetched.span !== span) return [];
        const start = leaderboardWindow ? Date.parse(leaderboardWindow.start) : Number.NaN;
        const end = leaderboardWindow ? Date.parse(leaderboardWindow.end) : Number.NaN;
        if (Number.isNaN(start) || Number.isNaN(end)) return wallFetched.detections;
        return wallFetched.detections.filter((detection) => {
            const at = Date.parse(detection.detection_time);
            return Number.isNaN(at) || (at >= start && at <= end);
        });
    });
    // The skeleton stands in only for a window's first answer: a refresh of a window already known to be
    // too quiet for a wall must not push the page about with a placeholder.
    let wallLoading = $state(true);
    $effect(() => {
        const requestedSpan = span;
        const range = leaderboardWindow;
        const publicVersion = authStore.isGuest ? detectionsStore.publicHistoryVersion : 0;
        void publicVersion;
        // The captures shown must belong to what the page now asks about: a withdrawn window is cleared at
        // once, as the portraits are, instead of staying on screen until the new answer arrives.
        if (requestedSpan !== 'all' && range === null) {
            wallLoading = true;
            return;
        }
        const controller = new AbortController();
        wallLoading = true;
        if (authStore.isGuest) wallFetched = { span: requestedSpan, detections: [] };
        void fetchEvents({
            limit: WALL_CAPTURES,
            fields: WALL_FIELDS,
            startDate: requestedSpan === 'all' || !range ? undefined : toLocalYMD(range.start),
            endDate: requestedSpan === 'all' || !range ? undefined : toLocalYMD(range.end),
            requestKey: 'leaderboard:wall',
            signal: controller.signal
        })
            .then((response) => {
                if (!controller.signal.aborted) wallFetched = { span: requestedSpan, detections: response };
            })
            .catch((error) => {
                if (controller.signal.aborted) return;
                wallFetched = { span: requestedSpan, detections: [] };
                logger.warn('Leaderboard wall unavailable', { message: getErrorMessage(error) });
            })
            .finally(() => {
                if (!controller.signal.aborted) wallLoading = false;
            });
        return () => controller.abort();
    });
    let leaderboardWall = $derived(
        wallTiles(wallDetections, showcaseRows, {
            reviewThreshold: settingsStore.settings?.classification_threshold ?? null,
            filmEvents: new Set(portraits.filter((portrait) => portrait.film_url).map((portrait) => portrait.frigate_event))
        })
    );
    $effect(() => {
        // The reference image is what stands in for a species with no crop of its own.
        for (const row of showcaseRows) void loadSpeciesInfo(row.key);
    });
    function scrollToChecks(): void {
        const checks = document.querySelector<HTMLElement>('[data-spotlight-checks]');
        if (!checks) return;
        const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduced-motion');
        checks.scrollIntoView({ behavior: still ? 'auto' : 'smooth', block: 'nearest' });
        checks.querySelector<HTMLElement>('button')?.focus({ preventScroll: true });
    }
    let topByTrend = $derived(
        !trendAvailable
            ? null
            : [...leaderboardRows]
                .filter((row) => (deltaForMode(row, sourceMode) ?? 0) > 0)
                .sort(
                    (a, b) => (deltaForMode(b, sourceMode) ?? 0) - (deltaForMode(a, sourceMode) ?? 0)
                )[0] ?? null
    );
    let mostRecent = $derived([...leaderboardRows].sort((a, b) => {
        const aTime = Date.parse(activityTimestampForMode(a, sourceMode) ?? '') || 0;
        const bTime = Date.parse(activityTimestampForMode(b, sourceMode) ?? '') || 0;
        return bTime - aTime;
    })[0] ?? null);

    // BirdNET silence only means "not heard" when it was listening and its window loaded.
    let audioKnown = $derived(birdnetEnabled && audioLoadState === 'ready');
    let rowEvidence = $derived(
        new Map(leaderboardRows.map((row) => [`${row.species}|${row.audio_only}`, evidenceFor(row, { audioKnown })] as const))
    );
    function evidenceOf(row: LeaderboardTableRow): SpeciesEvidence {
        return rowEvidence.get(`${row.species}|${row.audio_only}`) ?? 'unknown';
    }
    // "The rest are the camera alone" is only true when no row's evidence is unknown; all time has no
    // confirmation counts, so there the band says so instead of counting.
    let evidenceKnown = $derived(rowEvidence.size > 0 && [...rowEvidence.values()].every((evidence) => evidence !== 'unknown'));
    let corroboratedCount = $derived([...rowEvidence.values()].filter(isCorroborated).length);
    function evidenceLabel(evidence: SpeciesEvidence): string {
        if (evidence === 'confirmed') return $_('leaderboard.evidence_confirmed', { default: 'Confirmed by you' });
        if (evidence === 'seen_and_heard') return $_('leaderboard.evidence_seen_and_heard', { default: 'Also heard' });
        if (evidence === 'heard_only') return $_('leaderboard.evidence_heard_only', { default: 'Heard only' });
        if (evidence === 'camera_only') return $_('leaderboard.evidence_camera_only', { default: 'Camera only' });
        if (evidence === 'unconfirmed') return $_('leaderboard.evidence_unconfirmed', { default: 'Not confirmed' });
        return '—';
    }
    let unlikelyRows = $derived(
        leaderboardRows.filter((row) => isUnlikelyHere(evidenceOf(row), row.reported_nearby))
    );
    let unlikelyKeys = $derived(new Set(unlikelyRows.map((row) => `${row.species}|${row.audio_only}`)));
    function unlikelyHere(row: LeaderboardTableRow): boolean {
        return unlikelyKeys.has(`${row.species}|${row.audio_only}`);
    }
    let showCameraColumn = $derived(leaderboardRows.some((row) => (row.camera_count ?? 0) > 1));
    let unidentifiedCount = $derived(species.find((row) => row.species === 'Unknown Bird')?.count ?? 0);
    let busiestHour = $derived(busiestHourOfDay(activityHeatmap?.cells ?? []));

    // The weekday grid can show one species' pattern: "when does the Robin come?" is the question
    // the all-species grid cannot answer. A choice that falls out of the window's list lapses.
    let heatmapSpeciesOptions = $derived(
        leaderboardRows.filter((row) => !row.audio_only && row.count > 0 && row.species !== 'Unknown Bird').slice(0, 5)
    );
    let heatmapChoice = $state<string | null>(null);
    let heatmapSpecies = $derived(
        heatmapChoice && heatmapSpeciesOptions.some((row) => row.species === heatmapChoice) ? heatmapChoice : null
    );
    let speciesHeatmap = $state.raw<DetectionsActivityHeatmapResponse | null>(null);
    let speciesHeatmapLoading = $state(false);
    let speciesHeatmapFailed = $state(false);
    $effect(() => {
        const requested = heatmapSpecies;
        const requestedSpan = span;
        if (!requested) {
            speciesHeatmapLoading = false;
            speciesHeatmapFailed = false;
            return;
        }
        const controller = new AbortController();
        speciesHeatmapLoading = true;
        speciesHeatmapFailed = false;
        fetchDetectionsActivityHeatmapSpan(requestedSpan, controller.signal, requested)
            .then((response) => {
                if (controller.signal.aborted) return;
                speciesHeatmap = response;
                speciesHeatmapLoading = false;
            })
            .catch((error) => {
                if (controller.signal.aborted) return;
                speciesHeatmapLoading = false;
                speciesHeatmapFailed = true;
                logger.warn('Species activity heatmap unavailable', { message: getErrorMessage(error) });
            });
        return () => controller.abort();
    });
    // While another species loads, the previous grid stays (dimmed) under its own name, so the
    // label never describes data that is not on screen.
    let shownHeatmap = $derived(heatmapSpecies ? speciesHeatmap : activityHeatmap);
    let heatmapSubject = $derived(
        shownHeatmap?.species
            ? (heatmapSpeciesOptions.find((row) => row.species === shownHeatmap?.species)?.displayName ?? shownHeatmap.species)
            : null
    );

    // Lookup of BirdNET "heard" rollups keyed by scientific name (preferred) and
    // localized species name, so we can merge them onto the visual leaderboard rows.
    let audioByKey = $derived(() => {
        const map = new Map<string, AudioSpeciesLeaderboardItem>();
        for (const a of audioSpecies) {
            if (a.scientific_name) map.set(`sci:${a.scientific_name.toLowerCase()}`, a);
            if (a.species) map.set(`nm:${a.species.toLowerCase()}`, a);
        }
        return map;
    });

    function heardForRow(row: LeaderboardRow, map: Map<string, AudioSpeciesLeaderboardItem>) {
        if (row.scientific_name) {
            const bySci = map.get(`sci:${row.scientific_name.toLowerCase()}`);
            if (bySci) return bySci;
        }
        if (row.species) return map.get(`nm:${row.species.toLowerCase()}`);
        return undefined;
    }

    // Rows for the leaderboard table: visual species with heard data merged in, plus
    // (in Heard/Both modes) audio-only species that were never seen on camera. Sort key
    // follows the active source toggle. Visual analytics remain separate, while the
    // podium and ranking list follow the source the user selected.
    function leaderboardTableRows(mode: SourceMode): LeaderboardTableRow[] {
        const showCommon = settingsStore.displayCommonNames;
        const preferSci = settingsStore.scientificNamePrimary;
        const map = audioByKey();
        const usedAudioKeys = new Set<string>();

        const rows: LeaderboardTableRow[] = leaderboardSpecies().map((item) => {
            const naming = getBirdNames(item, showCommon, preferSci);
            const heard = heardForRow(item, map);
            if (heard) {
                if (heard.scientific_name) usedAudioKeys.add(`sci:${heard.scientific_name.toLowerCase()}`);
                if (heard.species) usedAudioKeys.add(`nm:${heard.species.toLowerCase()}`);
            }
            return {
                ...item,
                displayName: naming.primary,
                subName: naming.secondary,
                heard_count: heard?.heard_count ?? 0,
                heard_prev_count: heard?.heard_prev_count ?? null,
                heard_delta: heard?.heard_delta ?? null,
                heard_percent: heard?.heard_percent ?? null,
                heard_avg: heard?.avg_confidence ?? null,
                heard_last: heard?.last_heard ?? null,
                audio_only: false
            };
        });

        if (birdnetEnabled && mode !== 'seen') {
            for (const a of audioSpecies) {
                const sciKey = a.scientific_name ? `sci:${a.scientific_name.toLowerCase()}` : null;
                const nmKey = a.species ? `nm:${a.species.toLowerCase()}` : null;
                if ((sciKey && usedAudioKeys.has(sciKey)) || (nmKey && usedAudioKeys.has(nmKey))) continue;
                if (!includeUnknownBird && a.species === 'Unknown Bird') continue;
                rows.push({
                    species: a.species,
                    scientific_name: a.scientific_name ?? null,
                    common_name: null,
                    taxa_id: null,
                    count: 0,
                    prev_count: null,
                    delta: null,
                    percent: null,
                    first_seen: null,
                    last_seen: a.last_heard ?? null,
                    avg_confidence: null,
                    camera_count: null,
                    displayName: a.species,
                    subName: a.scientific_name ?? null,
                    heard_count: a.heard_count,
                    heard_prev_count: a.heard_prev_count,
                    heard_delta: a.heard_delta,
                    heard_percent: a.heard_percent,
                    heard_avg: a.avg_confidence,
                    heard_last: a.last_heard ?? null,
                    audio_only: true
                });
                if (sciKey) usedAudioKeys.add(sciKey);
                if (nmKey) usedAudioKeys.add(nmKey);
            }
        }

        const sortValue = (r: LeaderboardTableRow) =>
            mode === 'heard'
                ? (r.heard_count || 0)
                : mode === 'both'
                    ? (r.count || 0) + (r.heard_count || 0)
                    : (r.count || 0);
        rows.sort((a, b) => sortValue(b) - sortValue(a));
        return rows;
    }

    let maxHeard = $derived(Math.max(...leaderboardRows.map((row) => row.heard_count || 0), 1));
    let sourceTotal = $derived(
        leaderboardRows.reduce((total, row) => total + countForMode(row, sourceMode), 0)
    );

    const leaderboardStale = new StaleTracker(120_000); // 2 minutes

    onDestroy(() => {
        destroyed = true;
        leaderboardLoadGeneration += 1;
        leaderboardAbortController?.abort();
        speciesInfoAbortController.abort();
    });

    $effect(() => {
        const _deps = [span];
        void loadLeaderboard();
    });

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => {
            // Clear private records immediately, but keep the document tall enough
            // that the browser does not clamp the reader's scroll position.
            refreshHeight = pageElement?.getBoundingClientRect().height ?? 0;
            species = [];
            audioSpecies = [];
            timeline = null;
            leaderboardWindow = null;
            historyStart = null;
            audioHistoryStart = null;
            previousWindowComplete = false;
            audioPreviousWindowComplete = false;
            activityHeatmap = null;
            speciesHeatmap = null;
            heatmapChoice = null;
            leaderboardAnalysis = null;
            leaderboardAnalysisTimestamp = null;
            void loadLeaderboard();
        });
    });

    // Re-fetch leaderboard when tab regains focus or user navigates here,
    // but only if the data is older than the stale threshold.
    $effect(() => {
        return refreshCoordinator.register(async () => {
            if (loading || !leaderboardStale.isStale()) return;
            await loadLeaderboard();
        });
    });

    $effect(() => {
        return pageRefreshAction.register(loadLeaderboard);
    });

    $effect(() => {
        if (!includeUnknownBird && selectedSpecies === "Unknown Bird") {
            selectedSpecies = null;
        }
    });

    function mapAllTimeSpecies(list: SpeciesCount[]): LeaderboardRow[] {
        return list.map((s) => ({
            species: s.species,
            scientific_name: s.scientific_name ?? null,
            common_name: s.common_name ?? null,
            taxa_id: null,
            count: s.count ?? 0,
            first_seen: s.first_seen ?? null,
            last_seen: s.last_seen ?? null,
            avg_confidence: s.avg_confidence ?? null,
            camera_count: s.camera_count ?? null,
            confirmed_count: null,
            prev_count: null,
            delta: null,
            percent: null
        }));
    }

    // Windows rank by visits, the object the dashboard shows, when the route counts them; an older
    // route only has frames, and the page then says detections rather than calling them visits.
    function windowCountsAreVisits(resp: Awaited<ReturnType<typeof fetchLeaderboardSpecies>>): boolean {
        return (resp.species || []).some((s) => typeof s.window_visit_count === 'number' && s.window_visit_count > 0);
    }

    function mapWindowSpecies(resp: Awaited<ReturnType<typeof fetchLeaderboardSpecies>>, visits: boolean): LeaderboardRow[] {
        return (resp.species || []).map((s) => {
            const count = visits ? (s.window_visit_count ?? 0) : (s.window_count ?? 0);
            const prevCount = visits ? (s.window_prev_visit_count ?? 0) : (s.window_prev_count ?? 0);
            return {
            species: s.species,
            scientific_name: s.scientific_name ?? null,
            common_name: s.common_name ?? null,
            taxa_id: s.taxa_id ?? null,
            count,
            prev_count: prevCount,
            delta: count - prevCount,
            percent: prevCount > 0 ? ((count - prevCount) / prevCount) * 100 : 0,
            first_seen: s.window_first_seen ?? null,
            last_seen: s.window_last_seen ?? null,
            avg_confidence: s.window_avg_confidence ?? null,
            camera_count: s.window_camera_count ?? null,
            confirmed_count: s.window_confirmed_count ?? null,
            reported_nearby: s.reported_nearby ?? null
            };
        });
    }

    function selectCompareSpecies(rows: LeaderboardRow[]): string[] {
        const source = includeUnknownBird
            ? rows
            : rows.filter((item) => item.species !== "Unknown Bird");
        return [...source]
            .sort((a, b) => (b.count || 0) - (a.count || 0))
            .map((item) => item.scientific_name || item.species)
            .filter(Boolean)
            .slice(0, SPECIES_SERIES_SLOTS);
    }

    async function loadLeaderboard() {
        leaderboardAbortController?.abort();
        const controller = new AbortController();
        leaderboardAbortController = controller;
        const loadGeneration = ++leaderboardLoadGeneration;
        const requestedSpan = span;
        loading = true;
        error = null;
        leaderboardWindow = null;
        hiddenDonutState = { theme: '', indices: [] };
        hiddenTimelineSeries = [];
        audioLoadState = birdnetEnabled ? 'loading' : 'disabled';
        if (!birdnetEnabled) audioSpecies = [];
        audioPreviousWindowComplete = false;
        audioHistoryStart = null;
        // Fetch species and timeline independently so a chart/weather failure
        // doesn't make the leaderboard table disappear.
        try {
            if (requestedSpan === 'all') {
                const allSpecies = await fetchSpecies(controller.signal);
                if (loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted) return;
                species = mapAllTimeSpecies(allSpecies);
                countsAreVisits = false;
                leaderboardWindow = null;
                historyStart = null;
                previousWindowComplete = false;
                nearbyCheck = null;
            } else {
                const response = await fetchLeaderboardSpecies(requestedSpan, controller.signal);
                if (loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted) return;
                countsAreVisits = windowCountsAreVisits(response);
                species = mapWindowSpecies(response, countsAreVisits);
                leaderboardWindow = {
                    start: response.window_start,
                    end: response.window_end
                };
                historyStart = response.history_start ?? null;
                previousWindowComplete = response.previous_window_complete ?? false;
                nearbyCheck = response.nearby_radius_km && response.nearby_days_back
                    ? { radiusKm: response.nearby_radius_km, daysBack: response.nearby_days_back }
                    : null;
            }
        } catch (e) {
            if (loadGeneration !== leaderboardLoadGeneration || controller.signal.aborted) return;
            error = $_('leaderboard.load_failed');
            species = [];
            leaderboardWindow = null;
            if (isTransientRequestError(e)) {
                logger.warn('Leaderboard species fetch failed (transient)', {
                    message: getErrorMessage(e)
                });
            } else {
                logger.error('Failed to load leaderboard species', e);
            }
        }

        if (loadGeneration !== leaderboardLoadGeneration) return;

        const compareSpecies = selectCompareSpecies(species);
        const [timelineResult, heatmapResult, audioResult] = await Promise.allSettled([
            fetchDetectionsTimelineSpan(requestedSpan, {
                includeWeather: true,
                compareSpecies,
                signal: controller.signal
            }),
            fetchDetectionsActivityHeatmapSpan(requestedSpan, controller.signal),
            birdnetEnabled ? fetchAudioSpeciesLeaderboard(requestedSpan, controller.signal) : Promise.resolve(null),
        ]);
        if (loadGeneration !== leaderboardLoadGeneration) return;

        // Audio "heard" data is supplementary — a failure here must not disturb the
        // visual leaderboard, so it is handled independently and degrades to empty.
        if (audioResult.status === 'fulfilled') {
            audioSpecies = audioResult.value?.species ?? [];
            audioPreviousWindowComplete = audioResult.value?.previous_window_complete ?? false;
            audioHistoryStart = audioResult.value?.history_start ?? null;
            audioLoadState = birdnetEnabled ? 'ready' : 'disabled';
        } else {
            audioSpecies = [];
            audioLoadState = 'error';
            if (isTransientRequestError(audioResult.reason)) {
                logger.warn('Audio species leaderboard fetch failed (transient)', {
                    message: getErrorMessage(audioResult.reason)
                });
            } else {
                logger.error('Failed to load audio species leaderboard', audioResult.reason);
            }
        }

        if (timelineResult.status === 'fulfilled') {
            timeline = timelineResult.value;
        } else {
            timeline = null;
            if (isTransientRequestError(timelineResult.reason)) {
                logger.warn('Leaderboard timeline fetch failed (transient)', {
                    message: getErrorMessage(timelineResult.reason)
                });
            } else {
                logger.error('Failed to load leaderboard timeline', timelineResult.reason);
            }
        }

        if (heatmapResult.status === 'fulfilled') {
            activityHeatmap = heatmapResult.value;
        } else {
            activityHeatmap = null;
            if (isTransientRequestError(heatmapResult.reason)) {
                logger.warn('Leaderboard activity heatmap fetch failed (transient)', {
                    message: getErrorMessage(heatmapResult.reason)
                });
            } else {
                logger.error('Failed to load activity heatmap', heatmapResult.reason);
            }
        }

        if (!error) leaderboardStale.touch();
        if (loadGeneration === leaderboardLoadGeneration) {
            loading = false;
            leaderboardAbortController = null;
            await tick();
            if (loadGeneration === leaderboardLoadGeneration) refreshHeight = 0;
        }
    }

    function acquireSpeciesInfoSlot(): Promise<void> {
        if (activeSpeciesInfoRequests < MAX_SPECIES_INFO_CONCURRENCY) {
            activeSpeciesInfoRequests += 1;
            return Promise.resolve();
        }
        return new Promise((resolve) => {
            speciesInfoWaiters.push(() => {
                activeSpeciesInfoRequests += 1;
                resolve();
            });
        });
    }

    function releaseSpeciesInfoSlot(): void {
        activeSpeciesInfoRequests = Math.max(0, activeSpeciesInfoRequests - 1);
        speciesInfoWaiters.shift()?.();
    }

    function pruneSpeciesInfoCache(cache: Record<string, SpeciesInfo>): Record<string, SpeciesInfo> {
        const next = { ...cache };
        const keys = Object.keys(next);
        for (let index = 0; index < keys.length - MAX_SPECIES_INFO_CACHE_ENTRIES; index += 1) {
            delete next[keys[index]];
        }
        return next;
    }

    async function loadSpeciesInfo(speciesName: string) {
        const cacheKey = getSpeciesInfoCacheKey(speciesName, speciesInfoLocale);
        if (
            !speciesName ||
            speciesName === "Unknown Bird" ||
            speciesInfoCache[cacheKey] ||
            speciesInfoPending[cacheKey]
        ) {
            return;
        }
        speciesInfoPending = { ...speciesInfoPending, [cacheKey]: true };
        await acquireSpeciesInfoSlot();
        try {
            if (destroyed) return;
            const info = await fetchSpeciesInfo(speciesName, speciesInfoAbortController.signal);
            speciesInfoCache = pruneSpeciesInfoCache({ ...speciesInfoCache, [cacheKey]: info });
        } catch (error) {
            if (!(error instanceof Error && error.name === 'AbortError')) {
                logger.debug('Species portrait enrichment unavailable', { species: speciesName });
            }
        } finally {
            releaseSpeciesInfoSlot();
            const { [cacheKey]: _discarded, ...rest } = speciesInfoPending;
            speciesInfoPending = rest;
        }
    }

    $effect(() => {
        if (topByCount?.species) {
            void loadSpeciesInfo(topByCount.species);
        }
        if (topByTrend?.species) {
            void loadSpeciesInfo(topByTrend.species);
        }
        if (mostRecent?.species) {
            void loadSpeciesInfo(mostRecent.species);
        }
    });

    $effect(() => {
        const topRows = sortedSpecies().slice(0, 20);
        for (const row of topRows) {
            if (!row?.species || row.species === "Unknown Bird") continue;
            void loadSpeciesInfo(row.species);
        }
    });

    function formatDate(value?: string | null): string {
        if (!value) return '—';
        return formatDateTime(value);
    }

    function getHeroBlurb(info: SpeciesInfo | null): string | null {
        if (!info) return null;
        const text = info.description || info.extract || null;
        if (!text) return null;
        const trimmed = text.trim();
        if (trimmed.length <= 220) return trimmed;
        return `${trimmed.slice(0, 217)}...`;
    }

    function getHeroSource(info: SpeciesInfo | null): { source: 'wikipedia' | 'inaturalist'; url: string } | null {
        if (!info) return null;
        if (info.wikipedia_url) return { source: 'wikipedia', url: info.wikipedia_url };
        if (info.summary_source_url) return { source: 'inaturalist', url: info.summary_source_url };
        if (info.source_url) return { source: 'inaturalist', url: info.source_url };
        return null;
    }

    let heroInfo = $derived(summaryEnabled && topByCount ? getCachedSpeciesInfo(topByCount.species) : null);
    let heroPortraitInfo = $derived(topByCount ? getCachedSpeciesInfo(topByCount.species) : null);
    let heroBlurb = $derived(getHeroBlurb(heroInfo));
    let heroSource = $derived(getHeroSource(heroInfo));
    function spanLabel(): string {
        if (span === 'day') return $_('leaderboard.sort_by_day');
        if (span === 'week') return $_('leaderboard.sort_by_week');
        if (span === 'month') return $_('leaderboard.sort_by_month');
        return $_('leaderboard.sort_by_total');
    }

    function wallEyebrow(): string {
        return $_('leaderboard.wall_eyebrow', {
            values: { unit: showcaseCountLabel(2), window: selectedCountLabel() },
            default: 'Most {unit} · {window}'
        });
    }

    function selectedCountLabel(): string {
        if (span === 'week') return $_('leaderboard.last_7_days');
        if (span === 'month') return $_('leaderboard.last_30_days');
        if (span === 'day') return $_('leaderboard.sort_by_day');
        return $_('leaderboard.total_sightings');
    }

    function bucketLabel(bucket?: DetectionsTimelineSpanResponse['bucket'] | null): string {
        if (bucket === 'hour') return $_('leaderboard.bucket_hour', { default: 'Hourly' });
        if (bucket === 'halfday') return $_('leaderboard.bucket_halfday', { default: 'AM/PM' });
        if (bucket === 'day') return $_('leaderboard.bucket_day', { default: 'Daily' });
        if (bucket === 'month') return $_('leaderboard.bucket_month', { default: 'Monthly' });
        return '—';
    }

    function formatShortDate(value?: string | null): string {
        if (!value) return '—';
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) return '—';
        return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    }

    function formatRangeCompact(start?: string | null, end?: string | null): string {
        if (!start || !end) return '—';
        return `${formatShortDate(start)}-${formatShortDate(end)}`;
    }

    function metricLabel(): string {
        return $_('leaderboard.metric_detections', { default: 'Detections' });
    }

    function metricValueFromPoint(point: DetectionsTimelineSpanResponse['points'][number]): number {
        return Math.max(0, Number(point.count ?? 0));
    }

    function formatMetricValue(value: number): string {
        if (!Number.isFinite(value)) return '—';
        return Math.round(value).toLocaleString();
    }

    function movingAverage(values: number[], windowSize: number): Array<number | null> {
        if (!values.length) return [];
        const out: Array<number | null> = [];
        for (let i = 0; i < values.length; i += 1) {
            const start = Math.max(0, i - windowSize + 1);
            const slice = values.slice(start, i + 1);
            if (!slice.length) {
                out.push(null);
                continue;
            }
            out.push(slice.reduce((sum, n) => sum + n, 0) / slice.length);
        }
        return out;
    }

    let timelinePoints = $derived(() => timeline?.points || []);
    let metricValues = $derived(() => timelinePoints().map((p) => metricValueFromPoint(p)));
    let metricPeak = $derived(() => metricValues().length ? Math.max(...metricValues()) : 0);
    let metricAvg = $derived(() => metricValues().length
        ? metricValues().reduce((sum, n) => sum + n, 0) / metricValues().length
        : 0);
    let showRawSeries = $derived(trendMode !== 'smooth');
    let showSmoothSeries = $derived(trendMode !== 'off');
    let smoothedMetricValues = $derived(() => movingAverage(metricValues(), 7));
    let detectionUsesBars = $derived(() => {
        if (!showRawSeries) return false;
        if (chartViewMode === 'line') return false;
        if (chartViewMode === 'bar') return true;
        return span === 'week' || span === 'month';
    });
    // Exposed at component scope so the template can adapt container height
    let isStackedChart = $derived(() => detectionUsesBars() && (timeline?.compare_series?.length ?? 0) > 0);
    let chartModeLabel = $derived(() => {
        if (chartViewMode === 'line') return $_('leaderboard.chart_line', { default: 'Line' });
        if (chartViewMode === 'bar') return $_('leaderboard.chart_bar', { default: 'Histogram' });
        return $_('leaderboard.chart_auto', { default: 'Auto' });
    });
    let isDark = $derived(() => themeStore.isDark);
    let weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    let temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));
    let windUnitLabel = $derived(
        weatherUnitSystem === 'imperial'
            ? $_('common.unit_mph', { default: 'mph' })
            : $_('common.unit_kmh', { default: 'km/h' })
    );
    let weatherByBucket = $derived(() => new Map((timeline?.weather ?? []).map((w) => [w.bucket_start, w] as const)));
    let hasWeather = $derived(() => !!(timeline?.weather && timeline.weather.length));
    let weatherOverlayEligible = $derived(() => {
        if (!timeline) return false;
        const startMs = Date.parse(timeline.window_start);
        const endMs = Date.parse(timeline.window_end);
        if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return false;
        const windowDays = Math.max(0, (endMs - startMs) / 86_400_000);
        return windowDays <= 31 && ['hour', 'halfday', 'day'].includes(timeline.bucket);
    });

    function convertTemperature(value: number | null | undefined) {
        if (value === null || value === undefined || Number.isNaN(value)) return null;
        if (temperatureUnit === 'fahrenheit') {
            return (value * 9) / 5 + 32;
        }
        return value;
    }

    type TimelineWeather = NonNullable<DetectionsTimelineSpanResponse['weather']>[number];
    function weatherValue(bucketStart: string, key: keyof TimelineWeather): number | null {
        const weather = weatherByBucket().get(bucketStart);
        const val = weather?.[key];
        if (val === undefined || val === null || Number.isNaN(val)) return null;
        return Number(val);
    }

    function bucketDurationMs(bucket?: DetectionsTimelineSpanResponse['bucket'] | null): number {
        if (bucket === 'hour') return 60 * 60 * 1000;
        if (bucket === 'halfday') return 12 * 60 * 60 * 1000;
        if (bucket === 'day') return 24 * 60 * 60 * 1000;
        // Monthly buckets vary; use a safe 30-day approximation for annotation width.
        return 30 * 24 * 60 * 60 * 1000;
    }

    let rainBandAnnotations = $derived(() => {
        if (!showPrecip || !hasWeather()) return [];
        const points = timelinePoints();
        if (!points.length) return [];
        const duration = bucketDurationMs(timeline?.bucket);
        const annotations: Array<{ x: number; x2: number; fillColor: string; opacity: number; borderColor: string }> = [];
        for (let i = 0; i < points.length; i += 1) {
            const bucketStart = points[i].bucket_start;
            const start = Date.parse(bucketStart);
            if (!Number.isFinite(start)) continue;
            const next = points[i + 1]?.bucket_start ? Date.parse(points[i + 1].bucket_start) : NaN;
            const end = Number.isFinite(next) ? next : (start + duration);
            const rain = Math.max(0, weatherValue(bucketStart, 'rain_total') ?? 0);
            const snow = Math.max(0, weatherValue(bucketStart, 'snow_total') ?? 0);
            const precip = Math.max(0, weatherValue(bucketStart, 'precip_total') ?? 0);
            const intensity = Math.max(rain + snow, precip);
            if (intensity <= 0) continue;
            const alpha = Math.min(0.28, 0.08 + (intensity * 0.12));
            annotations.push({
                x: start,
                x2: end,
                fillColor: `rgba(56, 189, 248, ${alpha.toFixed(3)})`,
                opacity: 0.85,
                borderColor: 'rgba(56, 189, 248, 0.12)'
            });
        }
        return annotations;
    });

    let chartOptions = $derived((): MixedCanvasChartConfig => {
        const points = timelinePoints();
        const indexedPoints = points
            .map((point, idx) => {
                const x = Date.parse(point.bucket_start);
                if (!Number.isFinite(x)) return null;
                return { point, idx, x };
            })
            .filter(
                (entry): entry is {
                    point: DetectionsTimelineSpanResponse['points'][number];
                    idx: number;
                    x: number;
                } => !!entry
            );

        const series: Array<{
            name: string;
            type: 'bar' | 'area' | 'line';
            color: string;
            data: Array<{ x: number; y: number | null }>;
        }> = [];
        const isBlueTit = themeStore.colorTheme === 'bluetit';
        const primaryColor = isBlueTit ? '#2563eb' : '#16a34a';
        const smoothColor = isBlueTit ? '#1d4ed8' : '#0f766e';
        const primaryName = metricLabel();
        const smoothName = $_('leaderboard.metric_smooth', { default: 'Smoothed' });

        const rawData = indexedPoints.map(({ point, x }) => ({
            x,
            y: metricValueFromPoint(point)
        }));
        const smoothData = indexedPoints.map(({ idx, x }) => ({
            x,
            y: smoothedMetricValues()[idx] ?? null
        }));
        const isStacked = detectionUsesBars() && (timeline?.compare_series?.length ?? 0) > 0;

        if (showRawSeries) {
            if (isStacked && timeline?.compare_series?.length) {
                // The compare series are requested by scientific name where one exists, so name them by both keys.
                const displayNames = new Map(
                    processedSpecies().flatMap((item) => [
                        [item.species, item.displayName] as const,
                        ...(item.scientific_name ? [[item.scientific_name, item.displayName] as const] : [])
                    ])
                );
                const compareEntries = timeline.compare_series;
                const compareMaps = compareEntries.map((entry) =>
                    new Map(
                        (entry.points || []).map((point) => [
                            point.bucket_start,
                            Math.max(0, Number(point.count ?? 0))
                        ] as const)
                    )
                );
                compareEntries.forEach((entry, idx) => {
                    series.push({
                        name: displayNames.get(entry.species) ?? entry.species,
                        type: 'bar',
                        color: speciesSeriesColor(speciesSlot().get(entry.species) ?? idx, isDark()),
                        data: indexedPoints.map(({ point, x }) => ({
                            x,
                            y: compareMaps[idx].get(point.bucket_start) ?? 0
                        }))
                    });
                });
                const otherData = indexedPoints.map(({ point, x }) => {
                    const total = metricValueFromPoint(point);
                    const compareSum = compareMaps.reduce((sum, m) => sum + (m.get(point.bucket_start) ?? 0), 0);
                    return { x, y: Math.max(0, total - compareSum) };
                });
                if (otherData.some((p) => p.y > 0)) {
                    series.push({
                        name: $_('leaderboard.other_species', { default: 'Other' }),
                        type: 'bar',
                        color: otherSeriesColor(isDark()),
                        data: otherData
                    });
                }
            } else {
                series.push({
                    name: primaryName,
                    type: detectionUsesBars() ? 'bar' : 'area',
                    color: primaryColor,
                    data: rawData
                });
            }
        }

        if (showSmoothSeries && !isStacked) {
            series.push({
                name: smoothName,
                type: 'line',
                color: smoothColor,
                data: smoothData
            });
        }

        if (!series.length) {
            series.push({
                name: primaryName,
                type: 'line',
                color: primaryColor,
                data: rawData
            });
        }

        const labels = indexedPoints.map(({ point }) => point.label);
        const datasets: ChartDataset<'bar' | 'line', number[]>[] = series.map((item) => {
            const isBar = item.type === 'bar';
            return {
                type: isBar ? 'bar' : 'line',
                label: item.name,
                data: item.data.map((point) => point.y ?? NaN),
                backgroundColor: isBar ? item.color : (item.type === 'area' ? `${item.color}33` : item.color),
                borderColor: item.color,
                borderWidth: isBar ? 0 : 2,
                borderRadius: isBar ? 3 : 0,
                maxBarThickness: timeline?.bucket === 'day' ? 24 : 18,
                fill: item.type === 'area',
                tension: isBar ? 0 : 0.32,
                pointRadius: 0,
                pointHoverRadius: 4,
                borderDash: item.name === smoothName ? [5, 4] : [],
                order: isBar ? 2 : 1,
                hidden: hiddenTimelineSeries.includes(item.name)
            };
        });
        const rainBands = rainBandAnnotations();
        const rainCells = indexedPoints.flatMap(({ x }, index) => {
            const band = rainBands.find((item) => x >= item.x && x < item.x2);
            return band ? [{ index, color: band.fillColor }] : [];
        });
        const rainPlugin: Plugin<'bar' | 'line'> = {
            id: 'leaderboardRainBands',
            beforeDatasetsDraw(chart) {
                const xScale = chart.scales.x;
                if (!xScale || !rainCells.length) return;
                const { ctx, chartArea } = chart;
                const gap = indexedPoints.length > 1
                    ? Math.abs(xScale.getPixelForValue(1) - xScale.getPixelForValue(0))
                    : chartArea.width;
                ctx.save();
                for (const { index, color } of rainCells) {
                    ctx.fillStyle = color;
                    const center = xScale.getPixelForValue(index);
                    ctx.fillRect(Math.max(chartArea.left, center - gap / 2), chartArea.top,
                        Math.min(gap, chartArea.right - Math.max(chartArea.left, center - gap / 2)), chartArea.height);
                }
                ctx.restore();
            }
        };
        const gridColor = isDark() ? 'rgba(148,163,184,0.12)' : 'rgba(148,163,184,0.2)';
        const textColor = isDark() ? '#94a3b8' : '#64748b';
        return {
            type: detectionUsesBars() ? 'bar' : 'line',
            data: { labels, datasets },
            plugins: [rainPlugin],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: typeof window !== 'undefined' && (window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduced-motion') || authStore.reducedMotion)
                    ? false : { duration: 300 },
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: (items) => indexedPoints[items[0]?.dataIndex]?.point.label ?? '',
                            label: (item) => {
                                return `${item.dataset.label ?? ''}: ${formatMetricValue(item.parsed.y ?? 0)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: isStacked,
                        // Inner alignment keeps the end labels inside the plot, so its width matches the weather charts below.
                        ticks: { color: textColor, maxTicksLimit: 6, maxRotation: 0, align: 'inner' },
                        grid: { display: false }
                    },
                    y: {
                        stacked: isStacked,
                        beginAtZero: true,
                        ticks: { color: textColor, callback: (value) => formatMetricValue(Number(value)) },
                        grid: { color: gridColor },
                        afterFit: alignValueAxis
                    }
                }
            }
        };

    });

    // Every chart in the timeline stack reserves the same width for its value axis, so the plot
    // areas line up and a temperature under a bar sits on the same bucket.
    function alignValueAxis(scale: { width: number }) {
        scale.width = 64;
    }

    type WeatherPanel = { key: 'temperature' | 'wind'; title: string; config: CanvasChartConfig };
    // Weather gets its own small charts under the detections rather than a second y-axis on them:
    // two scales on one plot invite reading a coincidence of heights as a relationship.
    let weatherPanels = $derived((): WeatherPanel[] => {
        if (!timeline || !hasWeather()) return [];
        const points = timelinePoints().filter((point) => Number.isFinite(Date.parse(point.bucket_start)));
        const labels = points.map((point) => point.label);
        const gridColor = isDark() ? 'rgba(148,163,184,0.12)' : 'rgba(148,163,184,0.2)';
        const textColor = isDark() ? '#94a3b8' : '#64748b';
        const reduced = typeof window !== 'undefined' && (window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduced-motion') || authStore.reducedMotion);
        const lineColor = isDark() ? '#cbd5e1' : '#475569';
        const panel = (
            key: WeatherPanel['key'],
            title: string,
            values: Array<number | null>,
            format: (value: number) => string
        ): WeatherPanel | null => {
            if (!values.some((value) => value !== null)) return null;
            return {
                key,
                title,
                config: {
                    type: 'line',
                    data: {
                        labels,
                        datasets: [{
                            label: title,
                            data: values.map((value) => value ?? NaN),
                            borderColor: lineColor,
                            backgroundColor: lineColor,
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            tension: 0.32,
                            spanGaps: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: reduced ? false : { duration: 300 },
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: { display: false },
                            tooltip: { callbacks: { label: (item) => `${title}: ${format(item.parsed.y ?? 0)}` } }
                        },
                        scales: {
                            // Bars sit centred in their bucket; the line must use the same offset to share x.
                            x: { offset: detectionUsesBars(), ticks: { display: false }, grid: { display: false } },
                            y: {
                                ticks: { color: textColor, maxTicksLimit: 3, callback: (value) => format(Number(value)) },
                                grid: { color: gridColor },
                                afterFit: alignValueAxis
                            }
                        }
                    }
                }
            };
        };
        return [
            showTemperature
                ? panel(
                    'temperature',
                    $_('leaderboard.temperature'),
                    points.map((point) => convertTemperature(weatherValue(point.bucket_start, 'temp_avg'))),
                    (value) => formatTemperature(value, temperatureUnit as TemperatureUnit)
                )
                : null,
            showWind
                ? panel(
                    'wind',
                    $_('leaderboard.wind_avg'),
                    points.map((point) => convertWindSpeed(weatherValue(point.bucket_start, 'wind_avg'), weatherUnitSystem)),
                    (value) => `${Math.round(value)} ${windUnitLabel}`
                )
                : null
        ].filter((item): item is WeatherPanel => item !== null);
    });

    // A species keeps its colour slot in both charts: the slot is its rank in this window.
    let speciesSlot = $derived(() => {
        const slots = new Map<string, number>();
        sortedSpecies().slice(0, SPECIES_SERIES_SLOTS).forEach((row, index) => {
            slots.set(row.species, index);
            if (row.scientific_name) slots.set(row.scientific_name, index);
        });
        return slots;
    });
    let timelineLegend = $derived(() =>
        (chartOptions().data.datasets ?? []).map((dataset) => ({
            label: String(dataset.label ?? ''),
            color: String(dataset.borderColor ?? ''),
            dashed: ((dataset as { borderDash?: number[] }).borderDash?.length ?? 0) > 0,
            line: dataset.type === 'line'
        }))
    );
    function toggleTimelineSeries(name: string) {
        hiddenTimelineSeries = hiddenTimelineSeries.includes(name)
            ? hiddenTimelineSeries.filter((item) => item !== name)
            : [...hiddenTimelineSeries, name];
    }

    function weekdayLabel(dayOfWeek: number): string {
        if (dayOfWeek === 1) return $_('leaderboard.weekday_mon', { default: 'Mon' });
        if (dayOfWeek === 2) return $_('leaderboard.weekday_tue', { default: 'Tue' });
        if (dayOfWeek === 3) return $_('leaderboard.weekday_wed', { default: 'Wed' });
        if (dayOfWeek === 4) return $_('leaderboard.weekday_thu', { default: 'Thu' });
        if (dayOfWeek === 5) return $_('leaderboard.weekday_fri', { default: 'Fri' });
        if (dayOfWeek === 6) return $_('leaderboard.weekday_sat', { default: 'Sat' });
        return $_('leaderboard.weekday_sun', { default: 'Sun' });
    }

    function hourLabel(hour: number): string {
        return `${String(Math.max(0, Math.min(23, hour))).padStart(2, '0')}:00`;
    }


    const DONUT_MAX_SLICES = SPECIES_SERIES_SLOTS;
    let donutSeries = $derived(() => {
        const sorted = sortedSpecies();
        if (!sorted.length) return { labels: [] as string[], series: [] as number[] };
        const top = sorted.slice(0, DONUT_MAX_SLICES);
        const rest = sorted.slice(DONUT_MAX_SLICES);
        const labels = top.map((s) => s.displayName);
        const values = top.map((s) => s.count || 0);
        if (rest.length > 0) {
            const otherCount = rest.reduce((sum, s) => sum + (s.count || 0), 0);
            if (otherCount > 0) {
                labels.push($_('leaderboard.other_species', { default: 'Other' }));
                values.push(otherCount);
            }
        }
        return { labels, series: values };
    });
    function donutColor(index: number): string {
        return index < DONUT_MAX_SLICES ? speciesSeriesColor(index, isDark()) : otherSeriesColor(isDark());
    }
    let donutHasData = $derived(() => donutSeries().series.some((v) => v > 0));
    let donutChartOptions = $derived((): CanvasChartConfig => {
        const { labels, series } = donutSeries();
        const totalLabel = countsAreVisits
            ? $_('leaderboard.metric_visits', { default: 'Visits' })
            : $_('leaderboard.metric_detections', { default: 'Detections' });
        const centerTotal = doughnutInsightPlugin('leaderboardCenterTotal', series, totalLabel, isDark());
        return {
            type: 'doughnut',
            data: {
                labels,
                datasets: [{ data: series, backgroundColor: labels.map((_, index) => donutColor(index)), borderColor: isDark() ? '#0a1225' : '#ffffff', borderWidth: 2 }]
            },
            plugins: [centerTotal],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: typeof window !== 'undefined' && (window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduced-motion') || authStore.reducedMotion)
                    ? false : { duration: 250 },
                cutout: '62%',
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (item) => `${item.label}: ${Number(item.raw).toLocaleString()} ${totalLabel.toLowerCase()}` } }
                }
            }
        };
    });

    const relativeUnits: Array<[Intl.RelativeTimeFormatUnit, number]> = [
        ['day', 86_400_000],
        ['hour', 3_600_000],
        ['minute', 60_000]
    ];
    function formatRelative(value?: string | null): string {
        if (!value) return '—';
        const at = Date.parse(value);
        if (!Number.isFinite(at)) return '—';
        const elapsed = at - Date.now();
        const format = new Intl.RelativeTimeFormat(($locale || 'en') as string, { numeric: 'auto', style: 'short' });
        for (const [unit, size] of relativeUnits) {
            if (Math.abs(elapsed) >= size || unit === 'minute') return format.format(Math.round(elapsed / size), unit);
        }
        return formatDate(value);
    }

    function trendTone(row: LeaderboardTableRow): string {
        const delta = deltaForMode(row, sourceMode) ?? 0;
        if (delta > 0) return 'text-success-700 dark:text-success-400';
        if (delta < 0) return 'text-rose-600 dark:text-rose-400';
        return 'text-slate-400';
    }
    function trendGlyph(row: LeaderboardTableRow): string {
        const delta = deltaForMode(row, sourceMode) ?? 0;
        return delta > 0 ? '▲' : delta < 0 ? '▼' : '';
    }

    function stableStringify(value: unknown): string {
        if (value === null || typeof value !== 'object') {
            return JSON.stringify(value);
        }
        if (Array.isArray(value)) {
            return `[${value.map(stableStringify).join(',')}]`;
        }
        const record = value as Record<string, unknown>;
        const keys = Object.keys(record).sort();
        return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(',')}}`;
    }

    async function computeConfigKey(config: Record<string, unknown>): Promise<string> {
        const raw = stableStringify(config);
        const subtle = globalThis.crypto?.subtle;
        if (subtle && globalThis.isSecureContext) {
            const data = new TextEncoder().encode(raw);
            const hash = await subtle.digest('SHA-256', data);
            return Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, '0')).join('');
        }
        let hash = 5381;
        for (let i = 0; i < raw.length; i += 1) {
            hash = ((hash << 5) + hash) + raw.charCodeAt(i);
            hash |= 0;
        }
        return `fallback-${Math.abs(hash)}`;
    }

    function sleep(ms: number) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    function buildLeaderboardConfig() {
        return {
            span,
            includeUnknownBird,
            trend_mode: trendMode,
            chart_view_mode: chartViewMode,
            chart_detection_type: detectionUsesBars() ? 'bar' : 'line',
            bucket: timeline?.bucket ?? null,
            window_start: timeline?.window_start ?? null,
            window_end: timeline?.window_end ?? null,
            total_count: timeline?.total_count ?? 0,
            points: timeline?.points?.length ?? 0,
            ...buildLeaderboardAnalysisPromptConfig({
                timeframe: `${spanLabel()} (${formatRangeCompact(timeline?.window_start, timeline?.window_end)})`,
                metricLabel: metricLabel(),
                bucketLabel: bucketLabel(timeline?.bucket),
                trendMode,
                chartDetectionType: detectionUsesBars() ? 'bar' : 'line',
                timeline,
            })
        };
    }

    async function refreshLeaderboardAnalysis() {
        if (!timeline || !canUseLeaderboardAnalysis) return;
        leaderboardAnalysisError = null;
        const config = buildLeaderboardConfig();
        const key = await computeConfigKey(config);
        if (leaderboardConfigKey === key && leaderboardAnalysis) return;
        leaderboardConfigKey = key;
        try {
            const result = await fetchLeaderboardAnalysis(key);
            leaderboardAnalysis = result.analysis;
            leaderboardAnalysisTimestamp = result.analysis_timestamp;
        } catch {
            leaderboardAnalysis = null;
            leaderboardAnalysisTimestamp = null;
        }
    }

    $effect(() => {
        if (!timeline) return;
        const _deps = [
            span,
            includeUnknownBird,
            chartViewMode,
            trendMode,
            timeline.bucket,
            timeline.window_start,
            timeline.window_end,
            timeline.total_count
        ];
        void refreshLeaderboardAnalysis();
    });

    async function runLeaderboardAnalysis(force = false) {
        if (!canUseLeaderboardAnalysis) return;
        if (!chartEl) return;
        if (!timeline?.points?.length) return;
        leaderboardAnalysisLoading = true;
        leaderboardAnalysisError = null;
        try {
            const config = buildLeaderboardConfig();
            await tick();
            await sleep(200);
            const key = await computeConfigKey(config);
            leaderboardConfigKey = key;
            const chartInstance = (chartEl as HTMLCanvasElement & { __chartjs?: unknown }).__chartjs;
            const imageBase64 = chartInstance ? chartEl.toDataURL('image/png') : null;
            if (!imageBase64) {
                throw new Error('Unable to capture chart image');
            }
            const result = await analyzeLeaderboardGraph({
                config,
                image_base64: imageBase64,
                force,
                config_key: key
            });
            leaderboardAnalysis = result.analysis;
            leaderboardAnalysisTimestamp = result.analysis_timestamp;
        } catch (e) {
            leaderboardAnalysisError = getErrorMessage(e) || 'Failed to analyze chart';
        } finally {
            await tick();
            await sleep(150);
            leaderboardAnalysisLoading = false;
        }
    }

    type AiBlock = { type: 'heading' | 'paragraph'; text: string };

    function parseAiAnalysis(text: string): AiBlock[] {
        if (!text) return [];
        const lines = text
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean);

        const blocks: AiBlock[] = [];

        for (const line of lines) {
            const headingMatch = line.match(/^#{1,6}\s+(.*)$/);
            if (headingMatch) {
                blocks.push({ type: 'heading', text: headingMatch[1] });
                continue;
            }

            const listMatch = line.match(/^[-*•]\s+(.*)$/);
            if (listMatch) {
                const last = blocks[blocks.length - 1];
                if (last?.type === 'paragraph') {
                    last.text = `${last.text} ${listMatch[1]}`.trim();
                } else {
                    blocks.push({ type: 'paragraph', text: listMatch[1] });
                }
                continue;
            }
            blocks.push({ type: 'paragraph', text: line });
        }

        return blocks;
    }

    let leaderboardAiBlocks = $derived(() => (leaderboardAnalysis ? parseAiAnalysis(leaderboardAnalysis) : []));
</script>

{#snippet unlikelyReason(radiusKm: number)}
    <span class="mt-1 flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold text-amber-800 dark:text-amber-300" data-leaderboard-unlikely-reason>
        <span class="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" aria-hidden="true"></span>
        {$_('leaderboard.unlikely_reason', { values: { radius: radiusKm }, default: 'Not reported within {radius} km' })}
    </span>
{/snippet}

{#snippet evidenceGlyph(evidence: SpeciesEvidence)}
    {#if evidence === 'confirmed'}
        <svg class="h-3.5 w-3.5 shrink-0 text-success-600 dark:text-success-400" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 10.5 3.2 3L15 6.5" /></svg>
    {:else if evidence === 'seen_and_heard' || evidence === 'heard_only'}
        <svg class="h-3.5 w-3.5 shrink-0 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" /></svg>
    {:else}
        <svg class="h-3.5 w-3.5 shrink-0 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8z" /><circle cx="12" cy="13" r="3.5" /></svg>
    {/if}
{/snippet}

<div class="space-y-10" data-leaderboard-page bind:this={pageElement} style:min-height={refreshHeight ? `${refreshHeight}px` : undefined}>
    <!-- Ranking controls -->
    <div class="border-y border-slate-200/80 py-4 dark:border-slate-700/70">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div class="flex flex-wrap gap-2" aria-label={$_('leaderboard.title')}>
            <button
                type="button"
                aria-pressed={span === 'month'}
                onclick={() => span = 'month'}
                class="tab-button {span === 'month' ? 'tab-button-active' : 'tab-button-inactive'}"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <rect x="3" y="4" width="14" height="13" rx="2"></rect>
                    <path d="M3 8h14"></path>
                </svg>
                {$_('leaderboard.sort_by_month')}
            </button>
            <button
                type="button"
                aria-pressed={span === 'week'}
                onclick={() => span = 'week'}
                class="tab-button {span === 'week' ? 'tab-button-active' : 'tab-button-inactive'}"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M4 6h12M4 10h12M4 14h8"></path>
                </svg>
                {$_('leaderboard.sort_by_week')}
            </button>
            <button
                type="button"
                aria-pressed={span === 'day'}
                onclick={() => span = 'day'}
                class="tab-button {span === 'day' ? 'tab-button-active' : 'tab-button-inactive'}"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <circle cx="10" cy="10" r="4.2"></circle>
                    <path d="M10 2.8v2.1M10 15.1v2.1M2.8 10h2.1M15.1 10h2.1"></path>
                </svg>
                {$_('leaderboard.sort_by_day')}
            </button>
            <button
                type="button"
                aria-pressed={span === 'all'}
                onclick={() => span = 'all'}
                class="tab-button {span === 'all' ? 'tab-button-active' : 'tab-button-inactive'}"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M4 10c0-2.8 2.2-5 5-5h2c2.8 0 5 2.2 5 5s-2.2 5-5 5H9c-2.8 0-5-2.2-5-5z"></path>
                </svg>
                {$_('leaderboard.sort_by_total')}
            </button>
            </div>

        <div class="flex flex-wrap items-center gap-3">
            {#if birdnetEnabled}
                <div class="inline-flex rounded-xl bg-slate-100 dark:bg-slate-800/70 p-0.5" role="group" aria-label={$_('leaderboard.source_toggle', { default: 'Detection source' })}>
                    <button
                        type="button"
                        aria-pressed={sourceMode === 'seen'}
                        onclick={() => sourceMode = 'seen'}
                        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {sourceMode === 'seen' ? 'bg-white dark:bg-slate-700 text-accent-600 dark:text-accent-300 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
                    >
                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M2.5 12S5.5 5.5 12 5.5 21.5 12 21.5 12 18.5 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.5"/></svg>
                        {$_('leaderboard.source_seen', { default: 'Seen' })}
                    </button>
                    <button
                        type="button"
                        aria-pressed={sourceMode === 'heard'}
                        onclick={() => sourceMode = 'heard'}
                        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {sourceMode === 'heard' ? 'bg-white dark:bg-slate-700 text-brand-600 dark:text-brand-300 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
                    >
                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/></svg>
                        {$_('leaderboard.source_heard', { default: 'Heard' })}
                    </button>
                    <button
                        type="button"
                        aria-pressed={sourceMode === 'both'}
                        onclick={() => sourceMode = 'both'}
                        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {sourceMode === 'both' ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-white shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
                    >
                        {$_('leaderboard.source_both', { default: 'Both' })}
                    </button>
                </div>
            {/if}

            <label class="inline-flex min-h-11 items-center gap-2 text-sm text-slate-600 dark:text-slate-300 select-none">
                <input
                    type="checkbox"
                    class="rounded border-slate-300 dark:border-slate-600 text-accent-600 focus:ring-accent-500"
                    bind:checked={includeUnknownBird}
                />
                {$_('leaderboard.include_unknown')}
            </label>
        </div>
        </div>
    </div>

    {#if error}
        <div class="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800">
            {error}
            <button onclick={loadLeaderboard} class="ml-2 underline">{$_('common.retry')}</button>
        </div>
    {/if}

    {#if loading && leaderboardRows.length === 0}
        <div class="space-y-3" role="status" aria-label={$_('common.loading', { default: 'Loading…' })}>
            {#each [1, 2, 3, 4, 5, 6] as _}
                <div class="h-16 rounded-xl bg-slate-100 motion-safe:animate-pulse dark:bg-slate-800" aria-hidden="true"></div>
            {/each}
        </div>
    {:else if sourceMode !== 'seen' && audioLoadState === 'error'}
        <div class="border-y border-rose-200 bg-rose-50/60 px-4 py-6 text-rose-800 dark:border-rose-900/70 dark:bg-rose-950/20 dark:text-rose-200" role="status">
            <h3 class="font-semibold">{$_('leaderboard.audio_unavailable_title', { default: 'BirdNET results unavailable' })}</h3>
            <p class="mt-1 text-sm">{$_('leaderboard.audio_unavailable_desc', { default: 'The listening leaderboard could not be loaded. Seen results are still available.' })}</p>
            <button class="btn btn-secondary mt-3 min-h-11 px-3 py-2 text-xs" onclick={loadLeaderboard}>
                {$_('common.retry')}
            </button>
        </div>
    {:else if leaderboardRows.length === 0}
        <div class="border-y border-slate-200 py-14 text-center dark:border-slate-700">
            <span class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-600 dark:text-brand-400" aria-hidden="true">
                <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49Z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16 8 2 22M17.5 15H9" />
                </svg>
            </span>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">{$_('leaderboard.no_species')}</h3>
            <p class="text-slate-500 dark:text-slate-400">
                {sourceMode === 'heard'
                    ? $_('leaderboard.no_audio_species', { default: 'No BirdNET detections were recorded in this period.' })
                    : species.length > 0 && !includeUnknownBird
                    ? $_('leaderboard.only_unknown_desc')
                    : $_('leaderboard.no_species_desc')}
            </p>
        </div>
    {:else}
        {#if sourceMode !== 'heard' && sourceLeader && sourceLeader.count > 0}
            <CaptureWall
                tiles={leaderboardWall}
                rows={showcaseRows}
                eyebrow={wallEyebrow()}
                label={$_('leaderboard.wall_label', { default: 'Photographs of recent visits to this feeder' })}
                countLabel={showcaseCountLabel}
                colourFor={(key) => (key ? speciesSeriesColor(speciesSlot().get(key) ?? SPECIES_SERIES_SLOTS, isDark()) : otherSeriesColor(isDark()))}
                otherColour={otherSeriesColor(isDark())}
                loading={wallLoading && wallFetched.span !== span}
                maxTiles={authStore.isGuest ? GUEST_WALL_TILES : undefined}
                onopen={(key) => (selectedSpecies = key)}
                onchecks={scrollToChecks}
            />
            <SpeciesChecks
                checks={showcaseRows.filter((row) => row.flagged)}
                countLabel={showcaseCountLabel}
                nearbyRadiusKm={nearbyCheck?.radiusKm ?? null}
                onopen={(key) => (selectedSpecies = key)}
            />
        {/if}

        <dl class="grid grid-cols-2 gap-x-6 gap-y-5 border-y border-slate-200 py-5 dark:border-slate-700 md:grid-cols-3 xl:grid-cols-6" data-leaderboard-standing>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.standing_species', { default: 'Species' })}</dt>
                <dd class="mt-1 font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{leaderboardRows.length.toLocaleString()}</dd>
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {sourceMode === 'heard'
                        ? $_('leaderboard.standing_calls', { default: 'Calls heard' })
                        : sourceMode === 'both'
                          ? countsAreVisits
                            ? $_('leaderboard.standing_visits_and_calls', { default: 'Visits and calls' })
                            : $_('leaderboard.standing_detections_and_calls', { default: 'Detections and calls' })
                          : countsAreVisits
                            ? $_('leaderboard.metric_visits', { default: 'Visits' })
                            : $_('leaderboard.metric_detections', { default: 'Detections' })}
                </dt>
                <dd class="mt-1 font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{sourceTotal.toLocaleString()}</dd>
            </div>
            <div class="min-w-0">
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.standing_busiest_hour', { default: 'Busiest hour' })}</dt>
                <dd class="mt-1 font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{busiestHour ? hourLabel(busiestHour.hour) : '—'}</dd>
                {#if busiestHour}<dd class="text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.standing_busiest_hour_count', { values: { count: busiestHour.count.toLocaleString() }, default: '{count} detections on camera' })}</dd>{/if}
            </div>
            <div class="min-w-0" data-leaderboard-corroboration>
                <dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{audioKnown ? $_('leaderboard.standing_corroborated', { default: 'Heard or confirmed' }) : $_('leaderboard.standing_confirmed', { default: 'Confirmed by you' })}</dt>
                {#if evidenceKnown}
                    <dd class="mt-1 font-display text-2xl font-bold tabular-nums text-slate-900 dark:text-white">{corroboratedCount}<span class="text-base font-semibold text-slate-400"> / {leaderboardRows.length}</span></dd>
                    <dd class="text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.standing_corroborated_hint', { default: 'species, the rest are the camera alone' })}</dd>
                {:else}
                    <dd class="mt-1 font-display text-2xl font-bold text-slate-400">—</dd>
                    <dd class="text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.standing_corroborated_unknown', { default: 'Counted for the day, week and month' })}</dd>
                {/if}
            </div>
            <div class="min-w-0">
                <dt class="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
                    <svg class="h-3.5 w-3.5 text-success-600 dark:text-success-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m4 17 5-5 4 4 7-9m-5 0h5v5" /></svg>
                    {$_('leaderboard.rising')}
                </dt>
                {#if topByTrend}
                    <dd class="mt-1 truncate text-base font-semibold text-slate-900 dark:text-white">{topByTrend.displayName}</dd>
                    <dd class="text-xs tabular-nums text-success-700 dark:text-success-400">{trendForMode(topByTrend, sourceMode)}</dd>
                {:else}
                    <dd class="mt-1 text-base font-semibold text-slate-400">—</dd>
                    <dd class="text-xs text-slate-500 dark:text-slate-400">{span === 'all' ? $_('leaderboard.rising_all_time', { default: 'No earlier window for all time' }) : !trendAvailable ? $_('leaderboard.rising_no_history', { default: 'Needs a full earlier window' }) : $_('leaderboard.rising_none', { default: 'Nothing up on the window before' })}</dd>
                {/if}
            </div>
            <div class="min-w-0">
                <dt class="flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
                    <svg class="h-3.5 w-3.5 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path stroke-linecap="round" d="M12 8v4l3 2" /></svg>
                    {$_('leaderboard.most_recent')}
                </dt>
                {#if mostRecent}
                    <dd class="mt-1 truncate text-base font-semibold text-slate-900 dark:text-white">{mostRecent.displayName}</dd>
                    <dd class="text-xs text-slate-500 dark:text-slate-400" title={formatDate(activityTimestampForMode(mostRecent, sourceMode))}>{formatRelative(activityTimestampForMode(mostRecent, sourceMode))}</dd>
                {:else}
                    <dd class="mt-1 text-base font-semibold text-slate-400">—</dd>
                {/if}
            </div>
        </dl>
        <section class="space-y-5" data-leaderboard-rankings>
            <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div class="flex items-center gap-3">
                    <svg data-leaderboard-section-icon aria-hidden="true" class="h-8 w-8 rounded-xl border border-brand-200 bg-brand-50 p-1.5 text-brand-700 dark:border-brand-800 dark:bg-brand-950/40 dark:text-brand-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                        <path stroke-linecap="round" d="M6 4v16M18 4v16" /><path stroke-linecap="round" stroke-linejoin="round" d="m9 8 3-3 3 3m-6 8 3 3 3-3" />
                    </svg>
                    <div>
                        <h3 class="text-xl font-bold text-slate-950 dark:text-white">{$_('leaderboard.full_rankings', { default: 'Full rankings' })}</h3>
                        <p class="text-sm text-slate-500 dark:text-slate-400">{spanLabel()} · {span === 'all' ? $_('leaderboard.all_species') : formatRangeCompact(leaderboardWindow?.start, leaderboardWindow?.end)}</p>
                    </div>
                </div>
            </div>
            {#if span !== 'all' && !trendAvailable && trendHistoryStart}
                <p class="text-sm text-slate-500 dark:text-slate-400" data-leaderboard-trend-note>
                    {$_('leaderboard.trend_needs_history', { values: { date: formatShortDate(trendHistoryStart) }, default: 'No trend yet. Records start {date}, so there is no complete earlier window to compare with.' })}
                </p>
            {/if}
            {#if unlikelyRows.length > 0 && nearbyCheck}
                <div class="flex items-start gap-3 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-100" role="note" data-leaderboard-unlikely-note>
                    <span class="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true"></span>
                    <p>
                        {$_('leaderboard.unlikely_note', {
                            values: { count: unlikelyRows.length, radius: nearbyCheck.radiusKm, days: nearbyCheck.daysBack },
                            default: '{count} species have no call, no confirmation and no eBird report within {radius} km in the last {days} days. They are probably misidentifications: open one to confirm or correct it.'
                        })}
                    </p>
                </div>
            {/if}

            {#key `${sourceMode}-${span}`}
                <div class="divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700 md:hidden" data-leaderboard-mobile-rankings>
                {#each leaderboardRows as item, index (`mobile-${item.species}|${item.audio_only}|${index}`)}
                    {@const evidence = evidenceOf(item)}
                    <button
                        type="button"
                        onclick={() => selectedSpecies = item.species}
                        class="group flex min-h-20 w-full items-center gap-3 py-3 text-left transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:hover:bg-slate-800/40 {unlikelyHere(item) ? 'bg-gradient-to-r from-amber-50 to-transparent dark:from-amber-500/10' : ''}"
                        title={item.species === "Unknown Bird" ? $_('leaderboard.unidentified_desc') : ""}
                        aria-label={$_('leaderboard.view_species', { values: { species: item.displayName } })}
                    >
                        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold tabular-nums {index < 3 ? 'bg-brand-100 text-brand-800 dark:bg-brand-900/50 dark:text-brand-200' : 'text-slate-500 dark:text-slate-400'}" aria-label={`${$_('leaderboard.rank')} ${index + 1}`}>{index + 1}</span>
                        <span data-leaderboard-species-portrait class="h-12 w-12 shrink-0 overflow-hidden rounded-full border-2 border-white bg-slate-100 shadow-sm ring-1 ring-brand-200 dark:border-slate-800 dark:bg-slate-800 dark:ring-brand-800">
                            {#if getCachedSpeciesInfo(item.species)?.thumbnail_url}
                                <img src={getCachedSpeciesInfo(item.species)?.thumbnail_url ?? undefined} alt="" class="h-full w-full object-cover" loading="lazy" />
                            {:else}
                                <span class="flex h-full w-full items-center justify-center text-slate-400"><svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg></span>
                            {/if}
                        </span>
                        <span class="min-w-0 flex-1">
                            <span class="flex items-center gap-2">
                                <span class="truncate font-semibold text-slate-900 dark:text-white">{item.displayName}</span>
                            </span>
                            {#if item.subName}<span class="mt-0.5 block truncate text-xs italic text-slate-500 dark:text-slate-400">{item.subName}</span>{/if}
                            {#if unlikelyHere(item) && nearbyCheck}{@render unlikelyReason(nearbyCheck.radiusKm)}{/if}
                            <span class="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-slate-500 dark:text-slate-400">
                                {#if evidence !== 'unknown'}<span class="inline-flex items-center gap-1 font-semibold {evidence === 'camera_only' || evidence === 'unconfirmed' ? '' : 'text-slate-700 dark:text-slate-200'}" data-leaderboard-evidence={evidence}>{@render evidenceGlyph(evidence)}{evidenceLabel(evidence)}</span><span aria-hidden="true">·</span>{/if}
                                <span title={formatDate(activityTimestampForMode(item, sourceMode))}>{formatRelative(activityTimestampForMode(item, sourceMode))}</span>
                            </span>
                        </span>
                        <span class="shrink-0 text-right">
                            <span class="block text-base font-bold tabular-nums text-slate-900 dark:text-white">{countForMode(item, sourceMode).toLocaleString()}</span>
                            {#if trendAvailable}<span class="block text-xs font-semibold tabular-nums {trendTone(item)}">{trendGlyph(item)} {trendForMode(item, sourceMode)}</span>{/if}
                        </span>
                        <svg class="h-4 w-4 shrink-0 text-slate-400 transition group-hover:translate-x-0.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                    </button>
                {/each}
                </div>

                <div class="hidden overflow-hidden border-y border-slate-200 dark:border-slate-700 md:block" data-leaderboard-desktop-rankings>
                <table class="w-full table-fixed text-left text-sm" data-testid="leaderboard-table">
                    <thead class="border-b border-slate-200 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                        <tr>
                            <th scope="col" class="w-14 px-3 py-3 text-center">{$_('leaderboard.rank')}</th>
                            <th scope="col" class="w-[32%] px-3 py-3">{$_('leaderboard.species')}</th>
                            <th scope="col" class="px-3 py-3 text-right">{countsAreVisits ? $_('leaderboard.metric_visits', { default: 'Visits' }) : $_('leaderboard.metric_detections', { default: 'Detections' })}</th>
                            {#if birdnetEnabled}<th scope="col" class="px-3 py-3 text-right">{$_('leaderboard.source_heard', { default: 'Heard' })}</th>{/if}
                            <th scope="col" class="hidden w-52 px-3 py-3 lg:table-cell" title={$_('leaderboard.evidence_hint', { default: 'Camera only: BirdNET did not hear this species in the same window and no detection of it has been confirmed. Worth a look before you trust it.' })}>{$_('leaderboard.evidence', { default: 'Evidence' })}</th>
                            {#if trendAvailable}<th scope="col" class="hidden px-3 py-3 text-right lg:table-cell">{$_('leaderboard.trend')}</th>{/if}
                            {#if showCameraColumn}<th scope="col" class="hidden px-3 py-3 text-right xl:table-cell">{$_('leaderboard.cameras')}</th>{/if}
                            <th scope="col" class="hidden px-3 py-3 text-right xl:table-cell">{$_('leaderboard.avg_confidence')}</th>
                            <th scope="col" class="hidden w-32 px-3 py-3 text-right lg:table-cell">{sourceMode === 'heard' ? $_('audio.card.last_heard') : sourceMode === 'both' ? $_('leaderboard.most_recent') : $_('leaderboard.last_seen')}</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                        {#each leaderboardRows as item, index (`desktop-${item.species}|${item.audio_only}|${index}`)}
                            {@const rowCountPct = maxCount > 0 ? Math.round((item.count / maxCount) * 100) : 0}
                            {@const rowHeardPct = maxHeard > 0 ? Math.round((item.heard_count / maxHeard) * 100) : 0}
                            {@const evidence = evidenceOf(item)}
                            <tr class="transition hover:bg-slate-50/80 dark:hover:bg-slate-800/35 {unlikelyHere(item) ? 'bg-gradient-to-r from-amber-50 to-transparent dark:from-amber-500/10' : ''}" data-leaderboard-unlikely={unlikelyHere(item) ? 'true' : undefined}>
                                <td class="px-3 py-3 text-center"><span class="inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold tabular-nums {index < 3 ? 'bg-brand-100 text-brand-800 dark:bg-brand-900/50 dark:text-brand-200' : 'text-slate-500 dark:text-slate-400'}" aria-label={`${$_('leaderboard.rank')} ${index + 1}`}>{index + 1}</span></td>
                                <td class="px-3 py-3">
                                    <button type="button" onclick={() => selectedSpecies = item.species} class="group flex min-h-11 max-w-full items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500" aria-label={$_('leaderboard.view_species', { values: { species: item.displayName } })}>
                                        <span data-leaderboard-species-portrait class="h-10 w-10 shrink-0 overflow-hidden rounded-full border-2 border-white bg-slate-100 shadow-sm ring-1 ring-brand-200 dark:border-slate-800 dark:bg-slate-800 dark:ring-brand-800">
                                            {#if getCachedSpeciesInfo(item.species)?.thumbnail_url}<img src={getCachedSpeciesInfo(item.species)?.thumbnail_url ?? undefined} alt="" class="h-full w-full object-cover" loading="lazy" />{:else}<span class="flex h-full w-full items-center justify-center text-slate-400"><svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M20.24 4.24a6 6 0 0 0-8.49 0L5 11v9h9l6.24-6.24a6 6 0 0 0 0-8.49ZM16 8 2 22M17.5 15H9" /></svg></span>{/if}
                                        </span>
                                        <span class="min-w-0"><span class="block truncate font-semibold text-slate-900 group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">{item.displayName}</span>{#if item.subName}<span class="block truncate text-xs italic text-slate-500 dark:text-slate-400">{item.subName}</span>{/if}</span>
                                    </button>
                                </td>
                                <td class="px-3 py-3 text-right">{#if item.audio_only}<span class="text-slate-400">—</span>{:else}<span class="font-semibold tabular-nums text-slate-700 dark:text-slate-200">{item.count.toLocaleString()}</span><span class="ml-auto mt-1 block h-1 w-14 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"><span class="block h-full rounded-full bg-brand-500/70" style="width: {rowCountPct}%"></span></span>{/if}</td>
                                {#if birdnetEnabled}<td class="px-3 py-3 text-right">{#if audioLoadState === 'ready'}<span class="font-semibold tabular-nums text-slate-700 dark:text-slate-200">{item.heard_count.toLocaleString()}</span><span class="ml-auto mt-1 block h-1 w-14 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"><span class="block h-full rounded-full bg-slate-400/80 dark:bg-slate-400/70" style="width: {rowHeardPct}%"></span></span>{:else}<span class="text-slate-400" title={$_('common.unavailable')}>—</span>{/if}</td>{/if}
                                <td class="hidden px-3 py-3 lg:table-cell">{#if evidence === 'unknown'}<span class="text-slate-400">—</span>{:else}<span class="inline-flex items-center gap-1.5 text-xs font-semibold {evidence === 'camera_only' || evidence === 'unconfirmed' ? 'text-slate-500 dark:text-slate-400' : 'text-slate-700 dark:text-slate-200'}" data-leaderboard-evidence={evidence}>{@render evidenceGlyph(evidence)}{evidenceLabel(evidence)}</span>{/if}{#if unlikelyHere(item) && nearbyCheck}{@render unlikelyReason(nearbyCheck.radiusKm)}{/if}</td>
                                {#if trendAvailable}<td class="hidden px-3 py-3 text-right font-semibold tabular-nums lg:table-cell {trendTone(item)}"><span aria-hidden="true" class="mr-0.5 text-xs">{trendGlyph(item)}</span>{trendForMode(item, sourceMode)}</td>{/if}
                                {#if showCameraColumn}<td class="hidden px-3 py-3 text-right tabular-nums text-slate-600 dark:text-slate-300 xl:table-cell">{(item.camera_count ?? 0).toLocaleString()}</td>{/if}
                                <td class="hidden px-3 py-3 text-right tabular-nums text-slate-600 dark:text-slate-300 xl:table-cell">{item.avg_confidence != null ? `${Math.round(item.avg_confidence * 100)}%` : '—'}</td>
                                <td class="hidden whitespace-nowrap px-3 py-3 text-right text-slate-500 dark:text-slate-400 lg:table-cell" title={formatDate(activityTimestampForMode(item, sourceMode))}>{formatRelative(activityTimestampForMode(item, sourceMode))}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
                </div>
            {/key}
        </section>


        <section class="space-y-6 border-t border-slate-200 pt-8 dark:border-slate-700" data-leaderboard-analytics>
            <div class="flex items-center gap-3">
                <svg data-leaderboard-section-icon aria-hidden="true" class="h-8 w-8 rounded-xl border border-brand-200 bg-brand-50 p-1.5 text-brand-700 dark:border-brand-800 dark:bg-brand-950/40 dark:text-brand-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" d="M4 19V9m5 10V5m5 14v-7m5 7V3" /></svg>
                <div><h3 class="text-xl font-bold text-slate-950 dark:text-white">{$_('leaderboard.analytics_section', { default: 'Analytics' })}</h3><p class="text-sm text-slate-500 dark:text-slate-400">{spanLabel()} · {formatRangeCompact(timeline?.window_start, timeline?.window_end)}</p></div>
            </div>

        <div class="border-y border-slate-200 py-6 dark:border-slate-700 md:py-8">
            <div class="relative flex flex-col flex-1">
                <div class="flex flex-col gap-4">
                    <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                        <div>
                            <h4 class="text-lg font-bold text-slate-900 dark:text-white md:text-xl">{$_('leaderboard.detections_over_time')}</h4>
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                {spanLabel()} · {formatRangeCompact(timeline?.window_start, timeline?.window_end)} · {bucketLabel(timeline?.bucket)} · {(timeline?.total_count ?? 0).toLocaleString()} {metricLabel().toLowerCase()}{#if unidentifiedCount > 0 && !includeUnknownBird}, {$_('leaderboard.includes_unidentified', { values: { count: unidentifiedCount.toLocaleString() }, default: 'including {count} not identified to species' })}{/if}
                            </p>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                            {#if canUseLeaderboardAnalysis}
                                <button
                                    type="button"
                                    class="inline-flex min-h-11 items-center rounded-xl border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-700 transition hover:bg-brand-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300 dark:hover:bg-brand-950/50"
                                    disabled={!timeline?.points?.length || leaderboardAnalysisLoading}
                                    onclick={() => runLeaderboardAnalysis(!!leaderboardAnalysis)}
                                >
                                    {leaderboardAnalysisLoading
                                        ? $_('leaderboard.ai_analyzing', { default: 'Analyzing…' })
                                        : leaderboardAnalysis
                                            ? $_('leaderboard.ai_rerun', { default: 'Rerun analysis' })
                                            : $_('leaderboard.ai_analyze', { default: 'Analyze chart' })}
                                </button>
                            {/if}
                        </div>
                    </div>
                </div>

                <!-- A fixed box, not a flex-grown one: Chart.js sizes the canvas to its parent, so a parent
                     that grows with its content lets the chart balloon to half the page width. -->
                <div class="mt-6 w-full shrink-0" style="height: {isStackedChart() ? 380 : 260}px">
                    {#if timeline?.points?.length}
                        {#key `${span}-${timeline.total_count}-${timeline.bucket}-${showPrecip}-${isDark()}-${themeStore.colorTheme}`}
                            <div class="flex h-full min-w-0 flex-col">
                                <div class="relative min-h-0 flex-1"><canvas use:chartjs={chartOptions()} bind:this={chartEl} aria-label="{$_('leaderboard.detections_over_time')}: {metricLabel()}" class="w-full"></canvas></div>
                            </div>
                        {/key}
                    {:else}
                        <div class="h-full w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                    {/if}
                </div>
                {#each weatherPanels() as panel (panel.key)}
                    <div class="mt-3" data-leaderboard-weather-panel={panel.key}>
                        <p class="mb-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{panel.title}</p>
                        <div class="h-24 w-full">
                            {#key `${span}-${timeline?.total_count}-${timeline?.bucket}-${isDark()}-${panel.key}`}
                                <canvas use:chartjs={panel.config} aria-label={panel.title}></canvas>
                            {/key}
                        </div>
                    </div>
                {/each}
                {#if timeline?.points?.length && timelineLegend().length > 1}
                    <div class="mt-3 flex flex-wrap gap-1" role="group" aria-label={$_('leaderboard.chart_legend', { default: 'Series in this chart' })} data-leaderboard-timeline-legend>
                        {#each timelineLegend() as entry (entry.label)}
                            {@const hidden = hiddenTimelineSeries.includes(entry.label)}
                            <button type="button" class="btn btn-ghost min-h-11 gap-1.5 px-2 text-xs focus-visible:ring-2 focus-visible:ring-brand-500 {hidden ? 'opacity-45 line-through' : ''}"
                                aria-pressed={!hidden} aria-label="{hidden ? $_('common.show') : $_('common.hide')} {entry.label}" onclick={() => toggleTimelineSeries(entry.label)}>
                                {#if entry.line}
                                    <span class="inline-block h-0.5 w-4 rounded-full {entry.dashed ? 'border-t-2 border-dashed bg-transparent' : ''}" style={entry.dashed ? `border-color: ${entry.color}` : `background-color: ${entry.color}`}></span>
                                {:else}
                                    <span class="h-2.5 w-2.5 rounded-sm" style="background-color: {entry.color}"></span>
                                {/if}
                                {entry.label}
                            </button>
                        {/each}
                    </div>
                {/if}

                <p class="mt-3 text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {$_('leaderboard.total', { default: 'Total' })}: {timeline?.total_count?.toLocaleString() || '0'}
                    · {$_('leaderboard.metric_peak', { default: 'Peak' })}: {formatMetricValue(metricPeak())}
                    · {$_('leaderboard.metric_avg', { default: 'Avg' })}: {formatMetricValue(metricAvg())}
                </p>
                {#if canUseLeaderboardAnalysis && (leaderboardAnalysisLoading || leaderboardAnalysisError || leaderboardAnalysis)}
                    <div class="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:bg-slate-800/40 dark:text-slate-300">
                        <div class="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                            <span>{$_('leaderboard.ai_summary', { default: 'AI insight' })}</span>
                            {#if leaderboardAnalysisTimestamp}
                                <span class="font-semibold normal-case tracking-normal">{formatDateTime(leaderboardAnalysisTimestamp)}</span>
                            {/if}
                        </div>
                        {#if leaderboardAnalysisLoading}
                            <p class="mt-2 text-xs text-slate-500">{$_('leaderboard.ai_analyzing', { default: 'Analyzing…' })}</p>
                        {:else if leaderboardAnalysisError}
                            <p class="mt-2 text-xs text-rose-500">{leaderboardAnalysisError}</p>
                        {:else if leaderboardAnalysis}
                            <div class="mt-2 space-y-2">
                                {#each leaderboardAiBlocks() as block}
                                    {#if block.type === 'heading'}
                                        <p class="text-xs font-semibold text-accent-600 dark:text-accent-300">{block.text}</p>
                                    {:else}
                                        <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">{block.text}</p>
                                    {/if}
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/if}
                <!-- Weather overlays -->
                <details class="mt-3 group/weather">
                    <summary class="inline-flex min-h-11 cursor-pointer list-none select-none items-center gap-2 rounded-xl px-2 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800/40 [&::-webkit-details-marker]:hidden">
                        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M6 9a4 4 0 1 1 7.5-1.8A2.8 2.8 0 1 1 14 13H6.5"></path>
                            <path d="M7 14.5v2M10 14.5v2M13 14.5v2"></path>
                        </svg>
                        {$_('leaderboard.weather_overlays', { default: 'Weather overlays' })}
                        <svg class="h-3 w-3 transition-transform group-open/weather:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path d="M6 8l4 4 4-4"></path>
                        </svg>
                        {#if timeline?.sunrise_range}
                            <span class="font-semibold normal-case tracking-normal text-amber-600 dark:text-amber-400">{$_('leaderboard.sunrise')} {timeline.sunrise_range}</span>
                        {/if}
                        {#if timeline?.sunset_range}
                            <span class="font-semibold normal-case tracking-normal text-orange-600 dark:text-orange-400">{$_('leaderboard.sunset')} {timeline.sunset_range}</span>
                        {/if}
                    </summary>
                    <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
                        <button
                            type="button"
                            aria-pressed={showTemperature}
                            onclick={() => showTemperature = !showTemperature}
                            disabled={!hasWeather()}
                            class="inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-45
                                {showTemperature ? 'border-brand-300 dark:border-brand-600 bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300' : 'border-slate-200/70 dark:border-slate-700/60 text-slate-500 dark:text-slate-400'}"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M10 4a2 2 0 0 0-4 0v6.4a3.5 3.5 0 1 0 4 0V4z"></path>
                                <path d="M8 9.5V4"></path>
                            </svg>
                            {$_('leaderboard.temperature')}
                        </button>
                        <button
                            type="button"
                            aria-pressed={showWind}
                            onclick={() => showWind = !showWind}
                            disabled={!hasWeather()}
                            class="inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-45
                                {showWind ? 'border-brand-300 dark:border-brand-600 bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300' : 'border-slate-200/70 dark:border-slate-700/60 text-slate-500 dark:text-slate-400'}"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M3 8h9a2 2 0 1 0-2-2"></path>
                                <path d="M3 12h12a2 2 0 1 1-2 2"></path>
                            </svg>
                            {$_('leaderboard.wind_avg')}
                        </button>
                        <button
                            type="button"
                            aria-pressed={showPrecip}
                            onclick={() => showPrecip = !showPrecip}
                            disabled={!hasWeather()}
                            class="inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-45
                                {showPrecip ? 'border-blue-300 dark:border-blue-600 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' : 'border-slate-200/70 dark:border-slate-700/60 text-slate-500 dark:text-slate-400'}"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M6 9a4 4 0 1 1 7.5-1.8A2.8 2.8 0 1 1 14 13H6.5"></path>
                                <path d="M7 14.5v2M10 14.5v2M13 14.5v2"></path>
                            </svg>
                            {$_('leaderboard.show_precip', { default: 'Precipitation' })}
                        </button>
                        {#if showPrecip && hasWeather()}
                            <span class="inline-flex items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-400">
                                <span class="h-2 w-2 rounded-sm bg-sky-300/45 border border-sky-300/60"></span>{$_('leaderboard.band_low', { default: 'Low' })}
                                <span class="h-2 w-2 rounded-sm bg-sky-300/65 border border-sky-300/75"></span>{$_('leaderboard.band_medium', { default: 'Med' })}
                                <span class="h-2 w-2 rounded-sm bg-sky-300/85 border border-sky-300/90"></span>{$_('leaderboard.band_high', { default: 'High' })}
                            </span>
                        {/if}
                        {#if !hasWeather()}
                            <span class="text-xs text-slate-500 dark:text-slate-400">
                                {weatherOverlayEligible()
                                    ? $_('leaderboard.weather_overlay_no_data', { default: 'No weather data in this range yet.' })
                                    : $_('leaderboard.weather_overlay_range_limited', { default: 'Weather overlays available on Day/Week/Month ranges.' })}
                            </span>
                        {/if}
                    </div>
                </details>
            </div>
        </div>

        <div class="grid grid-cols-1 divide-y divide-slate-200 border-b border-slate-200 dark:divide-slate-700 dark:border-slate-700 xl:grid-cols-5 xl:divide-x xl:divide-y-0">
            <div class="py-6 xl:col-span-3 xl:pr-8">
                <div class="relative">
                    <div class="flex items-start justify-between gap-3">
                        <div class="flex items-start gap-2.5">
                            <div class="h-8 w-8 rounded-xl border border-brand-200/80 dark:border-brand-700/60 bg-brand-100/80 dark:bg-brand-900/30 flex items-center justify-center text-brand-700 dark:text-brand-300">
                                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                    <rect x="3" y="4" width="14" height="12" rx="2"></rect>
                                    <path d="M3 9h14M8 4v12M13 4v12"></path>
                                </svg>
                            </div>
                            <div>
                                <p class="text-xs font-semibold text-brand-600 dark:text-brand-300">
                                    {$_('leaderboard.activity_heatmap_title', { default: 'Activity Heatmap' })}
                                </p>
                                <h4 class="mt-1 text-lg font-bold text-slate-900 dark:text-white md:text-xl">
                                    {$_('leaderboard.activity_heatmap_subtitle', { default: 'Hour x weekday activity' })}
                                </h4>
                            </div>
                        </div>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-300">
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <rect x="3" y="4" width="14" height="13" rx="2"></rect>
                                <path d="M3 8h14"></path>
                            </svg>
                            {formatRangeCompact(activityHeatmap?.window_start, activityHeatmap?.window_end)}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M4 14h12"></path>
                                <path d="M7 14V9M10 14V6M13 14v-3"></path>
                            </svg>
                            {$_('leaderboard.total', { default: 'Total' })}: {formatMetricValue(shownHeatmap?.total_count ?? 0)}
                        </span>
                    </div>

                    {#if heatmapSpeciesOptions.length > 1}
                        <div class="-mx-1 mt-3 flex gap-1 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible" role="group" aria-label={$_('leaderboard.heatmap_species_picker', { default: 'Show the activity of' })} data-leaderboard-heatmap-species>
                            <button type="button" class="btn btn-ghost min-h-11 shrink-0 whitespace-nowrap px-2.5 text-xs {heatmapSpecies === null ? 'bg-slate-100 font-semibold text-slate-900 dark:bg-slate-800 dark:text-white' : ''}" aria-pressed={heatmapSpecies === null} onclick={() => (heatmapChoice = null)}>
                                {$_('leaderboard.heatmap_all_species', { default: 'All species' })}
                            </button>
                            {#each heatmapSpeciesOptions as option (option.species)}
                                <button type="button" class="btn btn-ghost min-h-11 shrink-0 whitespace-nowrap px-2.5 text-xs {heatmapSpecies === option.species ? 'bg-slate-100 font-semibold text-slate-900 dark:bg-slate-800 dark:text-white' : ''}" aria-pressed={heatmapSpecies === option.species} onclick={() => (heatmapChoice = option.species)}>
                                    {option.displayName}
                                </button>
                            {/each}
                        </div>
                    {/if}

                    <div class="mt-4 min-h-[260px]" aria-busy={speciesHeatmapLoading}>
                        {#if shownHeatmap && (shownHeatmap.total_count ?? 0) > 0}
                            <div class="transition-opacity {speciesHeatmapLoading ? 'opacity-50' : ''}">
                                <ActivityHeatmap
                                    cells={shownHeatmap.cells}
                                    maxCellCount={shownHeatmap.max_cell_count}
                                    dark={isDark()}
                                    dayLabel={weekdayLabel}
                                    subject={heatmapSubject}
                                />
                            </div>
                        {:else if heatmapSpecies && speciesHeatmapFailed}
                            <div class="h-[260px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center px-6 text-center text-sm text-slate-500 dark:text-slate-400" role="status">
                                {$_('leaderboard.heatmap_species_failed', { default: 'That species\u2019 activity could not be loaded. Choose it again to retry.' })}
                            </div>
                        {:else if heatmapSpecies && shownHeatmap}
                            <div class="h-[260px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center px-6 text-center text-sm text-slate-500 dark:text-slate-400">
                                {$_('leaderboard.heatmap_species_empty', { values: { species: heatmapSubject ?? '' }, default: 'No {species} detections in this window.' })}
                            </div>
                        {:else if activityHeatmap && !heatmapSpecies}
                            <div class="h-[260px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                                {$_('leaderboard.no_activity_data', { default: 'No activity captured in this window yet.' })}
                            </div>
                        {:else}
                            <div class="h-[260px] w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                        {/if}
                    </div>
                </div>
            </div>
            <div class="py-6 xl:col-span-2 xl:pl-8">
                <div class="relative">
                    <div class="flex items-start justify-between gap-3">
                        <div class="flex items-start gap-2.5">
                            <div class="h-8 w-8 rounded-xl border border-brand-200/80 dark:border-brand-700/60 bg-brand-100/80 dark:bg-brand-900/30 flex items-center justify-center text-brand-700 dark:text-brand-300">
                                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                    <circle cx="10" cy="10" r="7"></circle>
                                    <circle cx="10" cy="10" r="3"></circle>
                                    <path d="M10 3v4M10 13v4M3 10h4M13 10h4" stroke-width="1.4"></path>
                                </svg>
                            </div>
                            <div>
                                <p class="text-xs font-semibold text-brand-600 dark:text-brand-300">
                                    {$_('leaderboard.detection_breakdown_title', { default: 'Detection Breakdown' })}
                                </p>
                                <h4 class="mt-1 text-lg font-bold text-slate-900 dark:text-white md:text-xl">
                                    {$_('leaderboard.detection_breakdown_subtitle', { default: 'Species composition' })}
                                </h4>
                            </div>
                        </div>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-500 dark:text-slate-300">
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M4 10h12M4 6h12M4 14h7"></path>
                            </svg>
                            {selectedCountLabel()}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M10 4v8l4 2"></path><circle cx="10" cy="10" r="7"></circle>
                            </svg>
                            {totalCount.toLocaleString()} {countsAreVisits ? $_('leaderboard.showcase_visits', { default: 'visits' }) : $_('leaderboard.showcase_detections', { default: 'detections' })}
                        </span>
                    </div>

                    <div class="mt-4 min-h-[260px]">
                        {#if donutHasData()}
                            {#key `${span}-${donutSeries().series.join(',')}-${isDark()}-${themeStore.colorTheme}`}
                                <div class="relative h-[210px] w-full"><canvas use:chartjs={donutChartOptions()} bind:this={donutChartEl} aria-label={$_('leaderboard.detection_breakdown_subtitle', { default: 'Species composition' })}></canvas></div>
                                <div class="mt-2 flex flex-wrap justify-center gap-x-1" role="group" aria-label={$_('leaderboard.detection_breakdown_subtitle', { default: 'Species composition' })}>
                                    {#each donutSeries().labels as label, index}
                                        <button type="button" class="btn btn-ghost min-h-11 gap-1.5 px-2 text-xs focus-visible:ring-2 focus-visible:ring-brand-500 {hiddenDonutSpecies.includes(index) ? 'opacity-45 line-through' : ''}"
                                            aria-pressed={!hiddenDonutSpecies.includes(index)} aria-label="{hiddenDonutSpecies.includes(index) ? $_('common.show') : $_('common.hide')} {label}" onclick={() => toggleDonutSlice(index)}>
                                            <span class="h-2.5 w-2.5 rounded-sm" style="background-color: {donutColor(index)}"></span>{label}
                                        </button>
                                    {/each}
                                </div>
                            {/key}
                        {:else}
                            <div class="h-[260px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                                {$_('leaderboard.no_compare_data', { default: 'Not enough data for comparison yet.' })}
                            </div>
                        {/if}
                    </div>
                </div>
            </div>

        </div>

        </section>
    {/if}
</div>

<!-- Species Detail Modal -->
{#if selectedSpecies}
    <SpeciesDetailModal
        speciesName={selectedSpecies}
        onclose={() => selectedSpecies = null}
    />
{/if}
