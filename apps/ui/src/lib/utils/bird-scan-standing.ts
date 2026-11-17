/**
 * Why the finder cannot run, split by whether the owner can do anything about it from the photograph.
 * A standing reason (no whole frame was kept, no crop detector, another frame is being scanned or
 * already reviewed) holds until something elsewhere changes, so the record says it once after the
 * identification and lists the finder in More actions with it, and the identification follows the
 * photograph. A frame that changed during a scan is feedback on the scan just run, so it stays under
 * the photograph.
 */
const STANDING = new Set(['full_scene_unavailable', 'crop_model_unavailable', 'scan_in_progress', 'reviewed_other_frame']);

type Translate = (id: string, options: { default: string }) => string;

export function isStandingUnavailability(reason: string | null | undefined): boolean {
    return reason != null && STANDING.has(reason);
}

/** Why this photograph cannot be scanned: no frame or image revision to bind a scan to, or the server's reason. */
export function birdScanUnavailableReason(
    candidateId: string | null,
    mediaRevision: string | null,
    response: { unavailable_reason?: string | null } | null
): string | null {
    if (!candidateId || !mediaRevision) return 'full_scene_unavailable';
    return response?.unavailable_reason ?? null;
}

/** The reason, when it stands: not while a scan runs, nor when the status could not be read. */
export function birdScanStandingReason(reason: string | null, state: { active: boolean; readError: boolean }): string | null {
    return !state.active && !state.readError && isStandingUnavailability(reason) ? reason : null;
}

export function birdScanUnavailableText(reason: string | null, t: Translate): string {
    if (reason === 'media_changed') return t('detection.bird_scan.media_changed', { default: 'The frame changed during the scan. Try again on the current frame.' });
    if (reason === 'crop_model_unavailable') return t('detection.bird_scan.detector_unavailable', { default: 'Install a crop detector to find additional birds.' });
    if (reason === 'scan_in_progress') return t('detection.bird_scan.other_running', { default: 'Another frame in this capture is being scanned. Try again when it finishes.' });
    if (reason === 'reviewed_other_frame') return t('detection.bird_scan.reviewed_other_frame', { default: 'Birds reviewed on another frame are kept. This frame cannot replace them.' });
    return t('detection.bird_scan.scene_unavailable', { default: 'More birds cannot be looked for: the whole frame behind this photograph was not kept.' });
}
