import type { DetectionsTimelineSpanResponse } from '../api/leaderboard';

type TrendMode = 'off' | 'smooth' | 'both';

type LeaderboardAnalysisPromptConfigInput = {
    timeframe: string;
    metricLabel: string;
    bucketLabel: string;
    trendMode: TrendMode | string;
    chartDetectionType: 'bar' | 'line';
    timeline: DetectionsTimelineSpanResponse | null;
};

function hasWeatherMetric(
    weather: NonNullable<DetectionsTimelineSpanResponse['weather']>,
    keys: Array<'temp_avg' | 'wind_avg' | 'precip_total' | 'rain_total' | 'snow_total'>
): boolean {
    return weather.some((point) => keys.some((key) => point?.[key] !== null && point?.[key] !== undefined));
}

export function buildLeaderboardAnalysisPromptConfig(
    input: LeaderboardAnalysisPromptConfigInput,
): Record<string, unknown> {
    const { timeframe, metricLabel, bucketLabel, trendMode, chartDetectionType, timeline } = input;
    const weather = timeline?.weather ?? [];
    const weatherMetrics: string[] = [];

    if (weather.length) {
        if (hasWeatherMetric(weather, ['temp_avg'])) weatherMetrics.push('temperature');
        if (hasWeatherMetric(weather, ['wind_avg'])) weatherMetrics.push('average wind');
        if (hasWeatherMetric(weather, ['precip_total', 'rain_total', 'snow_total'])) weatherMetrics.push('precipitation');
    }

    return {
        timeframe,
        total_count: timeline?.total_count ?? 0,
        series: [metricLabel],
        notes: `Metric: ${metricLabel}. Grouped by ${bucketLabel}. Trend mode: ${trendMode}. Detection chart: ${chartDetectionType}.`,
        weather_notes: weatherMetrics.length
            ? `Weather data available in this chart: ${weatherMetrics.join(', ')}.`
            : 'No weather data in this chart range.',
        sunrise_range: timeline?.sunrise_range ?? null,
        sunset_range: timeline?.sunset_range ?? null,
    };
}
