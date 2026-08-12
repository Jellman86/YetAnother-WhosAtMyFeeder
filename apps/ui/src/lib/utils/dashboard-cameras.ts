import type { CameraStatusResponse } from '../api';
import type { DetectionVisit } from './visit-grouping';

export interface DashboardCameraRow {
    name: string;
    visits: number;
    status: 'online' | 'offline' | 'unknown';
    lastSeen: string | null;
}

interface DashboardCameraRowsInput {
    cameraStatus: CameraStatusResponse | null;
    visits: readonly DetectionVisit[];
    /** Null while settings load; an empty list deliberately means every camera. */
    configuredCameras: readonly string[] | null;
}

export function buildDashboardCameraRows({
    cameraStatus,
    visits,
    configuredCameras
}: DashboardCameraRowsInput): DashboardCameraRow[] {
    const visitsByCamera = new Map<string, number>();
    const lastSeenByCamera = new Map<string, string>();
    for (const visit of visits) {
        if (!visit.camera) continue;
        visitsByCamera.set(visit.camera, (visitsByCamera.get(visit.camera) ?? 0) + 1);
        const seen = lastSeenByCamera.get(visit.camera);
        if (!seen || visit.endTime > seen) lastSeenByCamera.set(visit.camera, visit.endTime);
    }

    const statusByCamera = new Map(
        (cameraStatus?.cameras ?? []).map((camera) => [camera.camera, camera.status] as const)
    );
    const cameraNames = new Set<string>();
    if (configuredCameras === null) {
        for (const name of visitsByCamera.keys()) cameraNames.add(name);
    } else if (configuredCameras.length > 0) {
        for (const name of configuredCameras) {
            if (name) cameraNames.add(name);
        }
    } else {
        for (const name of statusByCamera.keys()) cameraNames.add(name);
        for (const name of visitsByCamera.keys()) cameraNames.add(name);
    }

    return [...cameraNames]
        .map((name) => ({
            name,
            visits: visitsByCamera.get(name) ?? 0,
            status: statusByCamera.get(name) ?? 'unknown',
            lastSeen: lastSeenByCamera.get(name) ?? null
        }))
        .sort((left, right) => right.visits - left.visits || left.name.localeCompare(right.name));
}
