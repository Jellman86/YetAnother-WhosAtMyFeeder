import type { Detection } from '../api';

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * What is known about a detection's event in Frigate.
 *
 * `gone` needs evidence: a not-found answer, or the integrity scan's recorded result. A Frigate
 * that was down, slow or erroring left the question open, and `unknown` means nobody reported on
 * the event at all, so the record says nothing about it.
 */
export type FrigateEventReading = 'found' | 'gone' | 'unreachable' | 'timed_out' | 'failed' | 'not_checked' | 'unknown';

export function frigateEventReading(detection: Detection): FrigateEventReading {
    const check = detection.frigate_event_check;
    if (
        detection.frigate_status === 'missing' ||
        check === 'not_found' ||
        detection.video_classification_error === 'event_not_found'
    ) {
        return 'gone';
    }
    if (check === 'found' || check === 'unreachable' || check === 'timed_out' || check === 'failed') return check;
    // The server said there is no event to link to without saying what Frigate answered.
    return detection.has_frigate_event === false ? 'not_checked' : 'unknown';
}

/** The record's sentence for a reading: the cause and the next step, or null when there is nothing to say. */
export function frigateEventNotice(reading: FrigateEventReading, t: Translate): string | null {
    switch (reading) {
        case 'gone':
            return t('detection.upstream_check.gone', { default: 'Frigate no longer has this event or media.' });
        case 'unreachable':
            return t('detection.upstream_check.unreachable', {
                default: 'YA-WAMF could not reach Frigate, so it is not known whether Frigate still has this event. Check that Frigate is running, then reopen this record.'
            });
        case 'timed_out':
            return t('detection.upstream_check.timed_out', {
                default: 'Frigate did not answer in time, so it is not known whether it still has this event. Reopen this record in a moment. If it keeps happening, check how busy Frigate is.'
            });
        case 'failed':
            return t('detection.upstream_check.failed', {
                default: "Frigate answered with an error, so it is not known whether it still has this event. Check Frigate's log, then reopen this record."
            });
        case 'not_checked':
            return t('detection.upstream_check.not_checked', {
                default: 'Frigate has not been asked about this event yet. Reopen this record to check.'
            });
        default:
            return null;
    }
}
