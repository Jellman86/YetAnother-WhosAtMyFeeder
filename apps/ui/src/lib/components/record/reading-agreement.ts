import type { Detection } from '../../api';
import type { BirdNamingInput } from '../../naming';

type ClassificationReading = NonNullable<Detection['snapshot_reading']>;

export interface ReadingDisagreement {
    snapshot: ClassificationReading;
    video: ClassificationReading;
    /** Amber, and the words for it, only while the owner has not named the bird themselves. */
    needsPerson: boolean;
}

/**
 * The record's snapshot and video readings when the server found they name different birds
 * (#804). The comparison and the names are the server's, by catalogue species; nothing here
 * compares labels.
 */
export function readingDisagreement(detection: Detection): ReadingDisagreement | null {
    if (detection.reading_agreement !== 'disagree') return null;
    if (detection.video_classification_status !== 'completed') return null;
    const snapshot = detection.snapshot_reading;
    const video = detection.video_reading;
    if (!snapshot || !video) return null;
    return { snapshot, video, needsPerson: !detection.manual_tagged };
}

/** A reading in the shape `birdNames` names a bird from, its stored label the last resort. */
export function readingNamingInput(reading: ClassificationReading): BirdNamingInput {
    return { scientific_name: reading.scientific_name, common_name: reading.common_name, display_name: reading.label };
}
