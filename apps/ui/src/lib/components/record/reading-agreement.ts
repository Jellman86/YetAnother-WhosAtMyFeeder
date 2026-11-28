import type { Detection } from '../../api';

type SnapshotReading = NonNullable<Detection['snapshot_reading']>;

export interface ReadingDisagreement {
    snapshot: SnapshotReading;
    videoLabel: string;
    videoScore: number | null;
    /** Amber, and the words for it, only while the owner has not named the bird themselves. */
    needsPerson: boolean;
}

/**
 * The record's snapshot and video readings when the server found they name different birds
 * (#804). The comparison is the server's, by catalogue species; nothing here compares labels.
 */
export function readingDisagreement(detection: Detection): ReadingDisagreement | null {
    if (detection.reading_agreement !== 'disagree') return null;
    if (detection.video_classification_status !== 'completed') return null;
    const snapshot = detection.snapshot_reading;
    const videoLabel = detection.video_classification_label?.trim();
    if (!snapshot || !videoLabel) return null;
    return {
        snapshot,
        videoLabel,
        videoScore: typeof detection.video_classification_score === 'number' ? detection.video_classification_score : null,
        needsPerson: !detection.manual_tagged
    };
}
