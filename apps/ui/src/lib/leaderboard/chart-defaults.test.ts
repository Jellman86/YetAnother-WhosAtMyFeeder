import { describe, expect, it } from 'vitest';

import { defaultLeaderboardChartPreferences } from './chart-defaults';

describe('defaultLeaderboardChartPreferences', () => {
    it('opens the leaderboard timeline as a raw histogram with no smoothing', () => {
        expect(defaultLeaderboardChartPreferences.chartViewMode).toBe('bar');
        expect(defaultLeaderboardChartPreferences.trendMode).toBe('off');
    });
});
