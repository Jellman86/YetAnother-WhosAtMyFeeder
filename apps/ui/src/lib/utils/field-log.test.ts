import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import type { GardenServerVisit } from '../api/garden';
import type { DetectionVisit } from './visit-grouping';
import { mergeFieldLog, namesCameras } from './field-log';

describe('namesCameras', () => {
    it('leaves the camera off rows when every visit in the log came from one camera', () => {
        expect(namesCameras([{ camera: 'birdcam' }, { camera: 'birdcam' }])).toBe(false);
    });

    it('names the camera on every row once the log holds two cameras', () => {
        expect(namesCameras([{ camera: 'birdcam' }, { camera: 'nestcam' }])).toBe(true);
    });

    it('says nothing about cameras for an empty log', () => {
        expect(namesCameras([])).toBe(false);
    });
});

function birdVisit(key: string, latest: string): DetectionVisit {
    const lead = { frigate_event: key, detection_time: latest, display_name: 'Robin', camera_name: 'birdcam' } as Detection;
    return {
        key, species: 'Robin', camera: 'birdcam', frames: [lead], lead, best: lead,
        startTime: latest, endTime: latest, needsReview: false, audioConfirmed: false
    };
}

function gardenVisit(id: string, end: string): GardenServerVisit {
    return {
        id, kind: 'visit', start_time: end, end_time: end, capture_count: 1,
        representative: {
            id, camera: 'patio', frigate_label: 'cat', observed_at: end, status: 'confirmed',
            reviewed_at: null, snapshot_url: null
        }
    };
}

describe('mergeFieldLog', () => {
    it('threads Garden visits between bird visits by their most recent activity, newest first', () => {
        const rows = mergeFieldLog(
            [birdVisit('robin-late', '2026-10-27T10:00:00Z'), birdVisit('robin-early', '2026-10-27T08:00:00Z')],
            [gardenVisit('fox', '2026-10-27T09:00:00Z'), gardenVisit('cat', '2026-10-27T11:00:00Z')],
            10
        );
        expect(rows.map((row) => row.key)).toEqual(['garden:cat', 'visit:robin-late', 'garden:fox', 'visit:robin-early']);
        expect(rows.map((row) => row.kind)).toEqual(['garden', 'visit', 'garden', 'visit']);
    });

    it('keeps the server order of bird visits even when a Garden visit falls between equal times', () => {
        const rows = mergeFieldLog(
            [birdVisit('first', '2026-10-27T10:00:00Z'), birdVisit('second', '2026-10-27T10:00:00Z')],
            [gardenVisit('fox', '2026-10-27T10:00:00Z')],
            10
        );
        expect(rows.map((row) => row.key)).toEqual(['visit:first', 'visit:second', 'garden:fox']);
    });

    it('caps the merged log so the newest rows of either kind are the ones shown', () => {
        const rows = mergeFieldLog(
            [birdVisit('robin', '2026-10-27T08:00:00Z')],
            [gardenVisit('cat', '2026-10-27T11:00:00Z'), gardenVisit('fox', '2026-10-27T09:00:00Z')],
            2
        );
        expect(rows.map((row) => row.key)).toEqual(['garden:cat', 'garden:fox']);
    });

    it('reads as a bird-only log when Garden is off or nothing was seen', () => {
        const rows = mergeFieldLog([birdVisit('robin', '2026-10-27T08:00:00Z')], [], 10);
        expect(rows).toEqual([{ kind: 'visit', key: 'visit:robin', at: Date.parse('2026-10-27T08:00:00Z'), visit: expect.anything() }]);
    });
});
