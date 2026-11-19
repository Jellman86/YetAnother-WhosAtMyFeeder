import type { AudioActivityHeatmapResponse, AudioHistoryResponse, AudioSummaryResponse } from '../api';

/**
 * Keep history and its aggregate projections (the summary and the weekday-by-hour grid) in the same
 * latest-request epoch, so every figure on the page counts the same calls.
 *
 * A failed refresh of the request already on screen keeps that reading and reports it stale; a
 * failed read of anything else (another window, filter or page) withdraws what was shown, because
 * it would otherwise stand in for the answer that was asked for.
 */
export function createAudioHistoryLoader(options: {
    /** Identifies what is being asked for, so a failed refresh can tell it apart from a new question. */
    requestKey?: () => string;
    fetchHistory: () => Promise<AudioHistoryResponse>;
    fetchSummary: () => Promise<AudioSummaryResponse>;
    fetchHeatmap: () => Promise<AudioActivityHeatmapResponse>;
    begin: () => void;
    apply: (history: AudioHistoryResponse, summary: AudioSummaryResponse, heatmap: AudioActivityHeatmapResponse) => void;
    clear: () => void;
    fail: (error: unknown, state: { stale: boolean }) => void;
    finish: () => void;
}) {
    let generation = 0;
    let shownKey: string | null = null;
    return {
        async load(invalidated = false): Promise<void> {
            const requestGeneration = ++generation;
            const key = options.requestKey?.() ?? '';
            if (invalidated) {
                options.clear();
                shownKey = null;
            }
            options.begin();
            try {
                const [history, summary, heatmap] = await Promise.all([
                    options.fetchHistory(),
                    options.fetchSummary(),
                    options.fetchHeatmap()
                ]);
                if (requestGeneration === generation) {
                    options.apply(history, summary, heatmap);
                    shownKey = key;
                }
            } catch (error) {
                if (requestGeneration !== generation) return;
                const stale = shownKey !== null && shownKey === key;
                if (!stale) {
                    options.clear();
                    shownKey = null;
                }
                options.fail(error, { stale });
            } finally {
                if (requestGeneration === generation) options.finish();
            }
        },
        dispose() { generation += 1; }
    };
}
