import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '../api/core';
import { signInFailure } from './sign-in-failure';

describe('why a sign-in failed', () => {
    it('is a wrong username or password when the server refuses the pair', () => {
        expect(signInFailure(new ApiRequestError('Invalid credentials', 401))).toBe('wrong_credentials');
    });

    it('is too many attempts when the server is rate limiting', () => {
        expect(signInFailure(new ApiRequestError('Rate limit exceeded', 429))).toBe('rate_limited');
    });

    it('is the feeder being unreachable when no answer came back', () => {
        expect(signInFailure(new TypeError('Failed to fetch'))).toBe('unreachable');
    });

    it('is a server fault for any other answer, never blamed on the password', () => {
        expect(signInFailure(new ApiRequestError('Authentication not configured', 500))).toBe('server');
        expect(signInFailure(new ApiRequestError('Authentication is not enabled', 400))).toBe('server');
        expect(signInFailure(new Error('unexpected'))).toBe('server');
        expect(signInFailure(undefined)).toBe('server');
    });
});
