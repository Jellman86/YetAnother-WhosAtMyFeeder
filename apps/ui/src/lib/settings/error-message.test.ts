import { describe, expect, it } from 'vitest';
import { requestErrorMessage } from './error-message';

describe('the words of a failed request', () => {
    it('uses the error\'s own message', () => {
        expect(requestErrorMessage(new Error('Webhook refused'), 'Failed')).toBe('Webhook refused');
    });

    it('reads the detail out of a JSON error body', () => {
        expect(requestErrorMessage(new Error('{"detail": "Token expired"}'), 'Failed')).toBe('Token expired');
        expect(requestErrorMessage(new Error('{"message": "Not allowed"}'), 'Failed')).toBe('Not allowed');
    });

    it('falls back when there are no words to use', () => {
        expect(requestErrorMessage('not an error', 'Failed')).toBe('Failed');
        expect(requestErrorMessage(new Error('{"code": 5}'), 'Failed')).toBe('Failed');
    });

    it('keeps a body that only looks like JSON as it is', () => {
        expect(requestErrorMessage(new Error('{not json'), 'Failed')).toBe('{not json');
    });
});
