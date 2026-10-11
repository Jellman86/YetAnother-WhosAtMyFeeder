import type { BirdScanResponse } from '../api/media';

const STAGES = ['detecting', 'naming', 'counting', 'saving'] as const;
type ScanStage = (typeof STAGES)[number];

export interface BirdScanProgress {
    /** 1 to 4 while a step is known; null when the scan is running somewhere that cannot say. */
    step: number | null;
    stage: ScanStage | null;
    /** How full each of the four steps is, 0 to 1. Only a step the server counts is ever partial. */
    segments: number[];
}

/**
 * The four real steps of a scan, as the server reports them. A step is shown as done only once the
 * next one has started, and the naming step fills by the crops actually named, so the bar never
 * runs ahead of the work.
 */
export function birdScanProgress(response: BirdScanResponse | null): BirdScanProgress {
    const stage = STAGES.find((candidate) => candidate === response?.stage) ?? null;
    if (response?.status !== 'running' || stage === null) {
        return { step: null, stage: null, segments: STAGES.map(() => 0) };
    }
    const index = STAGES.indexOf(stage);
    const done = response.stage_done ?? 0;
    const total = response.stage_total ?? 0;
    const current = stage === 'naming' && total > 0 ? Math.min(1, Math.max(0, done / total)) : 0;
    return {
        step: index + 1,
        stage,
        segments: STAGES.map((_, position) => (position < index ? 1 : position === index ? current : 0))
    };
}

/** Whole seconds since the server started the scan, or since this page first saw it running. */
export function birdScanElapsedSeconds(startedAt: string | null | undefined, seenAt: number, now: number): number {
    const started = startedAt ? Date.parse(startedAt) : Number.NaN;
    const from = Number.isFinite(started) && started <= now ? started : seenAt;
    return Math.max(0, Math.floor((now - from) / 1000));
}
