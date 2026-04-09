import { describe, expect, it } from 'vitest';

import { buildLeaderboardAnalysisPromptConfig } from './analysis-config';
import type { DetectionsTimelineSpanResponse } from '../api/leaderboard';

describe('buildLeaderboardAnalysisPromptConfig', () => {
    it('includes weather and sun metadata when the timeline has weather data', () => {
        const timeline: DetectionsTimelineSpanResponse = {
            span: 'month',
            bucket: 'day',
            window_start: '2026-03-10T00:00:00Z',
            window_end: '2026-04-09T00:00:00Z',
            total_count: 123,
            points: [],
            weather: [
                {
                    bucket_start: '2026-04-08T00:00:00Z',
                    temp_avg: 12.4,
                    wind_avg: 8.1,
                    precip_total: 1.5,
                    rain_total: 1.5,
                    snow_total: 0,
                    condition_text: 'Partly cloudy',
                }
            ],
            sunrise_range: '6:12-6:48 AM',
            sunset_range: '7:18-7:52 PM',
        };

        expect(buildLeaderboardAnalysisPromptConfig({
            timeframe: 'Last 30 days',
            metricLabel: 'Detections',
            bucketLabel: 'Daily',
            trendMode: 'off',
            chartDetectionType: 'bar',
            timeline,
        })).toEqual({
            timeframe: 'Last 30 days',
            total_count: 123,
            series: ['Detections'],
            notes: 'Metric: Detections. Grouped by Daily. Trend mode: off. Detection chart: bar.',
            weather_notes: 'Weather data available in this chart: temperature, average wind, precipitation.',
            sunrise_range: '6:12-6:48 AM',
            sunset_range: '7:18-7:52 PM',
        });
    });
});
