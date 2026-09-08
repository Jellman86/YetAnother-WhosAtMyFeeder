import { describe, expect, it, vi } from 'vitest';

import { resolveStreamUrl } from './stream-url';

describe('resolveStreamUrl', () => {
    it('opens the bare stream when there is no session to protect', async () => {
        const mint = vi.fn();

        const url = await resolveStreamUrl('/api/sse', false, mint);

        expect(url).toBe('/api/sse');
        expect(mint).not.toHaveBeenCalled();
    });

    it('exchanges the session for a ticket and never puts the token itself in the URL', async () => {
        const mint = vi.fn().mockResolvedValue({ ticket: 'one-shot/ticket+value', expires_in_seconds: 60 });

        const url = await resolveStreamUrl('/api/sse', true, mint);

        expect(url).toBe('/api/sse?ticket=one-shot%2Fticket%2Bvalue');
        expect(url).not.toContain('token=');
    });

    it('mints a fresh ticket on every call, because each one is redeemed exactly once', async () => {
        const mint = vi
            .fn()
            .mockResolvedValueOnce({ ticket: 'first', expires_in_seconds: 60 })
            .mockResolvedValueOnce({ ticket: 'second', expires_in_seconds: 60 });

        const first = await resolveStreamUrl('/api/sse', true, mint);
        const second = await resolveStreamUrl('/api/sse', true, mint);

        expect(first).not.toBe(second);
        expect(mint).toHaveBeenCalledTimes(2);
    });

    it('surfaces a failed exchange so the caller can back off, rather than opening the stream as a guest', async () => {
        const mint = vi.fn().mockRejectedValue(new Error('401'));

        await expect(resolveStreamUrl('/api/sse', true, mint)).rejects.toThrow('401');
    });
});
