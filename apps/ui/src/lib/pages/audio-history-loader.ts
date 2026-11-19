import type { AudioActivityHeatmapResponse, AudioHistoryResponse, AudioSummaryResponse } from '../api';

/** The weekday-by-hour grid's own answer: read, or failed on its own while the list was read. */
type AudioHeatmapRead = { heatmap: AudioActivityHeatmapResponse } | { error: unknown };

/**
 * Keep history and its aggregate projections (the summary and the weekday-by-hour grid) in the same
 * latest-request epoch, so every figure on the page counts the same calls and an older answer never
 * lands over a newer one.
 *
 * A failed refresh of the request already on screen keeps that reading and reports it stale; a
 * failed read of anything else (another window, filter or page) withdraws what was shown, because
 * it would otherwise stand in for the answer that was asked for. The grid is a view of the list,
 * not part of it: a grid that cannot be read is reported as its own failure beside a list and
 * summary that were read, never a reason to withdraw them.
 */
export function createAudioHistoryLoader(options: {
    /** Identifies what is being asked for, so a failed refresh can tell it apart from a new question. */
    requestKey?: () => string;
    fetchHistory: () => Promise<AudioHistoryResponse>;
    fetchSummary: () => Promise<AudioSummaryResponse>;
    fetchHeatmap: () => Promise<AudioActivityHeatmapResponse>;
    begin: () => void;
    apply: (history: AudioHistoryResponse, summary: AudioSummaryResponse, heatmap: AudioHeatmapRead) => void;
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
            // Settled on its own, so its failure can neither reject the list's read nor go unhandled.
            const heatmapRead: Promise<AudioHeatmapRead> = options.fetchHeatmap().then(
                (heatmap) => ({ heatmap }),
                (error: unknown) => ({ error })
            );
            try {
                const [history, summary] = await Promise.all([options.fetchHistory(), options.fetchSummary()]);
                const heatmap = await heatmapRead;
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
