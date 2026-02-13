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
        type DetectionsActivityHeatmapResponse,
        type DetectionsTimelineSpanResponse,
        type LeaderboardSpan,
        type SpeciesCount,
        type SpeciesInfo
    } from '../api';
    import { chart } from '../actions/apexchart';
    import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { themeStore } from '../stores/theme.svelte';
    import { getBirdNames } from '../naming';
    import { formatTemperature } from '../utils/temperature';
    import { formatDateTime } from '../utils/datetime';
    import { _ } from 'svelte-i18n';

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

    let species: LeaderboardRow[] = $state([]);
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
    let chartViewMode = $state<'auto' | 'line' | 'bar'>('auto');
    let trendMode = $state<TrendMode>('smooth');

    const enrichmentModeSetting = $derived(settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment');
    const enrichmentSingleProviderSetting = $derived(settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia');
    const enrichmentSummaryProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_summary_source ?? authStore.enrichmentSummarySource ?? 'wikipedia')
    );
    const summaryEnabled = $derived(enrichmentSummaryProvider !== 'disabled');
    const canUseLeaderboardAnalysis = $derived(llmReady && authStore.canModify);

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
            const naming = getBirdNames(item as any, showCommon, preferSci);
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

    $effect(() => {
        const _deps = [span];
        void loadLeaderboard();
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
            .map((item) => item.species)
            .filter(Boolean)
            .slice(0, 3);
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
            console.error('Failed to load leaderboard species', e);
        }

        const compareSpecies = selectCompareSpecies(species);
        const [timelineResult, heatmapResult] = await Promise.allSettled([
            fetchDetectionsTimelineSpan(span, { includeWeather: true, compareSpecies }),
            fetchDetectionsActivityHeatmapSpan(span),
        ]);

        if (timelineResult.status === 'fulfilled') {
            timeline = timelineResult.value;
        } else {
            timeline = null;
            console.error('Failed to load leaderboard timeline', timelineResult.reason);
        }

        if (heatmapResult.status === 'fulfilled') {
            activityHeatmap = heatmapResult.value;
        } else {
            activityHeatmap = null;
            console.error('Failed to load activity heatmap', heatmapResult.reason);
        }

        loading = false;
    }

    async function loadSpeciesInfo(speciesName: string) {
        if (
            !speciesName ||
            speciesName === "Unknown Bird" ||
            speciesInfoCache[speciesName] ||
            speciesInfoPending[speciesName]
        ) {
            return;
        }
        speciesInfoPending = { ...speciesInfoPending, [speciesName]: true };
        try {
            const info = await fetchSpeciesInfo(speciesName);
            speciesInfoCache = { ...speciesInfoCache, [speciesName]: info };
        } catch {
            // ignore fetch errors
        } finally {
            const { [speciesName]: _discarded, ...rest } = speciesInfoPending;
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

    function getMedal(index: number): string {
        if (index === 0) return '🥇';
        if (index === 1) return '🥈';
        if (index === 2) return '🥉';
        return '';
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

    let heroInfo = $derived(summaryEnabled && topByCount ? speciesInfoCache[topByCount.species] : null);
    let heroBlurb = $derived(getHeroBlurb(heroInfo));
    let heroSource = $derived(getHeroSource(heroInfo));
    let risingInfo = $derived(summaryEnabled && topByTrend ? speciesInfoCache[topByTrend.species] : null);
    let recentInfo = $derived(summaryEnabled && mostRecent ? speciesInfoCache[mostRecent.species] : null);

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
    let chartModeLabel = $derived(() => {
        if (chartViewMode === 'line') return $_('leaderboard.chart_line', { default: 'Line' });
        if (chartViewMode === 'bar') return $_('leaderboard.chart_bar', { default: 'Histogram' });
        return $_('leaderboard.chart_auto', { default: 'Auto' });
    });
    let isDark = $derived(() => themeStore.isDark);
    let temperatureUnit = $derived(settingsStore.settings?.location_temperature_unit ?? 'celsius');
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

    function weatherValue(bucketStart: string, key: string): number | null {
        const w: any = weatherByBucket().get(bucketStart);
        const val = w?.[key];
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
            chartModeLabel(),
            leaderboardAnalysisSubtitle
        ].filter(Boolean).join(' • ');
    });

    let chartOptions = $derived(() => {
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

        const series: any[] = [];
        const primaryColor = '#16a34a';
        const smoothColor = '#0f766e';
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
            y: weatherValue(point.bucket_start, 'wind_avg')
        }));

        const hasTemperatureSeries = hasWeather() && showTemperature && temperatureData.some((p) => p.y !== null);
        const hasWindSeries = hasWeather() && showWind && windData.some((p) => p.y !== null);

        if (showRawSeries) {
            series.push({
                name: primaryName,
                type: detectionUsesBars() ? 'bar' : 'area',
                color: primaryColor,
                data: rawData
            });
        }

        if (showSmoothSeries) {
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
        const tickAmount = indexedPoints.length > 1 ? Math.min(6, indexedPoints.length) : undefined;
        const yAxes: any[] = [
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
                labels: {
                    style: { fontSize: '10px', colors: '#f59e0b' },
                    formatter: (value: number) => formatTemperature(value, temperatureUnit as any)
                }
            });
        }
        if (hasWindSeries) {
            yAxes.push({
                // Apex handles dynamic remapping more reliably when seriesName is array form.
                seriesName: [windName],
                opposite: true,
                labels: {
                    style: { fontSize: '10px', colors: '#0ea5e9' },
                    formatter: (value: number) => `${Math.round(value)} ${$_('common.unit_kmh', { default: 'km/h' })}`
                }
            });
        }

        return {
            chart: {
                type: detectionUsesBars() ? 'bar' : 'line',
                height: 260,
                width: '100%',
                toolbar: { show: false },
                zoom: { enabled: false },
                animations: { enabled: true, easing: 'easeinout', speed: 500 }
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
                    borderRadius: 5,
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
                labels: { rotate: 0, style: { fontSize: '10px', colors: '#94a3b8' } }
            },
            yaxis: yAxes,
            tooltip: {
                theme: isDark() ? 'dark' : 'light',
                x: {
                    format: timeline?.bucket === 'hour'
                        ? 'MMM dd HH:mm'
                        : (timeline?.bucket === 'month' ? 'MMM yyyy' : 'MMM dd HH:mm')
                },
                y: {
                    formatter: (value: number, opts: any) => {
                        const seriesName = opts?.w?.globals?.seriesNames?.[opts.seriesIndex] ?? '';
                        if (seriesName === temperatureName) return formatTemperature(value, temperatureUnit as any);
                        if (seriesName === windName) return `${Math.round(value)} ${$_('common.unit_kmh', { default: 'km/h' })}`;
                        if (seriesName === smoothName || seriesName === primaryName) return formatMetricValue(value);
                        return `${Math.round(value)} ${$_('leaderboard.metric_detections', { default: 'detections' }).toLowerCase()}`;
                    }
                }
            },
            legend: {
                show: series.length > 1,
                position: 'top',
                horizontalAlign: 'right',
                fontSize: '10px',
                markers: { fillColors: seriesColors },
                labels: { colors: isDark() ? '#94a3b8' : '#64748b' }
            },
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

    const comparePalette = ['#10b981', '#0ea5e9', '#6366f1', '#f59e0b'];
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

    let compareSeries = $derived(() => {
        if (!timeline?.compare_series?.length) return [];
        const points = timelinePoints();
        if (!points.length) return [];
        const displayNames = new Map(processedSpecies().map((item) => [item.species, item.displayName] as const));
        return timeline.compare_series
            .map((entry, index) => {
                const valuesByBucket = new Map(
                    (entry.points || []).map((point) => [point.bucket_start, Math.max(0, Number(point.count ?? 0))] as const)
                );
                const data = points
                    .map((point) => {
                        const x = Date.parse(point.bucket_start);
                        if (!Number.isFinite(x)) return null;
                        return {
                            x,
                            y: valuesByBucket.get(point.bucket_start) ?? 0
                        };
                    })
                    .filter((point): point is { x: number; y: number } => !!point);

                if (!data.length) return null;
                return {
                    name: displayNames.get(entry.species) ?? entry.species,
                    type: 'line',
                    color: comparePalette[index % comparePalette.length],
                    data
                };
            })
            .filter((series): series is { name: string; type: 'line'; color: string; data: Array<{ x: number; y: number }> } => !!series);
    });

    let compareHasData = $derived(() => compareSeries().some((series) => series.data.some((point) => point.y > 0)));
    let comparePeak = $derived(() => compareSeries().reduce((peak, series) => {
        const seriesPeak = series.data.reduce((max, point) => Math.max(max, point.y), 0);
        return Math.max(peak, seriesPeak);
    }, 0));
    let compareChartOptions = $derived(() => ({
        chart: {
            type: 'line',
            height: 220,
            width: '100%',
            toolbar: { show: false },
            zoom: { enabled: false },
            animations: { enabled: true, easing: 'easeinout', speed: 450 }
        },
        series: compareSeries(),
        dataLabels: { enabled: false },
        stroke: { curve: 'smooth', width: 2 },
        markers: { size: 0, hover: { size: 4 } },
        grid: {
            borderColor: 'rgba(148,163,184,0.18)',
            strokeDashArray: 3,
            padding: { left: 8, right: 8, top: 8, bottom: 2 }
        },
        xaxis: {
            type: 'datetime',
            tickAmount: Math.min(6, timelinePoints().length || 0),
            labels: { rotate: 0, style: { fontSize: '10px', colors: '#94a3b8' } }
        },
        yaxis: {
            min: 0,
            forceNiceScale: true,
            labels: {
                style: { fontSize: '10px', colors: '#94a3b8' },
                formatter: (value: number) => formatMetricValue(value)
            }
        },
        tooltip: {
            theme: isDark() ? 'dark' : 'light',
            x: {
                format: timeline?.bucket === 'hour'
                    ? 'MMM dd HH:mm'
                    : (timeline?.bucket === 'month' ? 'MMM yyyy' : 'MMM dd HH:mm')
            },
            y: {
                formatter: (value: number) => formatMetricValue(value)
            }
        },
        legend: {
            show: compareSeries().length > 0,
            position: 'top',
            horizontalAlign: 'right',
            fontSize: '10px',
            labels: { colors: isDark() ? '#94a3b8' : '#64748b' }
        }
    }));

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
    let heatmapChartOptions = $derived(() => {
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
                animations: { enabled: true, easing: 'easeinout', speed: 350 }
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

    function stableStringify(value: any): string {
        if (value === null || typeof value !== 'object') {
            return JSON.stringify(value);
        }
        if (Array.isArray(value)) {
            return `[${value.map(stableStringify).join(',')}]`;
        }
        const keys = Object.keys(value).sort();
        return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(value[k])}`).join(',')}}`;
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
            points: timeline?.points?.length ?? 0
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
            const chartInstance = (chartEl as any).__apexchart;
            const dataUri = await chartInstance?.dataURI();
            const imageBase64 = dataUri?.imgURI ?? null;
            if (!imageBase64) {
                throw new Error('Unable to capture chart image');
            }
            const result = await analyzeLeaderboardGraph({
                config: {
                    timeframe: `${spanLabel()} (${formatRangeCompact(timeline.window_start, timeline.window_end)})`,
                    total_count: timeline.total_count,
                    series: [metricLabel()],
                    notes: `Metric: ${metricLabel()}. Grouped by ${bucketLabel(timeline.bucket)}. Trend mode: ${trendMode}.`
                },
                image_base64: imageBase64,
                force,
                config_key: key
            });
            leaderboardAnalysis = result.analysis;
            leaderboardAnalysisTimestamp = result.analysis_timestamp;
        } catch (e: any) {
            leaderboardAnalysisError = e?.message || 'Failed to analyze chart';
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

<div class="space-y-6">
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <h2 class="text-2xl font-bold text-slate-900 dark:text-white">{$_('leaderboard.title')}</h2>

        <div class="flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/50 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M3.5 14.2c1.6-1.8 3.2-2.7 4.8-2.7 1.9 0 3.4 1.1 4.3 3.2"></path>
                    <path d="M6.2 9.1a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"></path>
                    <path d="M13.9 10.4a1.7 1.7 0 1 0 0-3.4 1.7 1.7 0 0 0 0 3.4z"></path>
                </svg>
                {$_('leaderboard.species_count', { values: { count: leaderboardSpecies().length } })}
            </span>
            <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/50 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M3 14l4-4 3 2 7-8"></path>
                </svg>
                {$_('leaderboard.detections_count', { values: { count: totalDetections.toLocaleString() } })}
            </span>

            <button
                onclick={loadLeaderboard}
                disabled={loading}
                class="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/50 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 disabled:opacity-50"
            >
                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path d="M16 10a6 6 0 1 1-1.8-4.3"></path>
                    <path d="M16 4v4h-4"></path>
                </svg>
                {$_('common.refresh')}
            </button>
        </div>
    </div>

    <!-- Rank + Filters -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div class="flex flex-wrap gap-2">
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

        <label class="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 select-none">
            <input
                type="checkbox"
                class="rounded border-slate-300 dark:border-slate-600 text-emerald-600 focus:ring-emerald-500"
                bind:checked={includeUnknownBird}
            />
            {$_('leaderboard.include_unknown')}
        </label>
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
        <div class="card-base rounded-3xl p-12 text-center">
            <span class="text-6xl mb-4 block">🐦</span>
            <h3 class="text-lg font-semibold text-slate-900 dark:text-white mb-2">{$_('leaderboard.no_species')}</h3>
            <p class="text-slate-500 dark:text-slate-400">
                {species.length > 0 && !includeUnknownBird
                    ? $_('leaderboard.only_unknown_desc')
                    : $_('leaderboard.no_species_desc')}
            </p>
        </div>
    {:else}
        <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div class="xl:col-span-2 card-base rounded-3xl p-6 md:p-8 relative overflow-hidden">
                {#if heroInfo?.thumbnail_url}
                    <div
                        class="absolute inset-0 bg-center bg-cover blur-md scale-100 opacity-25 dark:opacity-20"
                        style={`background-image: url('${heroInfo.thumbnail_url}');`}
                    ></div>
                {/if}
                <div class="absolute inset-0 bg-gradient-to-br from-emerald-50 via-transparent to-teal-50 dark:from-emerald-950/30 dark:to-teal-900/20 pointer-events-none"></div>
                <div class="relative space-y-6">
                    <div class="flex items-start justify-between gap-4">
                        <div>
                            <p class="text-[11px] uppercase tracking-[0.24em] font-black text-emerald-600 dark:text-emerald-300">
                                {$_('leaderboard.featured')}
                            </p>
                            <h3 class="text-2xl md:text-3xl font-black text-slate-900 dark:text-white mt-2">
                                {topByCount?.displayName || '—'}
                            </h3>
                            {#if topByCount?.subName}
                                <p class="text-xs italic text-slate-500 dark:text-slate-400">
                                    {topByCount.subName}
                                </p>
                            {/if}
                            {#if heroBlurb}
                                <p class="text-sm text-slate-600 dark:text-slate-300 mt-3 max-w-xl">
                                    {heroBlurb}
                                </p>
                                {#if heroSource}
                                    <a
                                        href={heroSource.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="inline-flex items-center gap-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300 hover:text-emerald-600 dark:hover:text-emerald-200 mt-2"
                                    >
                                        {heroSource.source === 'wikipedia'
                                            ? $_('actions.read_more_wikipedia')
                                            : $_('actions.read_more_source', { values: { source: $_('common.source_inaturalist', { default: 'iNaturalist' }) } })}
                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 3h7v7m0-7L10 14m-1 7h11a2 2 0 002-2V9" />
                                        </svg>
                                    </a>
                                {/if}
                            {/if}
                        </div>
                        <button
                            type="button"
                            onclick={() => topByCount && (selectedSpecies = topByCount.species)}
                            class="px-4 py-2 rounded-2xl bg-emerald-500/90 text-white text-xs font-black uppercase tracking-widest shadow-md hover:bg-emerald-500"
                        >
                            {$_('leaderboard.view_details')}
                        </button>
                    </div>

                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{selectedCountLabel()}</p>
                            <p class="text-2xl font-black text-slate-900 dark:text-white">
                                {topByCount?.count?.toLocaleString() || '—'}
                            </p>
                        </div>
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.trend')}</p>
                            <p class="text-xl font-black text-slate-900 dark:text-white">{span === 'all' ? '—' : formatTrend(topByCount?.delta, topByCount?.percent)}</p>
                        </div>
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.cameras')}</p>
                            <p class="text-xl font-black text-slate-900 dark:text-white">{(topByCount?.camera_count ?? 0).toLocaleString()}</p>
                        </div>
                        <div class="rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-3">
                            <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.last_seen')}</p>
                            <p class="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                {formatDate(topByCount?.last_seen)}
                            </p>
                        </div>
                    </div>

                    <div class="flex flex-wrap gap-3 text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                        {#if span !== 'all'}
                            <span class="px-3 py-1 rounded-full bg-emerald-100/80 dark:bg-emerald-900/30">
                                {$_('leaderboard.trend')}: {formatTrend(topByCount?.delta, topByCount?.percent)}
                            </span>
                        {/if}
                        <span class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800/60">
                            {$_('leaderboard.cameras')}:{' '}{topByCount?.camera_count || 0}
                        </span>
                        <span class="px-3 py-1 rounded-full bg-slate-100 dark:bg-slate-800/60">
                            {$_('leaderboard.avg_confidence')}: {(topByCount?.avg_confidence ?? 0).toFixed(2)}
                        </span>
                    </div>
                </div>
            </div>

            <div class="space-y-3">
                <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                    {#if heroInfo?.thumbnail_url}
                        <div
                            class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                            style={`background-image: url('${heroInfo.thumbnail_url}');`}
                        ></div>
                    {/if}
                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.most_active')}</p>
                    <div class="flex items-center gap-3 mt-2">
                        {#if heroInfo?.thumbnail_url}
                            <img
                                src={heroInfo.thumbnail_url}
                                alt={topByCount?.displayName || 'Species'}
                                class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                            />
                        {:else}
                            <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                        {/if}
                        <div class="relative">
                            <p class="text-lg font-black text-slate-900 dark:text-white">{topByCount?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{spanLabel()}: {(topByCount?.count || 0).toLocaleString()}</p>
                        </div>
                    </div>
                </div>
                {#if span !== 'all'}
                    <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                        {#if risingInfo?.thumbnail_url}
                            <div
                                class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                                style={`background-image: url('${risingInfo.thumbnail_url}');`}
                            ></div>
                        {/if}
                        <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.rising')}</p>
                        <div class="flex items-center gap-3 mt-2">
                            {#if risingInfo?.thumbnail_url}
                                <img
                                    src={risingInfo.thumbnail_url}
                                    alt={topByTrend?.displayName || 'Species'}
                                    class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                                />
                            {:else}
                                <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                            {/if}
                            <div class="relative">
                                <p class="text-lg font-black text-slate-900 dark:text-white">{topByTrend?.displayName || '—'}</p>
                                <p class="text-xs text-slate-500">{$_('leaderboard.trend')}: {formatTrend(topByTrend?.delta, topByTrend?.percent)}</p>
                            </div>
                        </div>
                    </div>
                {/if}
                <div class="card-base rounded-2xl p-4 relative overflow-hidden">
                    {#if recentInfo?.thumbnail_url}
                        <div
                            class="absolute inset-0 bg-center bg-cover blur-lg scale-105 opacity-25 dark:opacity-20"
                            style={`background-image: url('${recentInfo.thumbnail_url}');`}
                        ></div>
                    {/if}
                    <p class="text-[10px] uppercase tracking-widest text-slate-400">{$_('leaderboard.most_recent')}</p>
                    <div class="flex items-center gap-3 mt-2">
                        {#if recentInfo?.thumbnail_url}
                            <img
                                src={recentInfo.thumbnail_url}
                                alt={mostRecent?.displayName || 'Species'}
                                class="w-10 h-10 rounded-2xl object-cover shadow-md border border-white/70"
                            />
                        {:else}
                            <div class="w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-lg">🐦</div>
                        {/if}
                        <div class="relative">
                            <p class="text-lg font-black text-slate-900 dark:text-white">{mostRecent?.displayName || '—'}</p>
                            <p class="text-xs text-slate-500">{formatDate(mostRecent?.last_seen)}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="card-base rounded-3xl p-6 md:p-8 relative overflow-hidden flex flex-col">
            {#if heroInfo?.thumbnail_url}
                <div
                    class="absolute inset-0 bg-center bg-cover blur-3xl scale-110 opacity-20 dark:opacity-15"
                    style={`background-image: url('${heroInfo.thumbnail_url}');`}
                ></div>
            {/if}
            <div class="absolute inset-0 bg-gradient-to-br from-slate-50 via-transparent to-emerald-50 dark:from-slate-900/50 dark:to-emerald-900/20 pointer-events-none"></div>
            <div class="relative flex flex-col flex-1">
                <div class="flex flex-col gap-4">
                    <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                        <div>
                            <p class="text-[10px] uppercase tracking-[0.3em] font-black text-slate-500 dark:text-slate-300">
                                {spanLabel()}
                            </p>
                            <h3 class="text-xl md:text-2xl font-black text-slate-900 dark:text-white">{$_('leaderboard.detections_over_time')}</h3>
                            <div class="mt-2 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                                <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                                    <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                        <rect x="3" y="4" width="14" height="13" rx="2"></rect>
                                        <path d="M3 8h14"></path>
                                    </svg>
                                    {formatRangeCompact(timeline?.window_start, timeline?.window_end)}
                                </span>
                                <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                                    <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                        <path d="M4 10h12M4 6h12M4 14h7"></path>
                                    </svg>
                                    {bucketLabel(timeline?.bucket)}
                                </span>
                                <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                                    <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                        <path d="M4 14l4-4 3 2 5-6"></path>
                                    </svg>
                                    {metricLabel()}
                                </span>
                            </div>
                        </div>
                        <div class="flex flex-wrap items-center gap-3 text-sm font-semibold text-slate-500 dark:text-slate-400">
                            <span class="text-[11px] font-black text-slate-500 dark:text-slate-300">
                                {$_('leaderboard.detections_count', { values: { count: timeline?.total_count?.toLocaleString() || '0' } })}
                            </span>
                            {#if canUseLeaderboardAnalysis}
                                <button
                                    type="button"
                                    class="px-3 py-1.5 rounded-full border border-emerald-200/70 dark:border-emerald-800/60 text-[10px] font-black uppercase tracking-widest text-emerald-700 dark:text-emerald-300 bg-emerald-50/70 dark:bg-emerald-900/20 hover:bg-emerald-100/70 dark:hover:bg-emerald-900/40 disabled:opacity-60 disabled:cursor-not-allowed"
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

                    <div class="flex flex-wrap items-center gap-2 text-[10px]">
                        <div class="inline-flex items-center rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/50 p-1">
                            <button
                                type="button"
                                class="px-2 py-1 font-black uppercase tracking-widest rounded-full transition-colors {trendMode === 'off' ? 'bg-emerald-500 text-white' : 'text-slate-500 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                                aria-pressed={trendMode === 'off'}
                                onclick={() => trendMode = 'off'}
                            >
                                {$_('leaderboard.trend_off', { default: 'Raw' })}
                            </button>
                            <button
                                type="button"
                                class="px-2 py-1 font-black uppercase tracking-widest rounded-full transition-colors {trendMode === 'smooth' ? 'bg-emerald-500 text-white' : 'text-slate-500 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                                aria-pressed={trendMode === 'smooth'}
                                onclick={() => trendMode = 'smooth'}
                            >
                                {$_('leaderboard.trend_smooth', { default: 'Smooth' })}
                            </button>
                            <button
                                type="button"
                                class="px-2 py-1 font-black uppercase tracking-widest rounded-full transition-colors {trendMode === 'both' ? 'bg-emerald-500 text-white' : 'text-slate-500 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                                aria-pressed={trendMode === 'both'}
                                onclick={() => trendMode = 'both'}
                            >
                                {$_('leaderboard.trend_both', { default: 'Both' })}
                            </button>
                        </div>
                        <div class="inline-flex items-center rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/50 p-1">
                            <button
                                type="button"
                                class="px-2 py-1 font-black uppercase tracking-widest rounded-full transition-colors {chartViewMode === 'auto' ? 'bg-emerald-500 text-white' : 'text-slate-500 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                                aria-pressed={chartViewMode === 'auto'}
                                onclick={() => chartViewMode = 'auto'}
                            >
                                {$_('leaderboard.chart_auto', { default: 'Auto' })}
                            </button>
                            <button
                                type="button"
                                class="px-2 py-1 font-black uppercase tracking-widest rounded-full transition-colors {chartViewMode === 'line' ? 'bg-emerald-500 text-white' : 'text-slate-500 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                                aria-pressed={chartViewMode === 'line'}
                                onclick={() => chartViewMode = 'line'}
                            >
                                {$_('leaderboard.chart_line', { default: 'Line' })}
                            </button>
                            <button
                                type="button"
                                class="px-2 py-1 font-black uppercase tracking-widest rounded-full transition-colors {chartViewMode === 'bar' ? 'bg-emerald-500 text-white' : 'text-slate-500 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'}"
                                aria-pressed={chartViewMode === 'bar'}
                                onclick={() => chartViewMode = 'bar'}
                            >
                                {$_('leaderboard.chart_bar', { default: 'Histogram' })}
                            </button>
                        </div>
                    </div>

                </div>

                <div class="mt-6 w-full flex-1 min-h-[140px] max-h-[240px]">
                    {#if timeline?.points?.length}
                        {#key `${span}-${timeline.total_count}-${timeline.bucket}-${trendMode}-${chartViewMode}-${showTemperature}-${showWind}-${showPrecip}`}
                            <div use:chart={chartOptions() as any} bind:this={chartEl} class="w-full h-[240px]"></div>
                        {/key}
                    {:else}
                        <div class="h-full w-full rounded-2xl bg-slate-100 dark:bg-slate-800/60 animate-pulse"></div>
                    {/if}
                </div>

                <div class="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                    <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/45 px-2 py-1">
                        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M4 14h12"></path>
                            <path d="M7 14V9M10 14V6M13 14v-3"></path>
                        </svg>
                        {$_('leaderboard.total', { default: 'Total' })}: {timeline?.total_count?.toLocaleString() || '0'}
                    </span>
                    <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/45 px-2 py-1">
                        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M4 14l4-4 3 2 5-6"></path>
                        </svg>
                        {$_('leaderboard.metric_peak', { default: 'Peak' })}: {formatMetricValue(metricPeak())}
                    </span>
                    <span class="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/45 px-2 py-1">
                        <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                            <path d="M4 10h12M4 6h12M4 14h12"></path>
                        </svg>
                        {$_('leaderboard.metric_avg', { default: 'Avg' })}: {formatMetricValue(metricAvg())}
                    </span>
                </div>
                {#if canUseLeaderboardAnalysis && (leaderboardAnalysisLoading || leaderboardAnalysisError || leaderboardAnalysis)}
                    <div class="mt-4 rounded-2xl border border-slate-200/70 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 px-4 py-3 text-sm text-slate-600 dark:text-slate-300 shadow-sm">
                        <div class="flex flex-wrap items-center justify-between gap-2 text-[10px] uppercase tracking-widest font-black text-slate-400">
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
                                        <p class="text-[10px] font-black uppercase tracking-[0.2em] text-emerald-600 dark:text-emerald-300">{block.text}</p>
                                    {:else}
                                        <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">{block.text}</p>
                                    {/if}
                                {/each}
                            </div>
                        {/if}
                    </div>
                {/if}
                <div class="mt-4 flex flex-wrap items-center gap-3 text-[10px] text-slate-400">
                    <div class="flex items-center gap-2">
                        <button
                            type="button"
                            onclick={() => showTemperature = !showTemperature}
                            disabled={!hasWeather()}
                            class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 disabled:opacity-45 disabled:cursor-not-allowed"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M10 4a2 2 0 0 0-4 0v6.4a3.5 3.5 0 1 0 4 0V4z"></path>
                                <path d="M8 9.5V4"></path>
                            </svg>
                            {showTemperature ? $_('leaderboard.hide_temperature') : $_('leaderboard.show_temperature')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showWind = !showWind}
                            disabled={!hasWeather()}
                            class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 disabled:opacity-45 disabled:cursor-not-allowed"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M3 8h9a2 2 0 1 0-2-2"></path>
                                <path d="M3 12h12a2 2 0 1 1-2 2"></path>
                            </svg>
                            {showWind ? $_('leaderboard.hide_wind') : $_('leaderboard.show_wind')}
                        </button>
                        <button
                            type="button"
                            onclick={() => showPrecip = !showPrecip}
                            disabled={!hasWeather()}
                            class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-slate-200/70 dark:border-slate-700/60 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 disabled:opacity-45 disabled:cursor-not-allowed"
                        >
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M6 9a4 4 0 1 1 7.5-1.8A2.8 2.8 0 1 1 14 13H6.5"></path>
                                <path d="M7 14.5v2M10 14.5v2M13 14.5v2"></path>
                            </svg>
                            {showPrecip
                                ? $_('leaderboard.hide_precip', { default: 'Hide precipitation' })
                                : $_('leaderboard.show_precip', { default: 'Show precipitation' })}
                        </button>
                    </div>
                    {#if showPrecip && hasWeather()}
                        <span class="inline-flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400">
                            <span>{$_('leaderboard.band_intensity', { default: 'Band intensity' })}</span>
                            <span class="inline-flex items-center gap-1">
                                <span class="h-2 w-2 rounded-sm bg-sky-300/45 border border-sky-300/60"></span>
                                {$_('leaderboard.band_low', { default: 'Low' })}
                            </span>
                            <span class="inline-flex items-center gap-1">
                                <span class="h-2 w-2 rounded-sm bg-sky-300/65 border border-sky-300/75"></span>
                                {$_('leaderboard.band_medium', { default: 'Med' })}
                            </span>
                            <span class="inline-flex items-center gap-1">
                                <span class="h-2 w-2 rounded-sm bg-sky-300/85 border border-sky-300/90"></span>
                                {$_('leaderboard.band_high', { default: 'High' })}
                            </span>
                        </span>
                    {/if}
                    <span class="text-slate-400/70">{$_('common.grouped_by', { default: 'Grouped by' })}: {bucketLabel(timeline?.bucket)}</span>
                    {#if !hasWeather()}
                        <span class="text-slate-500 dark:text-slate-400">
                            {weatherOverlayEligible()
                                ? $_('leaderboard.weather_overlay_no_data', { default: 'No weather data in this range yet. Run Weather Backfill in Settings > Data.' })
                                : $_('leaderboard.weather_overlay_range_limited', { default: 'Weather overlays are available on Day/Week/Month ranges up to ~31 days.' })}
                        </span>
                    {/if}
                </div>

                {#if timeline?.sunrise_range || timeline?.sunset_range}
                    <div class="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                        {#if timeline?.sunrise_range}
                            <span class="inline-flex items-center gap-1 rounded-full border border-amber-200/60 dark:border-amber-700/50 bg-amber-50/60 dark:bg-amber-900/20 px-2 py-1 text-amber-700 dark:text-amber-300">
                                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                    <path d="M4 12a6 6 0 0 1 12 0"></path>
                                    <path d="M3 14h14M10 4v3M6.5 6.5l1.4 1.4M13.5 6.5l-1.4 1.4"></path>
                                </svg>
                                {$_('leaderboard.sunrise')}: {timeline.sunrise_range}
                            </span>
                        {/if}
                        {#if timeline?.sunset_range}
                            <span class="inline-flex items-center gap-1 rounded-full border border-orange-200/60 dark:border-orange-700/50 bg-orange-50/60 dark:bg-orange-900/20 px-2 py-1 text-orange-700 dark:text-orange-300">
                                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                    <path d="M4 12a6 6 0 0 1 12 0"></path>
                                    <path d="M3 14h14M10 9v3M6.5 8.5l1.4 1.4M13.5 8.5l-1.4 1.4"></path>
                                </svg>
                                {$_('leaderboard.sunset')}: {timeline.sunset_range}
                            </span>
                        {/if}
                    </div>
                {/if}
            </div>
        </div>

        <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div class="card-base rounded-3xl p-6 md:p-7 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-sky-50 via-transparent to-indigo-50 dark:from-sky-950/25 dark:to-indigo-900/15 pointer-events-none"></div>
                <div class="relative">
                    <div class="flex items-start justify-between gap-3">
                        <div class="flex items-start gap-2.5">
                            <div class="h-8 w-8 rounded-xl border border-sky-200/80 dark:border-sky-700/60 bg-sky-100/80 dark:bg-sky-900/30 flex items-center justify-center text-sky-700 dark:text-sky-300">
                                <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                    <path d="M3 14l4-4 3 2 7-8"></path>
                                </svg>
                            </div>
                            <div>
                                <p class="text-[10px] uppercase tracking-[0.26em] font-black text-sky-600 dark:text-sky-300">
                                    {$_('leaderboard.species_compare_title', { default: 'Species Compare' })}
                                </p>
                                <h4 class="text-lg md:text-xl font-black text-slate-900 dark:text-white mt-1">
                                    {$_('leaderboard.species_compare_subtitle', { default: 'Top species over time' })}
                                </h4>
                            </div>
                        </div>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M3 14l4-4 3 2 7-8"></path>
                            </svg>
                            {compareSeries().length}
                        </span>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M4 10h12M4 6h12M4 14h7"></path>
                            </svg>
                            {bucketLabel(timeline?.bucket)}
                        </span>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <path d="M4 14l4-4 3 2 5-6"></path>
                            </svg>
                            {$_('leaderboard.metric_peak', { default: 'Peak' })}: {formatMetricValue(comparePeak())}
                        </span>
                    </div>

                    <div class="mt-4 min-h-[220px]">
                        {#if compareSeries().length}
                            {#key `${span}-${timeline?.bucket}-${timeline?.total_count}-${compareSeries().length}-${isDark()}`}
                                <div use:chart={compareChartOptions() as any} class="w-full h-[220px]"></div>
                            {/key}
                        {:else}
                            <div class="h-[220px] w-full rounded-2xl border border-dashed border-slate-300/80 dark:border-slate-700/70 bg-slate-50/70 dark:bg-slate-900/35 flex items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                                {$_('leaderboard.no_compare_data', { default: 'Not enough data for comparison yet.' })}
                            </div>
                        {/if}
                    </div>

                    {#if compareSeries().length && !compareHasData()}
                        <p class="mt-3 text-xs text-slate-500 dark:text-slate-400">
                            {$_('leaderboard.compare_zero_activity', { default: 'Compared species are selected, but activity in this window is currently zero.' })}
                        </p>
                    {/if}
                </div>
            </div>

            <div class="card-base rounded-3xl p-6 md:p-7 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-cyan-50 via-transparent to-blue-50 dark:from-cyan-950/20 dark:to-blue-900/15 pointer-events-none"></div>
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
                                <p class="text-[10px] uppercase tracking-[0.26em] font-black text-cyan-600 dark:text-cyan-300">
                                    {$_('leaderboard.activity_heatmap_title', { default: 'Activity Heatmap' })}
                                </p>
                                <h4 class="text-lg md:text-xl font-black text-slate-900 dark:text-white mt-1">
                                    {$_('leaderboard.activity_heatmap_subtitle', { default: 'Hour x weekday activity' })}
                                </h4>
                            </div>
                        </div>
                        <span class="inline-flex items-center gap-1 rounded-full border border-slate-200/80 dark:border-slate-700/70 bg-white/80 dark:bg-slate-900/40 px-2 py-1 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
                            <svg class="h-3 w-3" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                <rect x="3" y="4" width="14" height="12" rx="2"></rect>
                                <path d="M3 9h14M8 4v12M13 4v12"></path>
                            </svg>
                            {formatMetricValue(activityHeatmap?.max_cell_count ?? 0)}
                        </span>
                    </div>

                    <div class="mt-3 flex flex-wrap items-center gap-2 text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-300">
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
                                <div use:chart={heatmapChartOptions() as any} class="w-full h-[260px]"></div>
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

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
            {#each sortedSpecies().slice(0, 3) as topSpecies, index}
                <button
                    type="button"
                    onclick={() => selectedSpecies = topSpecies.species}
                    class="card-base card-interactive text-left rounded-3xl p-5 pt-8 transition-all duration-300 relative group/card"
                    title={topSpecies.species === "Unknown Bird" ? $_('leaderboard.unidentified_desc') : ""}
                >
                    <!-- Overlapping Thumbnail -->
                    <div class="absolute -top-6 left-6 w-16 h-16 rounded-2xl overflow-hidden border-4 border-white dark:border-slate-800 shadow-xl group-hover/card:-translate-y-1 transition-transform duration-300">
                        {#if speciesInfoCache[topSpecies.species]?.thumbnail_url}
                            <img 
                                src={speciesInfoCache[topSpecies.species].thumbnail_url} 
                                alt={topSpecies.displayName}
                                class="w-full h-full object-cover"
                            />
                        {:else}
                            <div class="w-full h-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-2xl">🐦</div>
                        {/if}
                    </div>

                    {#if topSpecies.species === "Unknown Bird"}
                        <div class="absolute top-2 right-2 bg-amber-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-xs font-black shadow-md" title={$_('leaderboard.needs_review')}>
                            ?
                        </div>
                    {/if}
                    <div class="flex items-center gap-3">
                        <span class="text-3xl ml-16">{getMedal(index)}</span>
                        <div class="flex-1 min-w-0">
                            <h4 class="font-semibold text-slate-900 dark:text-white truncate">
                                {topSpecies.displayName}
                            </h4>
                            {#if topSpecies.subName}
                                <p class="text-[10px] italic text-slate-500 dark:text-slate-400 truncate -mt-0.5">
                                    {topSpecies.subName}
                                </p>
                            {/if}
                            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400 mt-2">
                                <span class="font-black text-emerald-600 dark:text-emerald-400">{topSpecies.count.toLocaleString()}</span>
                                <span>•</span>
                                <span>{selectedCountLabel()}: {topSpecies.count.toLocaleString()}</span>
                                {#if span !== 'all'}
                                    <span>•</span>
                                    <span>{$_('leaderboard.trend')}: {formatTrend(topSpecies.delta, topSpecies.percent)}</span>
                                {/if}
                            </div>
                        </div>
                    </div>
                </button>
            {/each}
        </div>

        <div class="card-base rounded-2xl overflow-hidden backdrop-blur-sm">
            <div class="p-4 border-b border-slate-200/80 dark:border-slate-700/50 flex items-center justify-between">
                <h3 class="font-semibold text-slate-900 dark:text-white">{$_('leaderboard.all_species')}</h3>
                <div class="text-xs text-slate-500 dark:text-slate-400">
                    {spanLabel()} ({formatRangeCompact(timeline?.window_start, timeline?.window_end)}) · {totalDetections.toLocaleString()} · {bucketLabel(timeline?.bucket)}
                </div>
            </div>

            <div class="overflow-x-auto" data-testid="leaderboard-table-wrap">
                <table class="min-w-[900px] w-full text-left text-sm" data-testid="leaderboard-table">
                    <thead class="text-[10px] uppercase tracking-widest text-slate-400 bg-slate-50 dark:bg-slate-900/40">
                        <tr>
                            <th class="px-4 py-3">{$_('leaderboard.rank')}</th>
                            <th class="px-4 py-3">{$_('leaderboard.species')}</th>
                            <th class="px-4 py-3 text-right">{selectedCountLabel()}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.trend')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.cameras')}</th>
                            <th class="px-4 py-3 text-right">{$_('leaderboard.avg_confidence')}</th>
                            <th class="px-4 py-3">{$_('leaderboard.last_seen')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each sortedSpecies() as item, index (item.species)}
                            <tr
                                class="border-b border-slate-100/70 dark:border-slate-800/60 hover:bg-slate-50/70 dark:hover:bg-slate-900/30 transition cursor-pointer"
                                role="button"
                                tabindex="0"
                                aria-label={$_('leaderboard.view_species', { values: { species: item.displayName } })}
                                onclick={() => selectedSpecies = item.species}
                                onkeydown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault();
                                        selectedSpecies = item.species;
                                    }
                                }}
                                title={item.species === "Unknown Bird" ? $_('leaderboard.unidentified_desc') : ""}
                            >
                                <td class="px-4 py-3 font-semibold text-slate-500 dark:text-slate-400">
                                    {getMedal(index) || `#${index + 1}`}
                                </td>
                                <td class="px-4 py-3">
                                    <div class="flex items-center gap-2">
                                        <div class="w-8 h-8 rounded-md overflow-hidden border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 flex-shrink-0">
                                            {#if speciesInfoCache[item.species]?.thumbnail_url}
                                                <img
                                                    src={speciesInfoCache[item.species].thumbnail_url}
                                                    alt={item.displayName}
                                                    class="w-full h-full object-cover"
                                                    loading="lazy"
                                                />
                                            {:else}
                                                <div class="w-full h-full flex items-center justify-center text-[11px] text-slate-500 dark:text-slate-300">
                                                    🐦
                                                </div>
                                            {/if}
                                        </div>
                                        <div class="min-w-0">
                                            <div class="flex items-center gap-2">
                                                <span class="font-semibold text-slate-900 dark:text-white truncate">
                                                    {item.displayName}
                                                </span>
                                                {#if item.species === "Unknown Bird"}
                                                    <span class="inline-flex items-center justify-center bg-amber-500 text-white rounded-full w-5 h-5 text-[10px] font-black" title={$_('leaderboard.needs_review')}>?</span>
                                                {/if}
                                            </div>
                                            {#if item.subName}
                                                <div class="text-[10px] italic text-slate-500 dark:text-slate-400 truncate">
                                                    {item.subName}
                                                </div>
                                            {/if}
                                        </div>
                                    </div>
                                </td>
                                <td class="px-4 py-3 text-right font-bold text-slate-700 dark:text-slate-300">
                                    {item.count.toLocaleString()}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {span === 'all' ? '—' : formatTrend(item.delta, item.percent)}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {(item.camera_count ?? 0).toLocaleString()}
                                </td>
                                <td class="px-4 py-3 text-right text-slate-600 dark:text-slate-300">
                                    {(item.avg_confidence ?? 0).toFixed(2)}
                                </td>
                                <td class="px-4 py-3 text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                    {formatDate(item.last_seen)}
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        </div>
    {/if}
</div>

<!-- Species Detail Modal -->
{#if selectedSpecies}
    <SpeciesDetailModal
        speciesName={selectedSpecies}
        onclose={() => selectedSpecies = null}
    />
{/if}
