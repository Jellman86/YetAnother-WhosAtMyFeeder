/**
 * Why the finder cannot run, split by whether the owner can do anything about it from the photograph.
 * A standing reason (no whole frame was kept, no crop detector, another frame is being scanned or
 * already reviewed) holds until something elsewhere changes, so the record keeps it out of the way,
 * in More actions with its reason, and the identification follows the photograph. A frame that
 * changed during a scan is feedback on the scan just run, so it stays under the photograph.
 */
const STANDING = new Set(['full_scene_unavailable', 'crop_model_unavailable', 'scan_in_progress', 'reviewed_other_frame']);

export function isStandingUnavailability(reason: string | null | undefined): boolean {
    return reason != null && STANDING.has(reason);
}
