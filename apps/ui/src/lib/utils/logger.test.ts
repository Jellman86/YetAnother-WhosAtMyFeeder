import { describe, expect, it } from 'vitest';

import { formatErrorForLog, sanitizeLogContext } from './logger';

describe('formatErrorForLog', () => {
    it('includes stack traces in development logs', () => {
        const error = new Error('preview failed');

        expect(formatErrorForLog(error, true)).toMatchObject({
            message: 'preview failed',
            name: 'Error',
            stack: expect.any(String)
        });
    });

    it('strips stack traces from production logs', () => {
        const error = new Error('preview failed');

        expect(formatErrorForLog(error, false)).toEqual({
            message: 'preview failed',
            name: 'Error'
        });
    });

    it('passes non-Error values through unchanged', () => {
        const error = { code: 'network_error' };

        expect(formatErrorForLog(error, false)).toBe(error);
    });

    it('strips Error stacks from production warning contexts', () => {
        expect(sanitizeLogContext({ error: new Error('probe failed'), eventId: 'evt-1' }, false)).toEqual({
            error: {
                message: 'probe failed',
                name: 'Error'
            },
            eventId: 'evt-1'
        });
    });
});
