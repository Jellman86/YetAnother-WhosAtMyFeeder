import type { ReclassificationProgress } from '../stores/detections.svelte';

/**
 * How a clip scan reads as a ribbon: one bar per sampled frame, its height the model's
 * confidence. Frames are addressed by their 1-based place in the sample, because the clip's own
 * timing is not part of the progress stream and the ribbon must not claim a time it never measured.
 */
export type FrameScanTone = 'pending' | 'strong' | 'moderate' | 'weak';

export interface FrameScanBar {
    position: number;
    tone: FrameScanTone;
    /** 0 while waiting; read frames never drop below a visible minimum. */
    heightPercent: number;
    label: string | null;
    scorePercent: number | null;
}

interface FrameScanRead {
    position: number;
    label: string;
    scorePercent: number;
    thumb: string | null;
}

export interface FrameScan {
    bars: FrameScanBar[];
    total: number;
    readCount: number;
    /** The frame the model works on next; null once the run is complete. */
    nextPosition: number | null;
    complete: boolean;
    latest: FrameScanRead | null;
    best: FrameScanRead | null;
}

type ScanProgress = Pick<ReclassificationProgress, 'currentFrame' | 'totalFrames' | 'frameResults' | 'status'>;

const STRONG_SCORE = 0.8;
const MODERATE_SCORE = 0.5;
// A near-zero read is still a read; it must not look like a frame that never arrived.
const MIN_READ_HEIGHT_PERCENT = 8;

function wholeCount(value: number, minimum: number): number {
    return Number.isFinite(value) ? Math.max(minimum, Math.floor(value)) : minimum;
}

function toneFor(score: number): FrameScanTone {
    if (score >= STRONG_SCORE) return 'strong';
    if (score >= MODERATE_SCORE) return 'moderate';
    return 'weak';
}

export function frameScan(progress: ScanProgress): FrameScan {
    const total = wholeCount(progress.totalFrames, 1);
    const current = Math.min(total, wholeCount(progress.currentFrame, 0));
    const complete = progress.status === 'completed' || current >= total;

    let readCount = 0;
    let latest: FrameScanRead | null = null;
    let best: FrameScanRead | null = null;

    const bars = Array.from({ length: total }, (_, index): FrameScanBar => {
        const frame = progress.frameResults[index];
        const position = index + 1;
        if (!frame || !Number.isFinite(frame.score)) {
            return { position, tone: 'pending', heightPercent: 0, label: null, scorePercent: null };
        }
        const score = Math.min(1, Math.max(0, frame.score));
        const scorePercent = Math.round(score * 100);
        const read: FrameScanRead = { position, label: frame.label, scorePercent, thumb: frame.thumb ?? null };
        readCount += 1;
        latest = read;
        if (!best || scorePercent > best.scorePercent) best = read;
        return {
            position,
            tone: toneFor(score),
            heightPercent: Math.max(MIN_READ_HEIGHT_PERCENT, scorePercent),
            label: frame.label,
            scorePercent
        };
    });

    return {
        bars,
        total,
        readCount,
        nextPosition: complete ? null : current + 1,
        complete,
        latest,
        best
    };
}
