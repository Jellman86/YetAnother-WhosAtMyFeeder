import type { HeardGroup } from '../api/audio';
import { formatTime } from './datetime';

/** The bands the visual standard sets for scores: under 60 amber, under 85 brand, above green. */
export function heardConfidenceTone(confidence: number): string {
    if (confidence < 0.6) return 'text-accent-700 dark:text-accent-300';
    if (confidence < 0.85) return 'text-brand-700 dark:text-brand-300';
    return 'text-success-700 dark:text-success-300';
}

/** "3 calls to 09:17" reads only when the calls ran past the minute they started in. */
export function heardCallsUntil(group: HeardGroup): string | null {
    const from = formatTime(group.first_heard);
    const to = formatTime(group.last_heard);
    return group.call_count > 1 && from !== to ? to : null;
}

/**
 * The two ends of a band. A band that runs overnight names the day it started on, or
 * "11:22 to 08:20" reads as time running backwards.
 */
export function heardSpanEnds(firstHeard: string, lastHeard: string, dayOf: (value: string) => string): { from: string; to: string } {
    const sameDay = new Date(firstHeard).toDateString() === new Date(lastHeard).toDateString();
    const from = formatTime(firstHeard);
    return { from: sameDay ? from : `${dayOf(firstHeard)} ${from}`, to: formatTime(lastHeard) };
}
