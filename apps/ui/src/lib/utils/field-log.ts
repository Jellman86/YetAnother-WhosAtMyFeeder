/**
 * A camera name tells rows apart only when the log holds more than one camera. On a one-camera
 * feeder the same chip on every row is repetition; the record and the preview still name it.
 */
export function namesCameras(visits: readonly { camera: string }[]): boolean {
    return new Set(visits.map((visit) => visit.camera)).size > 1;
}
