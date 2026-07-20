import type { FullVisitFetchState } from '../stores/full-visit.svelte';

export type ReclassificationStrategy = 'snapshot' | 'video';

export function selectReclassificationStrategy(
    hasEventClip: boolean | null | undefined,
    fullVisitFetchState: FullVisitFetchState | undefined
): ReclassificationStrategy {
    return hasEventClip || fullVisitFetchState === 'ready' ? 'video' : 'snapshot';
}
