import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
    checkRecordingClipAvailable,
    fetchSnapshotStatus,
    generateHighQualityBirdCropSnapshot
} from './media';

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

describe('snapshot HQ crop helpers', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('fetches snapshot status from the media proxy', async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(
            Response.json({
                event_id: 'evt-7',
                cached: true,
                source: 'high_quality_snapshot',
                high_quality_event_snapshots_enabled: true,
                high_quality_bird_crop_enabled: true,
                already_hq_bird_crop: false,
                can_generate_hq_bird_crop: true
            })
        );

        await expect(fetchSnapshotStatus('evt-7')).resolves.toMatchObject({
            event_id: 'evt-7',
            source: 'high_quality_snapshot',
            can_generate_hq_bird_crop: true
        });
        expect(globalThis.fetch).toHaveBeenCalledWith(
            '/api/frigate/evt-7/snapshot/status',
            expect.objectContaining({ headers: expect.any(Object) })
        );
    });

    it('posts manual HQ bird crop generation requests', async () => {
        vi.spyOn(globalThis, 'fetch').mockResolvedValue(
            Response.json({
                event_id: 'evt-8',
                status: 'generated_hq_bird_crop',
                result: 'bird_crop_replaced',
                cached: true,
                source: 'high_quality_bird_crop',
                high_quality_event_snapshots_enabled: true,
                high_quality_bird_crop_enabled: true,
                already_hq_bird_crop: true,
                can_generate_hq_bird_crop: false
            })
        );

        await expect(generateHighQualityBirdCropSnapshot('evt-8')).resolves.toMatchObject({
            event_id: 'evt-8',
            status: 'generated_hq_bird_crop',
            source: 'high_quality_bird_crop'
        });
        expect(globalThis.fetch).toHaveBeenCalledWith(
            '/api/frigate/evt-8/snapshot/hq-bird-crop',
            expect.objectContaining({
                method: 'POST',
                headers: expect.any(Object)
            })
        );
    });
});
