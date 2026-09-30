import type { AudioHistoryResponse, AudioSummaryResponse } from '../api';

/** Keep history and its aggregate projection in the same latest-request epoch. */
export function createAudioHistoryLoader(options: {
    fetchHistory: () => Promise<AudioHistoryResponse>;
    fetchSummary: () => Promise<AudioSummaryResponse>;
    begin: () => void;
    apply: (history: AudioHistoryResponse, summary: AudioSummaryResponse) => void;
    clear: () => void;
    fail: (error: unknown) => void;
    finish: () => void;
}) {
    let generation = 0;
    return {
        async load(invalidated = false): Promise<void> {
            const requestGeneration = ++generation;
            if (invalidated) options.clear();
            options.begin();
            try {
                const [history, summary] = await Promise.all([options.fetchHistory(), options.fetchSummary()]);
                if (requestGeneration === generation) options.apply(history, summary);
            } catch (error) {
                if (requestGeneration !== generation) return;
                options.clear();
                options.fail(error);
            } finally {
                if (requestGeneration === generation) options.finish();
            }
        },
        dispose() { generation += 1; }
    };
}
