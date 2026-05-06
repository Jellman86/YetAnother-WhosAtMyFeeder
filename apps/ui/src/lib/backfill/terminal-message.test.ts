import { describe, expect, it } from 'vitest';
import { formatTerminalBackfillMessage } from './terminal-message';

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
