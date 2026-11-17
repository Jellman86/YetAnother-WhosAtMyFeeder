import type { Detection } from '../../api';

/**
 * What a record's identification is: the visit, the species it names and whether the owner chose or
 * confirmed it. Anything said about one identification (an AI note being written, or why it failed)
 * belongs to it, and is dropped when this key changes.
 */
export function recordClassificationKey(detection: Detection): string {
    return JSON.stringify([detection.frigate_event, detection.display_name ?? null, detection.category_name ?? null, Boolean(detection.manual_tagged)]);
}
