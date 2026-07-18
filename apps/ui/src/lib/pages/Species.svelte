<script lang="ts">
    import { tick } from 'svelte';
    import {
        analyzeLeaderboardGraph,
        fetchDetectionsActivityHeatmapSpan,
        fetchDetectionsTimelineSpan,
        fetchLeaderboardAnalysis,
        fetchLeaderboardSpecies,
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
    import { chart } from '../actions/apexchart';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { defaultLeaderboardChartPreferences } from '../leaderboard/chart-defaults';
    import { buildLeaderboardAnalysisPromptConfig } from '../leaderboard/analysis-config';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
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
    import { _, locale } from 'svelte-i18n';
    import { refreshCoordinator } from '../stores/refresh_coordinator.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { StaleTracker } from '../utils/stale_tracker';
    import type { ApexOptions } from 'apexcharts';
    import type { TemperatureUnit } from '../utils/temperature';

    type LeaderboardRow = {
        species: string;
        scientific_name?: string | null;
        common_name?: string | null;
        taxa_id?: number | null;
        count: number;
        prev_count?: number | null;
        delta?: number | null;
        percent?: number | null;
        first_seen?: string | null;
        last_seen?: string | null;
        avg_confidence?: number | null;
        camera_count?: number | null;
    };
    type TrendMode = 'off' | 'smooth' | 'both';
    type SourceMode = 'seen' | 'heard' | 'both';

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
    let sourceMode = $state<SourceMode>('seen');
    let loading = $state(true);
    let error = $state<string | null>(null);
    let span = $state<LeaderboardSpan>('month');
    let includeUnknownBird = $state(false);
    let selectedSpecies = $state<string | null>(null);
    let timeline = $state<DetectionsTimelineSpanResponse | null>(null);
    let activityHeatmap = $state<DetectionsActivityHeatmapResponse | null>(null);
    let speciesInfoCache = $state<Record<string, SpeciesInfo>>({});
    let speciesInfoPending = $state<Record<string, boolean>>({});
    let chartEl = $state<HTMLDivElement | null>(null);
    let leaderboardAnalysis = $state<string | null>(null);
    let leaderboardAnalysisTimestamp = $state<string | null>(null);
    let leaderboardAnalysisLoading = $state(false);
    let leaderboardAnalysisError = $state<string | null>(null);
    let leaderboardConfigKey = $state<string | null>(null);
    let leaderboardAnalysisSubtitle = $state<string | null>(null);
    let llmReady = $state(false);
    let showTemperature = $state(false);
    let showWind = $state(false);
    let showPrecip = $state(false);
    let chartViewMode = $state<'auto' | 'line' | 'bar'>('bar');
    let trendMode = $state<TrendMode>('off');
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
        settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false
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
    let totalDetections = $derived(leaderboardSpecies().reduce((sum, s) => sum + (s.count || 0), 0));
    let maxCount = $derived(Math.max(...leaderboardSpecies().map(s => s.count || 0), 1));

    let topByCount = $derived(sortedSpecies()[0]);
    let topByTrend = $derived(
        span === 'all'
            ? null
            : [...processedSpecies()].sort((a, b) => (b.delta || 0) - (a.delta || 0))[0]
    );
    let mostRecent = $derived([...processedSpecies()].sort((a, b) => {
        const aTime = a.last_seen ? new Date(a.last_seen).getTime() : 0;
        const bTime = b.last_seen ? new Date(b.last_seen).getTime() : 0;
        return bTime - aTime;
    })[0]);

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
    // follows the active source toggle. Charts/stats/podium still use the visual-only
    // derived lists above, so they are unaffected.
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

    let maxHeard = $derived(Math.max(...leaderboardTableRows(sourceMode).map((r) => r.heard_count || 0), 1));

    const leaderboardStale = new StaleTracker(120_000); // 2 minutes

    $effect(() => {
        const _deps = [span];
        void loadLeaderboard();
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
            prev_count: null,
            delta: null,
            percent: null
        }));
    }

    function mapWindowSpecies(resp: Awaited<ReturnType<typeof fetchLeaderboardSpecies>>): LeaderboardRow[] {
        return (resp.species || []).map((s) => ({
            species: s.species,
            scientific_name: s.scientific_name ?? null,
            common_name: s.common_name ?? null,
            taxa_id: s.taxa_id ?? null,
            count: s.window_count ?? 0,
            prev_count: s.window_prev_count ?? 0,
            delta: s.window_delta ?? 0,
            percent: s.window_percent ?? 0,
            first_seen: s.window_first_seen ?? null,
            last_seen: s.window_last_seen ?? null,
            avg_confidence: s.window_avg_confidence ?? null,
            camera_count: s.window_camera_count ?? null
        }));
    }

    function selectCompareSpecies(rows: LeaderboardRow[]): string[] {
        const source = includeUnknownBird
            ? rows
            : rows.filter((item) => item.species !== "Unknown Bird");
        return [...source]
            .sort((a, b) => (b.count || 0) - (a.count || 0))
            .map((item) => item.scientific_name || item.species)
            .filter(Boolean)
            .slice(0, 7);
    }

    async function loadLeaderboard() {
        loading = true;
        error = null;
        // Fetch species and timeline independently so a chart/weather failure
        // doesn't make the leaderboard table disappear.
        try {
            species = span === 'all'
                ? await fetchSpecies().then(mapAllTimeSpecies)
                : await fetchLeaderboardSpecies(span).then(mapWindowSpecies);
        } catch (e) {
            error = $_('leaderboard.load_failed');
            species = [];
            if (isTransientRequestError(e)) {
                logger.warn('Leaderboard species fetch failed (transient)', {
                    message: getErrorMessage(e)
                });
            } else {
                logger.error('Failed to load leaderboard species', e);
            }
        }

        const compareSpecies = selectCompareSpecies(species);
        const [timelineResult, heatmapResult, audioResult] = await Promise.allSettled([
            fetchDetectionsTimelineSpan(span, { includeWeather: true, compareSpecies }),
            fetchDetectionsActivityHeatmapSpan(span),
            birdnetEnabled ? fetchAudioSpeciesLeaderboard(span) : Promise.resolve(null),
        ]);

        // Audio "heard" data is supplementary — a failure here must not disturb the
        // visual leaderboard, so it is handled independently and degrades to empty.
        if (audioResult.status === 'fulfilled') {
            audioSpecies = audioResult.value?.species ?? [];
        } else {
            audioSpecies = [];
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
        loading = false;
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
        try {
            const info = await fetchSpeciesInfo(speciesName);
            speciesInfoCache = { ...speciesInfoCache, [cacheKey]: info };
        } catch {
            // ignore fetch errors
        } finally {
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

    function getBarColor(index: number): string {
        const colors = [
            'bg-amber-500',      // Gold
            'bg-slate-400',      // Silver
            'bg-amber-700',      // Bronze
            'bg-teal-500',
            'bg-blue-500',
            'bg-purple-500',
            'bg-pink-500',
            'bg-indigo-500',
            'bg-cyan-500',
            'bg-emerald-500',
        ];
        return colors[index % colors.length];
    }

    function formatDate(value?: string | null): string {
        if (!value) return '—';
        return formatDateTime(value);
    }

    function formatTrend(delta?: number | null, percent?: number | null): string {
        if (!delta) return '0';
        if (percent === undefined || percent === null) {
            return `${delta > 0 ? '+' : ''}${delta}`;
        }
        return `${delta > 0 ? '+' : ''}${delta} (${percent.toFixed(1)}%)`;
    }

    function rowCountForMode(row: LeaderboardTableRow, mode: SourceMode): number {
        if (mode === 'heard') return row.heard_count;
        if (mode === 'both') return row.count + row.heard_count;
        return row.count;
    }

    function rowDeltaForMode(row: LeaderboardTableRow, mode: SourceMode): number | null {
        if (mode === 'heard') return row.heard_delta;
        if (mode === 'both') return (row.delta ?? 0) + (row.heard_delta ?? 0);
        return row.delta ?? null;
    }

    function rowTrendForMode(row: LeaderboardTableRow, mode: SourceMode): string {
        const delta = rowDeltaForMode(row, mode);
        if (mode === 'heard') return formatTrend(delta, row.heard_percent);
        if (mode === 'both') return formatTrend(delta, null);
        return formatTrend(delta, row.percent);
    }

    function rowLastActivityForMode(row: LeaderboardTableRow, mode: SourceMode): string {
        return formatDate(mode === 'heard' ? row.heard_last : row.last_seen);
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
    let heroBlurb = $derived(getHeroBlurb(heroInfo));
    let heroSource = $derived(getHeroSource(heroInfo));
    function spanLabel(): string {
        if (span === 'day') return $_('leaderboard.sort_by_day');
        if (span === 'week') return $_('leaderboard.sort_by_week');
        if (span === 'month') return $_('leaderboard.sort_by_month');
        return $_('leaderboard.sort_by_total');
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

    let chartSubtitle = $derived(() => {
        if (!timeline) return '';
        return [
            metricLabel(),
            bucketLabel(timeline.bucket),
            leaderboardAnalysisSubtitle
        ].filter(Boolean).join(' • ');
    });

    let chartOptions = $derived((): ApexOptions => {
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
        const temperatureColor = '#f97316';
        const windColor = '#38bdf8';
        const primaryName = metricLabel();
        const smoothName = $_('leaderboard.metric_smooth', { default: 'Smoothed' });
        const temperatureName = $_('leaderboard.temperature');
        const windName = $_('leaderboard.wind_avg');

        const rawData = indexedPoints.map(({ point, x }) => ({
            x,
            y: metricValueFromPoint(point)
        }));
        const smoothData = indexedPoints.map(({ idx, x }) => ({
            x,
            y: smoothedMetricValues()[idx] ?? null
        }));
        const temperatureData = indexedPoints.map(({ point, x }) => ({
            x,
            y: convertTemperature(weatherValue(point.bucket_start, 'temp_avg'))
        }));
        const windData = indexedPoints.map(({ point, x }) => ({
            x,
            y: convertWindSpeed(weatherValue(point.bucket_start, 'wind_avg'), weatherUnitSystem)
        }));

        const hasTemperatureSeries = hasWeather() && showTemperature && temperatureData.some((p) => p.y !== null);
        const hasWindSeries = hasWeather() && showWind && windData.some((p) => p.y !== null);
        const isStacked = detectionUsesBars() && (timeline?.compare_series?.length ?? 0) > 0;

        if (showRawSeries) {
            if (isStacked && timeline?.compare_series?.length) {
                const displayNames = new Map(processedSpecies().map((item) => [item.species, item.displayName] as const));
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
                        color: comparePalette[idx % comparePalette.length],
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
                        color: isDark() ? 'rgba(148,163,184,0.5)' : 'rgba(148,163,184,0.65)',
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

        if (hasTemperatureSeries) {
            series.push({
                name: temperatureName,
                type: 'line',
                color: temperatureColor,
                data: temperatureData
            });
        }

        if (hasWindSeries) {
            series.push({
                name: windName,
                type: 'line',
                color: windColor,
                data: windData
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

        const seriesColors = series.map((s) => s.color || primaryColor);
        // Map from UTC x-value → backend-computed local label so the chart always
        // shows server-timezone labels regardless of the browser's local timezone.
        const xLabelMap = new Map(indexedPoints.map(({ point, x }) => [x, point.label] as const));

        const tickAmount = indexedPoints.length > 1 ? Math.min(6, indexedPoints.length) : undefined;
        const yAxes: Array<{
            min?: number;
            seriesName?: string[];
            opposite?: boolean;
            tickAmount?: number;
            labels: {
                maxWidth?: number;
                style: { fontSize: string; colors: string };
                formatter: (value: number) => string;
            };
        }> = [
            {
                min: 0,
                labels: {
                    style: { fontSize: '10px', colors: '#94a3b8' },
                    formatter: (value: number) => formatMetricValue(value)
                }
            }
        ];
        if (hasTemperatureSeries) {
            yAxes.push({
                // Apex handles dynamic remapping more reliably when seriesName is array form.
                seriesName: [temperatureName],
                opposite: true,
                tickAmount: 4,
                labels: {
                    maxWidth: 52,
                    style: { fontSize: '10px', colors: '#f59e0b' },
                    formatter: (value: number) => formatTemperature(value, temperatureUnit as TemperatureUnit)
                }
            });
        }
        if (hasWindSeries) {
            yAxes.push({
                // Apex handles dynamic remapping more reliably when seriesName is array form.
                seriesName: [windName],
                opposite: true,
                tickAmount: 4,
                labels: {
                    maxWidth: 52,
                    style: { fontSize: '10px', colors: '#0ea5e9' },
                    formatter: (value: number) => `${Math.round(value)} ${windUnitLabel}`
                }
            });
        }

        return {
            chart: {
                type: detectionUsesBars() ? 'bar' : 'line',
                stacked: isStacked,
                height: isStacked ? 380 : 260,
                width: '100%',
                toolbar: { show: false },
                zoom: { enabled: false },
                animations: { enabled: true, speed: 500 }
            },
            colors: seriesColors,
            series,
            annotations: { xaxis: rainBandAnnotations() },
            noData: {
                text: $_('dashboard.no_detections')
            },
            dataLabels: { enabled: false },
            stroke: {
                curve: 'smooth',
                width: series.map((s) => (s.type === 'bar' ? 0 : 2)),
                dashArray: series.map((s) => (
                    s.name === smoothName ? 5
                        : (s.name === windName ? 4 : 0)
                ))
            },
            fill: {
                type: series.map((s) => (s.type === 'area' ? 'gradient' : 'solid')),
                gradient: {
                    shadeIntensity: 1,
                    opacityFrom: 0.35,
                    opacityTo: 0.05,
                    stops: [0, 90, 100]
                }
            },
            plotOptions: {
                bar: {
                    borderRadius: isStacked ? 3 : 5,
                    ...(isStacked ? { borderRadiusApplication: 'end' } : {}),
                    columnWidth: timeline?.bucket === 'day' ? '62%' : '56%'
                }
            },
            markers: { size: 0, hover: { size: 0 } },
            grid: {
                borderColor: 'rgba(148,163,184,0.2)',
                strokeDashArray: 3,
                padding: { left: 12, right: 12, top: 8, bottom: 4 }
            },
            xaxis: {
                type: 'datetime',
                tickAmount,
                labels: {
                    rotate: 0,
                    style: { fontSize: '10px', colors: '#94a3b8' },
                    formatter: (val: string | number) => xLabelMap.get(Number(val)) ?? ''
                }
            },
            yaxis: yAxes,
            tooltip: {
                theme: isDark() ? 'dark' : 'light',
                x: {
                    formatter: (val: number) => xLabelMap.get(val) ?? ''
                },
                y: {
                    formatter: (
                        value: number,
                        opts?: { seriesIndex?: number; w?: { globals?: { seriesNames?: string[] } } }
                    ) => {
                        const seriesIndex = opts?.seriesIndex ?? -1;
                        const seriesName = opts?.w?.globals?.seriesNames?.[seriesIndex] ?? '';
                        if (seriesName === temperatureName) {
                            return formatTemperature(value, temperatureUnit as TemperatureUnit);
                        }
                        if (seriesName === windName) return `${Math.round(value)} ${windUnitLabel}`;
                        if (seriesName === smoothName || seriesName === primaryName) return formatMetricValue(value);
                        return `${Math.round(value)} ${$_('leaderboard.metric_detections', { default: 'detections' }).toLowerCase()}`;
                    }
                }
            },
            legend: { show: false },
            subtitle: {
                text: chartSubtitle() ?? '',
                align: 'left',
                offsetX: 0,
                offsetY: 0,
                style: {
                    fontSize: '10px',
                    fontWeight: 600,
                    color: isDark() ? '#94a3b8' : '#64748b'
                }
            }
        };
    });

    let comparePalette = $derived(
        themeStore.colorTheme === 'bluetit'
            ? ['#2563eb', '#0ea5e9', '#6366f1', '#f59e0b', '#ec4899', '#14b8a6', '#8b5cf6', '#f97316']
            : ['#10b981', '#0ea5e9', '#6366f1', '#f59e0b', '#ec4899', '#14b8a6', '#8b5cf6', '#f97316']
    );
    const heatmapDayOrder = [1, 2, 3, 4, 5, 6, 0];

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


    // Keep in sync with the .slice(0, 7) in selectCompareSpecies and the >= 8 cap in stats.py
    const DONUT_MAX_SLICES = 7;
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
    let donutHasData = $derived(() => donutSeries().series.some((v) => v > 0));
    let donutChartOptions = $derived((): ApexOptions => {
        const { labels, series } = donutSeries();
        const donutPalette = themeStore.colorTheme === 'bluetit'
            ? ['#2563eb', '#0ea5e9', '#6366f1', '#f59e0b', '#ec4899', '#14b8a6', '#8b5cf6', '#94a3b8']
            : ['#10b981', '#0ea5e9', '#6366f1', '#f59e0b', '#ec4899', '#14b8a6', '#8b5cf6', '#94a3b8'];
        return {
            chart: {
                type: 'donut',
                height: 260,
                width: '100%',
                toolbar: { show: false },
                animations: { enabled: true, speed: 450 }
            },
            series,
            labels,
            colors: donutPalette.slice(0, labels.length),
            dataLabels: {
                enabled: true,
                formatter: (val: number) => (val >= 5 ? `${Math.round(val)}%` : ''),
                style: { fontSize: '10px', fontWeight: 600, colors: ['#fff'] },
                dropShadow: { enabled: false }
            },
            plotOptions: {
                pie: {
                    donut: {
                        size: '62%',
                        labels: {
                            show: true,
                            total: {
                                show: true,
                                showAlways: true,
                                label: $_('leaderboard.metric_detections', { default: 'Detections' }),
                                fontSize: '11px',
                                fontWeight: 600,
                                color: isDark() ? '#94a3b8' : '#64748b',
                                formatter: () => totalDetections.toLocaleString()
                            },
                            value: {
                                show: true,
                                fontSize: '15px',
                                fontWeight: 700,
                                color: isDark() ? '#e2e8f0' : '#1e293b',
                                formatter: (val: string) => Number(val).toLocaleString()
                            },
                            name: {
                                show: true,
                                fontSize: '10px',
                                color: isDark() ? '#94a3b8' : '#64748b'
                            }
                        }
                    }
                }
            },
            stroke: { width: 1.5, colors: [isDark() ? '#1e293b' : '#ffffff'] },
            legend: {
                show: true,
                position: 'bottom',
                fontSize: '10px',
                labels: { colors: isDark() ? '#94a3b8' : '#64748b' },
                markers: { size: 8 }
            },
            tooltip: {
                theme: isDark() ? 'dark' : 'light',
                y: {
                    formatter: (val: number) =>
                        `${val.toLocaleString()} ${$_('leaderboard.metric_detections', { default: 'detections' }).toLowerCase()}`
                }
            },
            noData: { text: $_('dashboard.no_detections') }
        };
    });

    let heatmapCellMap = $derived(() => {
        const map = new Map<string, number>();
        for (const cell of activityHeatmap?.cells ?? []) {
            if (cell.day_of_week < 0 || cell.day_of_week > 6 || cell.hour < 0 || cell.hour > 23) continue;
            map.set(`${cell.day_of_week}-${cell.hour}`, Math.max(0, Number(cell.count ?? 0)));
        }
        return map;
    });

    let heatmapSeries = $derived(() => heatmapDayOrder.map((dayOfWeek) => ({
        name: weekdayLabel(dayOfWeek),
        data: Array.from({ length: 24 }, (_, hour) => ({
            x: hourLabel(hour),
            y: heatmapCellMap().get(`${dayOfWeek}-${hour}`) ?? 0
        }))
    })));
    let heatmapHasData = $derived(() => (activityHeatmap?.total_count ?? 0) > 0);
    let heatmapChartOptions = $derived((): ApexOptions => {
        const maxCellCount = Math.max(1, activityHeatmap?.max_cell_count ?? 0);
        const midLow = Math.max(1, Math.ceil(maxCellCount * 0.2));
        const mid = Math.max(midLow + 1, Math.ceil(maxCellCount * 0.45));
        const high = Math.max(mid + 1, Math.ceil(maxCellCount * 0.7));
        const ranges: Array<{ from: number; to: number; color: string; name: string }> = [
            { from: 0, to: 0, color: isDark() ? 'rgba(51,65,85,0.22)' : 'rgba(226,232,240,0.8)', name: '0' }
        ];
        const pushRange = (from: number, to: number, color: string, name: string) => {
            if (from <= to) {
                ranges.push({ from, to, color, name });
            }
        };
        pushRange(1, Math.min(midLow, maxCellCount), '#93c5fd', '1+');
        pushRange(midLow + 1, Math.min(mid, maxCellCount), '#60a5fa', `${midLow + 1}+`);
        pushRange(mid + 1, Math.min(high, maxCellCount), '#3b82f6', `${mid + 1}+`);
        pushRange(high + 1, maxCellCount, '#1d4ed8', `${high + 1}+`);
        return {
            chart: {
                type: 'heatmap',
                height: 260,
                width: '100%',
                toolbar: { show: false },
                animations: { enabled: true, speed: 350 }
            },
            series: heatmapSeries(),
            dataLabels: { enabled: false },
            stroke: {
                width: 1,
                colors: [isDark() ? 'rgba(15,23,42,0.45)' : 'rgba(148,163,184,0.2)']
            },
            plotOptions: {
                heatmap: {
                    radius: 2,
                    shadeIntensity: 0.45,
                    colorScale: {
                        ranges
                    }
                }
            },
            xaxis: {
                labels: { style: { fontSize: '10px', colors: '#94a3b8' } },
                tickPlacement: 'on'
            },
            yaxis: {
                labels: { style: { fontSize: '10px', colors: '#94a3b8' } }
            },
            tooltip: {
                theme: isDark() ? 'dark' : 'light',
                y: {
                    formatter: (value: number) => `${formatMetricValue(value)}`
                }
            },
            legend: { show: false }
        };
    });

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
        const priorSubtitle = leaderboardAnalysisSubtitle;
        try {
            const config = buildLeaderboardConfig();
            leaderboardAnalysisSubtitle = `${spanLabel()} • ${bucketLabel(timeline.bucket)}`;
            await tick();
            await sleep(200);
            const key = await computeConfigKey(config);
            leaderboardConfigKey = key;
            const chartInstance = (chartEl as HTMLDivElement & {
                __apexchart?: { dataURI(): Promise<{ imgURI?: string }> };
            }).__apexchart;
            const dataUri = await chartInstance?.dataURI();
            const imageBase64 = dataUri?.imgURI ?? null;
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
            leaderboardAnalysisSubtitle = priorSubtitle;
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

<div class="space-y-10" data-leaderboard-page>
    <!-- Ranking controls -->
    <div class="border-y border-slate-200/80 py-4 dark:border-slate-700/70">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div class="flex flex-wrap gap-2" aria-label={$_('leaderboard.title')}>
            <button
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
                onclick={() => span = 'week'}
                class="tab-button {span === 'week' ? 'tab-button-active' : 'tab-button-inactive'}"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M4 6h12M4 10h12M4 14h8"></path>
                </svg>
                {$_('leaderboard.sort_by_week')}
            </button>
            <button
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
                        onclick={() => sourceMode = 'seen'}
                        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 {sourceMode === 'seen' ? 'bg-white dark:bg-slate-700 text-emerald-600 dark:text-emerald-300 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
                    >
                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M2.5 12S5.5 5.5 12 5.5 21.5 12 21.5 12 18.5 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.5"/></svg>
                        {$_('leaderboard.source_seen', { default: 'Seen' })}
                    </button>
                    <button
                        type="button"
                        onclick={() => sourceMode = 'heard'}
                        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 {sourceMode === 'heard' ? 'bg-white dark:bg-slate-700 text-teal-600 dark:text-teal-300 shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
                    >
                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/></svg>
                        {$_('leaderboard.source_heard', { default: 'Heard' })}
                    </button>
                    <button
                        type="button"
                        onclick={() => sourceMode = 'both'}
                        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 {sourceMode === 'both' ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-white shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}"
                    >
                        {$_('leaderboard.source_both', { default: 'Both' })}
                    </button>
                </div>
            {/if}

            <label class="inline-flex min-h-11 items-center gap-2 text-sm text-slate-600 dark:text-slate-300 select-none">
                <input
                    type="checkbox"
                    class="rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:ring-emerald-500"
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

    {#if loading && leaderboardSpecies().length === 0}
        <div class="space-y-3">
            {#each [1, 2, 3, 4, 5, 6] as _}
                <div class="h-16 bg-slate-100 dark:bg-slate-800 rounded-xl animate-pulse"></div>
            {/each}
        </div>
    {:else if leaderboardSpecies().length === 0}
        <div class="border-y border-slate-200 py-14 text-center dark:border-slate-700">
            <svg class="mx-auto mb-4 h-10 w-10 text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 16c2.5-1.5 3.5-4 3.5-7.5 2.2 2.7 5.2 3.8 9 3.2-1.2 3.8-4.2 6.3-8.1 6.3H7l-2 2v-4z" />
                <path stroke-linecap="round" d="M16.5 8.5 20 7l-2.2 3" />
            </svg>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">{$_('leaderboard.no_species')}</h3>
            <p class="text-slate-500 dark:text-slate-400">
                {species.length > 0 && !includeUnknownBird
                    ? $_('leaderboard.only_unknown_desc')
                    : $_('leaderboard.no_species_desc')}
            </p>
        </div>
    {:else}
        <section class="overflow-hidden rounded-[2rem] border border-teal-200/80 bg-gradient-to-br from-teal-50/80 via-white to-emerald-50/60 dark:border-teal-800/60 dark:from-teal-950/35 dark:via-slate-900/40 dark:to-emerald-950/25" data-leaderboard-featured>
            <div class="grid lg:grid-cols-[minmax(0,1fr)_17rem]">
                <div class="p-6 md:p-8">
                    <div class="flex items-center gap-3 text-sm font-semibold text-teal-700 dark:text-teal-300">
                        <svg data-leaderboard-section-icon aria-hidden="true" class="h-8 w-8 rounded-xl border border-teal-200 bg-white/80 p-1.5 text-teal-600 dark:border-teal-700 dark:bg-slate-900/60 dark:text-teal-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M5 16c2.5-1.5 3.5-4 3.5-7.5 2.2 2.7 5.2 3.8 9 3.2-1.2 3.8-4.2 6.3-8.1 6.3H7l-2 2v-4z" />
                            <path stroke-linecap="round" d="M16.5 8.5 20 7l-2.2 3" />
                        </svg>
                        {$_('leaderboard.featured')}
                    </div>
                    <h3 class="mt-4 text-2xl font-bold text-slate-950 dark:text-white md:text-3xl">{topByCount?.displayName || '—'}</h3>
                    {#if topByCount?.subName}
                        <p class="mt-1 text-sm italic text-slate-500 dark:text-slate-400">{topByCount.subName}</p>
                    {/if}
                    {#if heroBlurb}
                        <p class="mt-4 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">{heroBlurb}</p>
                    {/if}
                    <div class="mt-5 flex flex-wrap items-center gap-3">
                        <button
                            type="button"
                            onclick={() => topByCount && (selectedSpecies = topByCount.species)}
                            class="inline-flex min-h-11 items-center gap-2 rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2 dark:bg-teal-500 dark:text-slate-950 dark:hover:bg-teal-400"
                        >
                            {$_('leaderboard.view_details')}
                            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                        </button>
                        {#if heroSource}
                            <a href={heroSource.url} target="_blank" rel="noopener noreferrer" class="inline-flex min-h-11 items-center gap-2 px-1 text-sm font-semibold text-teal-700 hover:text-teal-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:text-teal-300">
                                {heroSource.source === 'wikipedia' ? $_('actions.read_more_wikipedia') : $_('actions.read_more_source', { values: { source: $_('common.source_inaturalist', { default: 'iNaturalist' }) } })}
                                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14 4h6v6m0-6L10 14m-1-8H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" /></svg>
                            </a>
                        {/if}
                    </div>
                </div>
                <dl class="grid grid-cols-2 border-t border-teal-200/70 bg-white/40 dark:border-teal-800/50 dark:bg-slate-950/15 lg:grid-cols-1 lg:border-l lg:border-t-0">
                    <div class="p-4 lg:px-6"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{selectedCountLabel()}</dt><dd class="mt-1 text-2xl font-bold text-teal-700 dark:text-teal-300">{topByCount?.count?.toLocaleString() || '—'}</dd></div>
                    <div class="border-l border-teal-200/70 p-4 dark:border-teal-800/50 lg:border-l-0 lg:border-t lg:px-6"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.trend')}</dt><dd class="mt-1 text-lg font-bold text-slate-900 dark:text-white">{span === 'all' ? '—' : formatTrend(topByCount?.delta, topByCount?.percent)}</dd></div>
                    <div class="border-t border-teal-200/70 p-4 dark:border-teal-800/50 lg:px-6"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.cameras')}</dt><dd class="mt-1 text-lg font-bold text-slate-900 dark:text-white">{(topByCount?.camera_count ?? 0).toLocaleString()}</dd></div>
                    <div class="border-l border-t border-teal-200/70 p-4 dark:border-teal-800/50 lg:border-l-0 lg:px-6"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.last_seen')}</dt><dd class="mt-1 text-sm font-semibold text-slate-700 dark:text-slate-300">{formatDate(topByCount?.last_seen)}</dd></div>
                </dl>
            </div>
        </section>

        <dl class="grid border-y border-slate-200 dark:border-slate-700 md:grid-cols-3" data-leaderboard-highlights>
            <div class="flex min-w-0 items-center gap-3 py-4 md:pr-5">
                <svg class="h-5 w-5 shrink-0 text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 20V12h4v8M10 20V7h4v13M16 20V4h4v16" /></svg>
                <div class="min-w-0"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.most_active')}</dt><dd class="truncate font-semibold text-slate-900 dark:text-white">{topByCount?.displayName || '—'} <span class="font-normal text-teal-700 dark:text-teal-300">· {(topByCount?.count || 0).toLocaleString()}</span></dd></div>
            </div>
            {#if span !== 'all'}
                <div class="flex min-w-0 items-center gap-3 border-t border-slate-200 py-4 dark:border-slate-700 md:border-l md:border-t-0 md:px-5">
                    <svg class="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m4 17 5-5 4 4 7-9m-5 0h5v5" /></svg>
                    <div class="min-w-0"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.rising')}</dt><dd class="truncate font-semibold text-slate-900 dark:text-white">{topByTrend?.displayName || '—'} <span class="font-normal text-amber-700 dark:text-amber-300">· {formatTrend(topByTrend?.delta, topByTrend?.percent)}</span></dd></div>
                </div>
            {/if}
            <div class="flex min-w-0 items-center gap-3 border-t border-slate-200 py-4 dark:border-slate-700 md:border-l md:border-t-0 md:pl-5">
                <svg class="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path stroke-linecap="round" d="M12 8v4l3 2" /></svg>
                <div class="min-w-0"><dt class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('leaderboard.most_recent')}</dt><dd class="truncate font-semibold text-slate-900 dark:text-white">{mostRecent?.displayName || '—'} <span class="font-normal text-sky-700 dark:text-sky-300">· {formatDate(mostRecent?.last_seen)}</span></dd></div>
            </div>
        </dl>

        <section class="space-y-5" data-leaderboard-rankings>
            <div class="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div class="flex items-center gap-3">
                    <svg data-leaderboard-section-icon aria-hidden="true" class="h-8 w-8 rounded-xl border border-teal-200 bg-teal-50 p-1.5 text-teal-700 dark:border-teal-800 dark:bg-teal-950/40 dark:text-teal-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                        <path stroke-linecap="round" d="M6 4v16M18 4v16" /><path stroke-linecap="round" stroke-linejoin="round" d="m9 8 3-3 3 3m-6 8 3 3 3-3" />
                    </svg>
                    <div>
                        <h3 class="text-xl font-bold text-slate-950 dark:text-white">{$_('leaderboard.full_rankings', { default: 'Full rankings' })}</h3>
                        <p class="text-sm text-slate-500 dark:text-slate-400">{$_('leaderboard.all_species')}</p>
                    </div>
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400">{spanLabel()} · {formatRangeCompact(timeline?.window_start, timeline?.window_end)} · {totalDetections.toLocaleString()}</p>
            </div>

            {#key `${sourceMode}-${span}`}
                <div class="divide-y divide-slate-200 border-y border-slate-200 dark:divide-slate-700 dark:border-slate-700 md:hidden" data-leaderboard-mobile-rankings>
                {#each leaderboardTableRows(sourceMode) as item, index (`mobile-${item.species}|${item.audio_only}|${index}`)}
                    <button
                        type="button"
                        onclick={() => selectedSpecies = item.species}
                        class="group flex min-h-20 w-full items-center gap-3 py-3 text-left transition hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500 dark:hover:bg-slate-800/40"
                        title={item.species === "Unknown Bird" ? $_('leaderboard.unidentified_desc') : ""}
                        aria-label={$_('leaderboard.view_species', { values: { species: item.displayName } })}
                    >
                        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-bold {index < 3 ? 'bg-teal-100 text-teal-800 dark:bg-teal-900/50 dark:text-teal-200' : 'text-slate-500 dark:text-slate-400'}" aria-label={`${$_('leaderboard.rank')} ${index + 1}`}>{index + 1}</span>
                        <span class="h-12 w-12 shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
                            {#if getCachedSpeciesInfo(item.species)?.thumbnail_url}
                                <img src={getCachedSpeciesInfo(item.species)?.thumbnail_url ?? undefined} alt="" class="h-full w-full object-cover" loading="lazy" />
                            {:else}
                                <span class="flex h-full w-full items-center justify-center text-slate-400"><svg class="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 16c2.5-1.5 3.5-4 3.5-7.5 2.2 2.7 5.2 3.8 9 3.2-1.2 3.8-4.2 6.3-8.1 6.3H7l-2 2v-4z" /></svg></span>
                            {/if}
                        </span>
                        <span class="min-w-0 flex-1">
                            <span class="flex items-center gap-2">
                                <span class="truncate font-semibold text-slate-900 dark:text-white">{item.displayName}</span>
                                {#if item.audio_only}<span class="inline-flex shrink-0 items-center gap-1 rounded-full bg-teal-100 px-2 py-0.5 text-xs font-semibold text-teal-700 dark:bg-teal-900/40 dark:text-teal-300"><svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 0 1-14 0m7 7v4m-4 0h8M9 5a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0V5z" /></svg>{$_('leaderboard.audio_only', { default: 'Audio only' })}</span>{/if}
                            </span>
                            {#if item.subName}<span class="mt-0.5 block truncate text-xs italic text-slate-500 dark:text-slate-400">{item.subName}</span>{/if}
                            <span class="mt-1 block text-xs text-slate-500 dark:text-slate-400">{$_('leaderboard.last_seen')}: {rowLastActivityForMode(item, sourceMode)}</span>
                        </span>
                        <span class="shrink-0 text-right">
                            <span class="block text-base font-bold text-slate-900 dark:text-white">{rowCountForMode(item, sourceMode).toLocaleString()}</span>
                            <span class="block text-xs font-semibold {(rowDeltaForMode(item, sourceMode) ?? 0) > 0 ? 'text-emerald-600 dark:text-emerald-400' : (rowDeltaForMode(item, sourceMode) ?? 0) < 0 ? 'text-rose-500 dark:text-rose-400' : 'text-slate-400'}">{span === 'all' ? '—' : rowTrendForMode(item, sourceMode)}</span>
                        </span>
                        <svg class="h-4 w-4 shrink-0 text-slate-400 transition group-hover:translate-x-0.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" /></svg>
                    </button>
                {/each}
                </div>

                <div class="hidden overflow-hidden border-y border-slate-200 dark:border-slate-700 md:block" data-leaderboard-desktop-rankings>
                <table class="w-full table-fixed text-left text-sm" data-testid="leaderboard-table">
                    <thead class="border-b border-slate-200 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
                        <tr>
                            <th class="w-14 px-3 py-3 text-center">{$_('leaderboard.rank')}</th>
                            <th class="w-[36%] px-3 py-3">{$_('leaderboard.species')}</th>
                            <th class="px-3 py-3 text-right">{$_('leaderboard.source_seen', { default: 'Seen' })}</th>
                            {#if birdnetEnabled}<th class="px-3 py-3 text-right">{$_('leaderboard.source_heard', { default: 'Heard' })}</th>{/if}
                            <th class="hidden px-3 py-3 text-right lg:table-cell">{$_('leaderboard.trend')}</th>
                            <th class="hidden px-3 py-3 text-right xl:table-cell">{$_('leaderboard.cameras')}</th>
                            <th class="hidden px-3 py-3 text-right xl:table-cell">{$_('leaderboard.avg_confidence')}</th>
                            <th class="hidden w-36 px-3 py-3 lg:table-cell">{$_('leaderboard.last_seen')}</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                        {#each leaderboardTableRows(sourceMode) as item, index (`desktop-${item.species}|${item.audio_only}|${index}`)}
                            {@const rowCountPct = maxCount > 0 ? Math.round((item.count / maxCount) * 100) : 0}
                            {@const rowHeardPct = maxHeard > 0 ? Math.round((item.heard_count / maxHeard) * 100) : 0}
                            <tr class="transition hover:bg-slate-50/80 dark:hover:bg-slate-800/35">
                                <td class="px-3 py-3 text-center"><span class="inline-flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold {index < 3 ? 'bg-teal-100 text-teal-800 dark:bg-teal-900/50 dark:text-teal-200' : 'text-slate-500 dark:text-slate-400'}" aria-label={`${$_('leaderboard.rank')} ${index + 1}`}>{index + 1}</span></td>
                                <td class="px-3 py-3">
                                    <button type="button" onclick={() => selectedSpecies = item.species} class="group flex min-h-11 max-w-full items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500" aria-label={$_('leaderboard.view_species', { values: { species: item.displayName } })}>
                                        <span class="h-10 w-10 shrink-0 overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-800">
                                            {#if getCachedSpeciesInfo(item.species)?.thumbnail_url}<img src={getCachedSpeciesInfo(item.species)?.thumbnail_url ?? undefined} alt="" class="h-full w-full object-cover" loading="lazy" />{:else}<span class="flex h-full w-full items-center justify-center text-slate-400"><svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 16c2.5-1.5 3.5-4 3.5-7.5 2.2 2.7 5.2 3.8 9 3.2-1.2 3.8-4.2 6.3-8.1 6.3H7l-2 2v-4z" /></svg></span>{/if}
                                        </span>
                                        <span class="min-w-0"><span class="flex items-center gap-2"><span class="block truncate font-semibold text-slate-900 group-hover:text-teal-700 dark:text-white dark:group-hover:text-teal-300">{item.displayName}</span>{#if item.audio_only}<svg class="h-4 w-4 shrink-0 text-teal-600 dark:text-teal-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-label={$_('leaderboard.audio_only', { default: 'Audio only' })}><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 0 1-14 0m7 7v4m-4 0h8M9 5a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0V5z" /></svg>{/if}</span>{#if item.subName}<span class="block truncate text-xs italic text-slate-500 dark:text-slate-400">{item.subName}</span>{/if}</span>
                                    </button>
                                </td>
                                <td class="px-3 py-3 text-right"><span class="font-semibold text-slate-700 dark:text-slate-200">{item.count.toLocaleString()}</span><span class="ml-auto mt-1 block h-1 w-14 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"><span class="block h-full rounded-full bg-emerald-500/70" style="width: {rowCountPct}%"></span></span></td>
                                {#if birdnetEnabled}<td class="px-3 py-3 text-right"><span class="font-semibold text-teal-700 dark:text-teal-300">{item.heard_count.toLocaleString()}</span><span class="ml-auto mt-1 block h-1 w-14 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700"><span class="block h-full rounded-full bg-teal-500/70" style="width: {rowHeardPct}%"></span></span></td>{/if}
                                <td class="hidden px-3 py-3 text-right font-semibold lg:table-cell {(item.delta ?? 0) > 0 ? 'text-emerald-600 dark:text-emerald-400' : (item.delta ?? 0) < 0 ? 'text-rose-500 dark:text-rose-400' : 'text-slate-400'}">{span === 'all' ? '—' : formatTrend(item.delta, item.percent)}</td>
                                <td class="hidden px-3 py-3 text-right text-slate-600 dark:text-slate-300 xl:table-cell">{(item.camera_count ?? 0).toLocaleString()}</td>
                                <td class="hidden px-3 py-3 text-right text-slate-600 dark:text-slate-300 xl:table-cell">{(item.avg_confidence ?? 0).toFixed(2)}</td>
                                <td class="hidden px-3 py-3 text-slate-500 dark:text-slate-400 lg:table-cell">{formatDate(item.last_seen)}</td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
                </div>
            {/key}
        </section>

        <section class="space-y-6 border-t border-slate-200 pt-8 dark:border-slate-700" data-leaderboard-analytics>
            <div class="flex items-center gap-3">
                <svg data-leaderboard-section-icon aria-hidden="true" class="h-8 w-8 rounded-xl border border-teal-200 bg-teal-50 p-1.5 text-teal-700 dark:border-teal-800 dark:bg-teal-950/40 dark:text-teal-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" d="M4 19V9m5 10V5m5 14v-7m5 7V3" /></svg>
                <div><h3 class="text-xl font-bold text-slate-950 dark:text-white">{$_('leaderboard.analytics_section', { default: 'Analytics' })}</h3><p class="text-sm text-slate-500 dark:text-slate-400">{spanLabel()} · {formatRangeCompact(timeline?.window_start, timeline?.window_end)}</p></div>
            </div>

        <div class="border-y border-slate-200 py-6 dark:border-slate-700 md:py-8">
            <div class="relative flex flex-col flex-1">
                <div class="flex flex-col gap-4">
                    <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                        <div>
                            <h4 class="text-lg font-bold text-slate-900 dark:text-white md:text-xl">{$_('leaderboard.detections_over_time')}</h4>
                            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
                                {spanLabel()} · {formatRangeCompact(timeline?.window_start, timeline?.window_end)} · {bucketLabel(timeline?.bucket)} · {(timeline?.total_count ?? 0).toLocaleString()} {metricLabel().toLowerCase()}
                            </p>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                            {#if canUseLeaderboardAnalysis}
                                <button
                                    type="button"
                                    class="inline-flex min-h-11 items-center rounded-xl border border-teal-200 bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-700 transition hover:bg-teal-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-teal-800 dark:bg-teal-950/30 dark:text-teal-300 dark:hover:bg-teal-950/50"
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

                <div class="mt-6 w-full flex-1 min-h-[140px]" style="height: {isStackedChart() ? 380 : 260}px">
                    {#if timeline?.points?.length}
                        {#key `${span}-${timeline.total_count}-${timeline.bucket}-${showTemperature}-${showWind}-${showPrecip}-${isDark()}-${themeStore.colorTheme}`}
                            <div use:chart={chartOptions()} bind:this={chartEl} class="w-full" style="height: {isStackedChart() ? 380 : 260}px"></div>
                        {/key}
                    {:else}
                        <div class="h-full w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                    {/if}
                </div>

                <p class="mt-3 text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {$_('leaderboard.total', { default: 'Total' })}: {timeline?.total_count?.toLocaleString() || '0'}
                    · {$_('leaderboard.metric_peak', { default: 'Peak' })}: {formatMetricValue(metricPeak())}
                    · {$_('leaderboard.metric_avg', { default: 'Avg' })}: {formatMetricValue(metricAvg())}
                </p>
                {#if canUseLeaderboardAnalysis && (leaderboardAnalysisLoading || leaderboardAnalysisError || leaderboardAnalysis)}
                    <div class="mt-4 border-l-2 border-teal-300 py-2 pl-4 text-sm text-slate-600 dark:border-teal-700 dark:text-slate-300">
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
                                        <p class="text-xs font-semibold text-emerald-600 dark:text-emerald-300">{block.text}</p>
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
                    <summary class="inline-flex min-h-11 cursor-pointer list-none select-none items-center gap-2 rounded-xl px-2 py-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:text-slate-300 dark:hover:bg-slate-800/40 [&::-webkit-details-marker]:hidden">
                        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M6 9a4 4 0 1 1 7.5-1.8A2.8 2.8 0 1 1 14 13H6.5"></path>
                            <path d="M7 14.5v2M10 14.5v2M13 14.5v2"></path>
                        </svg>
                        {$_('leaderboard.weather_overlays', { default: 'Weather overlays' })}
                        <svg class="h-3 w-3 transition-transform group-open/weather:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <path d="M6 8l4 4 4-4"></path>
                        </svg>
                        {#if timeline?.sunrise_range}
                            <span class="font-semibold normal-case tracking-normal text-amber-600 dark:text-amber-400">{timeline.sunrise_range}</span>
                        {/if}
                        {#if timeline?.sunset_range}
                            <span class="font-semibold normal-case tracking-normal text-orange-600 dark:text-orange-400">{timeline.sunset_range}</span>
                        {/if}
                    </summary>
                    <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
                        <button
                            type="button"
                            onclick={() => showTemperature = !showTemperature}
                            disabled={!hasWeather()}
                            class="inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:cursor-not-allowed disabled:opacity-45
                                {showTemperature ? 'border-amber-300 dark:border-amber-600 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' : 'border-slate-200/70 dark:border-slate-700/60 text-slate-500 dark:text-slate-400'}"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M10 4a2 2 0 0 0-4 0v6.4a3.5 3.5 0 1 0 4 0V4z"></path>
                                <path d="M8 9.5V4"></path>
                            </svg>
                            {$_('leaderboard.temperature')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showWind = !showWind}
                            disabled={!hasWeather()}
                            class="inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:cursor-not-allowed disabled:opacity-45
                                {showWind ? 'border-sky-300 dark:border-sky-600 bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300' : 'border-slate-200/70 dark:border-slate-700/60 text-slate-500 dark:text-slate-400'}"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M3 8h9a2 2 0 1 0-2-2"></path>
                                <path d="M3 12h12a2 2 0 1 1-2 2"></path>
                            </svg>
                            {$_('leaderboard.wind_avg')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showPrecip = !showPrecip}
                            disabled={!hasWeather()}
                            class="inline-flex min-h-11 items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 disabled:cursor-not-allowed disabled:opacity-45
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

        <div class="grid grid-cols-1 divide-y divide-slate-200 border-b border-slate-200 dark:divide-slate-700 dark:border-slate-700 xl:grid-cols-2 xl:divide-x xl:divide-y-0">
            <div class="py-6 xl:pr-8">
                <div class="relative">
                    <div class="flex items-start justify-between gap-3">
                        <div class="flex items-start gap-2.5">
                            <div class="h-8 w-8 rounded-xl border border-violet-200/80 dark:border-violet-700/60 bg-violet-100/80 dark:bg-violet-900/30 flex items-center justify-center text-violet-700 dark:text-violet-300">
                                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                    <circle cx="10" cy="10" r="7"></circle>
                                    <circle cx="10" cy="10" r="3"></circle>
                                    <path d="M10 3v4M10 13v4M3 10h4M13 10h4" stroke-width="1.4"></path>
                                </svg>
                            </div>
                            <div>
                                <p class="text-xs font-semibold text-violet-600 dark:text-violet-300">
                                    {$_('leaderboard.detection_breakdown_title', { default: 'Detection Breakdown' })}
                                </p>
                                <h4 class="mt-1 text-lg font-bold text-slate-900 dark:text-white md:text-xl">
                                    {$_('leaderboard.detection_breakdown_subtitle', { default: 'Species composition' })}
                                </h4>
                            </div>
                        </div>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-300">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M3 6h14M3 10h14M3 14h7"></path>
                            </svg>
                            {donutSeries().labels.length}
                        </span>
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
                            {totalDetections.toLocaleString()} {$_('leaderboard.metric_detections', { default: 'detections' }).toLowerCase()}
                        </span>
                    </div>

                    <div class="mt-4 min-h-[260px]">
                        {#if donutHasData()}
                            {#key `${span}-${donutSeries().series.join(',')}-${isDark()}-${themeStore.colorTheme}`}
                                <div use:chart={donutChartOptions()} class="w-full h-[260px]"></div>
                            {/key}
                        {:else}
                            <div class="h-[260px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                                {$_('leaderboard.no_compare_data', { default: 'Not enough data for comparison yet.' })}
                            </div>
                        {/if}
                    </div>
                </div>
            </div>

            <div class="py-6 xl:pl-8">
                <div class="relative">
                    <div class="flex items-start justify-between gap-3">
                        <div class="flex items-start gap-2.5">
                            <div class="h-8 w-8 rounded-xl border border-cyan-200/80 dark:border-cyan-700/60 bg-cyan-100/80 dark:bg-cyan-900/30 flex items-center justify-center text-cyan-700 dark:text-cyan-300">
                                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                    <rect x="3" y="4" width="14" height="12" rx="2"></rect>
                                    <path d="M3 9h14M8 4v12M13 4v12"></path>
                                </svg>
                            </div>
                            <div>
                                <p class="text-xs font-semibold text-cyan-600 dark:text-cyan-300">
                                    {$_('leaderboard.activity_heatmap_title', { default: 'Activity Heatmap' })}
                                </p>
                                <h4 class="mt-1 text-lg font-bold text-slate-900 dark:text-white md:text-xl">
                                    {$_('leaderboard.activity_heatmap_subtitle', { default: 'Hour x weekday activity' })}
                                </h4>
                            </div>
                        </div>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-300">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <rect x="3" y="4" width="14" height="12" rx="2"></rect>
                                <path d="M3 9h14M8 4v12M13 4v12"></path>
                            </svg>
                            {formatMetricValue(activityHeatmap?.max_cell_count ?? 0)}
                        </span>
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
                            {$_('leaderboard.total', { default: 'Total' })}: {formatMetricValue(activityHeatmap?.total_count ?? 0)}
                        </span>
                    </div>

                    <div class="mt-4 min-h-[260px]">
                        {#if activityHeatmap && heatmapHasData()}
                            {#key `${span}-${activityHeatmap.total_count}-${activityHeatmap.max_cell_count}-${isDark()}`}
                                <div use:chart={heatmapChartOptions()} class="w-full h-[260px]"></div>
                            {/key}
                        {:else if activityHeatmap}
                            <div class="h-[260px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                                {$_('leaderboard.no_activity_data', { default: 'No activity captured in this window yet.' })}
                            </div>
                        {:else}
                            <div class="h-[260px] w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
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
