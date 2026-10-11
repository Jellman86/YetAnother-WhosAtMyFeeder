import { describe, expect, it } from 'vitest';
import { formatTerminalBackfillMessage, isBackfillTerminalTransition } from './terminal-message';

describe('formatTerminalBackfillMessage', () => {
    it('prefixes backend terminal messages with the completed backfill kind', () => {
        expect(formatTerminalBackfillMessage('detections', 'Backfill complete', 'Detection backfill complete')).toBe(
            'Detection backfill: Backfill complete'
        );
        expect(formatTerminalBackfillMessage('weather', 'Backfill complete', 'Weather backfill complete')).toBe(
            'Weather backfill: Backfill complete'
        );
    });

    it('uses the kind-specific fallback when the backend did not provide a message', () => {
        expect(formatTerminalBackfillMessage('detections', '', 'Detection backfill complete')).toBe(
            'Detection backfill complete'
        );
        expect(formatTerminalBackfillMessage('weather', null, 'Weather backfill complete')).toBe(
            'Weather backfill complete'
        );
    });
});

describe('isBackfillTerminalTransition', () => {
    const running = { id: 'current-job', status: 'running' };

    it.each(['completed', 'failed'])('does not announce an initially loaded %s job', (status) => {
        expect(isBackfillTerminalTransition(null, { ...running, status })).toBe(false);
    });

    it.each(['completed', 'failed'])('announces a running job changing to %s once', (status) => {
        const terminal = { ...running, status };
        expect(isBackfillTerminalTransition(running, terminal)).toBe(true);
        expect(isBackfillTerminalTransition(terminal, terminal)).toBe(false);
    });

    it('does not confuse a different job, missing status or missing identity with a completion', () => {
        expect(isBackfillTerminalTransition(running, { id: 'older-job', status: 'completed' })).toBe(false);
        expect(isBackfillTerminalTransition(running, null)).toBe(false);
        expect(isBackfillTerminalTransition(running, running)).toBe(false);
        expect(isBackfillTerminalTransition({ id: '', status: 'running' }, { id: '', status: 'failed' })).toBe(false);
    });
});
