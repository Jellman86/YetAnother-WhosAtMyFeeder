import { describe, expect, it } from 'vitest';
import type { BackfillJobStatus } from '../api/backfill';
import { terminalMessage } from './job-progress';

const status = (fields: Partial<BackfillJobStatus>): BackfillJobStatus => ({ id: 'job-1', status: 'failed', ...fields }) as BackfillJobStatus;

describe('what a finished backfill shows when its status is read by poll', () => {
    it('leads a failed job with the cause the server gave, as the live update does', () => {
        expect(terminalMessage('detections', status({ message: 'Frigate refused the request' }), '10 of 20 checked')).toBe(
            'Import of missed visits: Frigate refused the request'
        );
        expect(terminalMessage('weather', status({ message: 'Weather backfill cancelled' }), '3 of 9 checked')).toBe(
            'Filling in missing weather: Weather backfill cancelled'
        );
    });

    it('falls back to the counts when a failed job gave no cause', () => {
        expect(terminalMessage('detections', status({ message: '  ' }), '10 of 20 checked')).toBe('10 of 20 checked');
    });

    it('never drops the summary of a completed job, whether or not a language has loaded', () => {
        expect(terminalMessage('weather', status({ status: 'completed', message: 'Weather archive unavailable for range' }), '120 of 120 checked')).toContain('120 of 120 checked');
    });
});
