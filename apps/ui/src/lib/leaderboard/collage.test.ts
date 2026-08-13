import { describe, expect, it } from 'vitest';

import type { Detection } from '../api';
import {
    advanceCollageSlots,
    collageDateQuery,
    selectCollagePhotos
} from './collage';

function detection(
    eventId: string,
    detectionTime: string,
    cameraName: string,
    score = 0.7
): Detection {
    return {
        frigate_event: eventId,
        display_name: 'Eurasian Blackbird',
        detection_time: detectionTime,
        camera_name: cameraName,
        score,
        has_snapshot: true
    };
}

describe('leaderboard collage evidence', () => {
    it('uses the exact leaderboard window for bounded spans', () => {
        expect(
            collageDateQuery(
                'day',
                '2026-08-12T07:15:30+00:00',
                '2026-08-13T07:15:30+00:00'
            )
        ).toEqual({ startDate: '2026-08-12', endDate: '2026-08-13' });
        expect(collageDateQuery('all', null, null)).toEqual({});
        expect(collageDateQuery('week', null, null)).toBeNull();
    });

    it('keeps only photographs inside the exact window', () => {
        const photos = selectCollagePhotos(
            [
                detection('new', '2026-08-13T06:00:00Z', 'garden'),
                detection('old', '2026-08-10T06:00:00Z', 'garden')
            ],
            {
                windowStart: '2026-08-12T07:15:30Z',
                windowEnd: '2026-08-13T07:15:30Z'
            }
        );

        expect(photos.map((photo) => photo.frigate_event)).toEqual(['new']);
    });

    it('selects the best frame per visit without merging different cameras', () => {
        const photos = selectCollagePhotos([
            detection('garden-first', '2026-08-13T12:00:00Z', 'garden', 0.5),
            detection('side-visit', '2026-08-13T11:59:00Z', 'side', 0.75),
            detection('garden-best', '2026-08-13T11:52:00Z', 'garden', 0.95),
            detection('garden-chain', '2026-08-13T11:44:00Z', 'garden', 0.7)
        ]);

        expect(photos.map((photo) => photo.frigate_event)).toEqual([
            'garden-best',
            'side-visit'
        ]);
    });

    it('spreads a bounded number of photographs across the available visits', () => {
        const photos = selectCollagePhotos(
            Array.from({ length: 9 }, (_unused, index) =>
                detection(
                    `visit-${index}`,
                    new Date(Date.UTC(2026, 7, 13, 12 - index)).toISOString(),
                    'garden'
                )
            ),
            { maxPhotos: 4 }
        );

        expect(photos.map((photo) => photo.frigate_event)).toEqual([
            'visit-0',
            'visit-3',
            'visit-5',
            'visit-8'
        ]);
    });

    it('advances one tile to an unseen photograph without duplicates', () => {
        expect(
            advanceCollageSlots(['a', 'b', 'c', 'd'], ['a', 'b', 'c', 'd', 'e'], 0)
        ).toEqual({ slots: ['e', 'b', 'c', 'd'], nextTile: 1 });
    });
});
