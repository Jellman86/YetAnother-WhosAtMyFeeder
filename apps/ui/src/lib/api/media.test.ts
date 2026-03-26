import { beforeEach, describe, expect, it, vi } from 'vitest';

import { checkRecordingClipAvailable } from './media';

describe('checkRecordingClipAvailable', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('returns both availability and persisted fetch state from the recording HEAD response', async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(
            new Response(null, {
                status: 200,
                headers: {
                    'X-YAWAMF-Recording-Clip-Ready': 'cached'
                }
            })
        );

        await expect(checkRecordingClipAvailable('evt-3')).resolves.toEqual({
            available: true,
            fetched: true
        });
    });
});
