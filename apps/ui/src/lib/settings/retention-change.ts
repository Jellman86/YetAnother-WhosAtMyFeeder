/**
 * Whether saving `nextDays` of history deletes detections the saved policy keeps.
 * 0 days keeps everything, so moving to it never deletes, and moving away from it always can.
 */
export function retentionShrinks(savedDays: number, nextDays: number): boolean {
    if (nextDays <= 0) return false;
    return savedDays <= 0 || nextDays < savedDays;
}
