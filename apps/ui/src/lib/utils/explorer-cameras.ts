import type { ExplorerSubjects } from './garden-explorer';

/**
 * Which cameras the Explorer's rail offers, and whether it may count them.
 *
 * The filter read counts bird visits per camera, so its counts describe birds only. Under Garden
 * animals the rail lists the Garden cameras and counts nothing; under Both it lists every camera
 * once and counts nothing, because no single count covers birds and animals together.
 */

export interface ExplorerCameraOptions {
    cameras: string[];
    /** Null when no measured count describes what the results hold. */
    counts: Record<string, number> | null;
}

// The server's stand-in for a camera name it does not share with visitors (garden_public.HIDDEN_CAMERA).
// Filtering by it would narrow nothing, so it is never offered.
const VISITOR_HIDDEN_CAMERA = 'Hidden';

function sortedUnique(names: Iterable<string>): string[] {
    return [...new Set(names)].filter(Boolean).sort((a, b) => a.localeCompare(b));
}

export function explorerCameraOptions(input: {
    subjects: ExplorerSubjects;
    birdCameras: readonly string[];
    birdCounts: Record<string, number> | null | undefined;
    gardenCameras: readonly string[];
    chosen: string;
}): ExplorerCameraOptions {
    const options: ExplorerCameraOptions = input.subjects === 'birds'
        ? { cameras: [...input.birdCameras], counts: input.birdCounts ?? {} }
        : input.subjects === 'garden'
          ? { cameras: sortedUnique(input.gardenCameras), counts: null }
          : { cameras: sortedUnique([...input.birdCameras, ...input.gardenCameras]), counts: null };
    // A camera chosen from a link stays visible, so it can be seen and removed.
    if (input.chosen && !options.cameras.includes(input.chosen)) options.cameras.push(input.chosen);
    return options;
}

/**
 * A visitor cannot read the owner's Garden settings, so their Garden cameras are the ones the
 * captures already read came from. The list only grows, so choosing one camera keeps the others.
 */
export function seenGardenCameras(seen: readonly string[], captures: readonly { camera: string }[]): readonly string[] {
    const fresh = captures.map((capture) => capture.camera).filter((camera) => camera && camera !== VISITOR_HIDDEN_CAMERA && !seen.includes(camera));
    return fresh.length ? sortedUnique([...seen, ...fresh]) : seen;
}
