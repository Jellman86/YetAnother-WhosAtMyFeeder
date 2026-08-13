import { describe, expect, it } from 'vitest';
import type { CameraStatusResponse, Detection } from '../api';
import type { DetectionVisit } from './visit-grouping';
import { buildDashboardCameraRows } from './dashboard-cameras';

function visit(camera: string, eventId: string, endTime: string): DetectionVisit {
    const detection = {
        frigate_event: eventId,
        camera_name: camera,
        display_name: 'Blue Tit',
        detection_time: endTime,
        score: 0.9
    } as Detection;
    return {
        key: eventId,
        species: detection.display_name,
        camera,
        frames: [detection],
        lead: detection,
        best: detection,
        startTime: endTime,
        endTime,
        needsReview: false
    };
}

const status: CameraStatusResponse = {
    checked_at: '2026-08-12T09:00:00Z',
    cameras: [
        { camera: 'front', status: 'online' },
        { camera: 'garden', status: 'online' },
        { camera: 'garage', status: 'offline' }
    ]
};

describe('buildDashboardCameraRows', () => {
    it('shows only configured cameras and excludes historical or unrelated Frigate cameras', () => {
        const rows = buildDashboardCameraRows({
            cameraStatus: status,
            visits: [
                visit('front', 'front-1', '2026-08-12T08:00:00Z'),
                visit('garage', 'garage-1', '2026-08-12T07:00:00Z')
            ],
            configuredCameras: ['front', 'garden']
        });

        expect(rows.map((row) => row.name)).toEqual(['front', 'garden']);
        expect(rows[0]).toMatchObject({ visits: 1, status: 'online' });
        expect(rows[1]).toMatchObject({ visits: 0, status: 'online' });
    });

    it('keeps a configured camera visible with unknown health when Frigate omits it', () => {
        const rows = buildDashboardCameraRows({
            cameraStatus: status,
            visits: [],
            configuredCameras: ['nest']
        });

        expect(rows).toEqual([{ name: 'nest', visits: 0, status: 'unknown', lastSeen: null }]);
    });

    it('uses all reporting and visiting cameras when the configured list is deliberately empty', () => {
        const rows = buildDashboardCameraRows({
            cameraStatus: status,
            visits: [visit('side', 'side-1', '2026-08-12T08:30:00Z')],
            configuredCameras: []
        });

        expect(rows.map((row) => row.name)).toEqual(['side', 'front', 'garage', 'garden']);
    });

    it('does not expose status-only cameras before settings have loaded', () => {
        const rows = buildDashboardCameraRows({
            cameraStatus: status,
            visits: [visit('front', 'front-1', '2026-08-12T08:00:00Z')],
            configuredCameras: null
        });

        expect(rows.map((row) => row.name)).toEqual(['front']);
    });
});
