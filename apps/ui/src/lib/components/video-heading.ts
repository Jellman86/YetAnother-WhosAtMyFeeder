import { getBirdNames, type BirdNamingInput } from '../naming';

/** The player's title: the bird the clip shows and when it was recorded. */
export interface VideoHeading {
    name: string;
    at: string | null;
}

export function videoHeadingFor(
    detection: BirdNamingInput & { detection_time?: string | null },
    showCommon: boolean,
    preferScientific: boolean
): VideoHeading {
    return { name: getBirdNames(detection, showCommon, preferScientific).primary, at: detection.detection_time ?? null };
}
