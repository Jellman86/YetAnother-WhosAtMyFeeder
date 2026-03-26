import { describe, expect, it } from 'vitest';

import { extractApiErrorMessage } from './error-message';

describe('extractApiErrorMessage', () => {
    it('returns plain-string detail values', () => {
        expect(extractApiErrorMessage({ detail: 'Invalid credentials' }, 'Fallback')).toBe('Invalid credentials');
    });

    it('formats FastAPI validation detail arrays into a readable message', () => {
        expect(
            extractApiErrorMessage(
                {
                    detail: [
                        {
                            type: 'value_error',
                            loc: ['body', 'password'],
                            msg: 'Value error, Password must contain at least one letter and one number',
                        }
                    ]
                },
                'Fallback'
            )
        ).toBe('Password must contain at least one letter and one number');
    });

    it('joins multiple validation errors without leaking object formatting', () => {
        expect(
            extractApiErrorMessage(
                {
                    detail: [
                        {
                            type: 'missing',
                            loc: ['body', 'frigate_url'],
                            msg: 'Field required',
                        },
                        {
                            type: 'value_error',
                            loc: ['body', 'auth_password'],
                            msg: 'Value error, Password must contain at least one letter and one number',
                        }
                    ]
                },
                'Fallback'
            )
        ).toBe('frigate_url: Field required; auth_password: Password must contain at least one letter and one number');
    });

    it('falls back cleanly when detail is not useful', () => {
        expect(extractApiErrorMessage({ detail: {} }, 'Fallback')).toBe('Fallback');
    });
});
