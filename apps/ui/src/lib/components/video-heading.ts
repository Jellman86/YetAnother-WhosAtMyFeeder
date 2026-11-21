import type { BirdNamer, BirdNamingInput } from '../naming';

/** The player's title: the bird the clip shows and when it was recorded. */
export interface VideoHeading {
    name: string;
    at: string | null;
}

export function videoHeadingFor(
    detection: BirdNamingInput & { detection_time?: string | null },
    showCommon: boolean,
    preferScientific: boolean,
    names: BirdNamer
): VideoHeading {
    return { name: names(detection, showCommon, preferScientific).primary, at: detection.detection_time ?? null };
}
