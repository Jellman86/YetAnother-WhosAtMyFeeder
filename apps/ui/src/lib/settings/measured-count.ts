/**
 * A count read from the server, or null when the answer holds none.
 *
 * A destructive question states how much it deletes, so a missing figure must stay missing: falling
 * back to zero told an owner with 931 detections that "all 0" would go.
 */
export function measuredCount(value: unknown): number | null {
    return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
}
