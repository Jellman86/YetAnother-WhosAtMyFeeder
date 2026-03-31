export type LeaderboardChartViewMode = 'auto' | 'line' | 'bar';
export type LeaderboardTrendMode = 'off' | 'smooth' | 'both';

export const defaultLeaderboardChartPreferences: {
    chartViewMode: LeaderboardChartViewMode;
    trendMode: LeaderboardTrendMode;
} = {
    chartViewMode: 'bar',
    trendMode: 'off'
};
