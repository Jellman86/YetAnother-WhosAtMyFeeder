import { describe, expect, it } from 'vitest';

import type { Detection } from '../api';
import { frigateEventNotice, frigateEventReading } from './frigate-event-reading';

const t = (key: string, options?: Record<string, unknown>): string => String(options?.default ?? key);

function detection(overrides: Partial<Detection> = {}): Detection {
    return {
        frigate_event: 'evt-1',
        display_name: 'Dunnock',
        score: 0.81,
        detection_time: '2026-11-16T07:11:00Z',
        camera_name: 'feeder',
        ...overrides
    };
}

describe('what was learned about the Frigate event', () => {
    it('says gone only on a not-found answer, a recorded integrity result or a not-found video error', () => {
        expect(frigateEventReading(detection({ has_frigate_event: false, frigate_event_check: 'not_found' }))).toBe('gone');
        expect(frigateEventReading(detection({ frigate_status: 'missing', frigate_event_check: 'unreachable' }))).toBe('gone');
        expect(frigateEventReading(detection({ video_classification_error: 'event_not_found' }))).toBe('gone');
    });

    it.each(['unreachable', 'timed_out', 'failed'] as const)(
        'keeps a check that %s apart from an absence',
        (check) => {
            expect(frigateEventReading(detection({ has_frigate_event: false, frigate_event_check: check }))).toBe(check);
        }
    );

    it('reads an event Frigate returned as found', () => {
        expect(frigateEventReading(detection({ has_frigate_event: true, frigate_event_check: 'found' }))).toBe('found');
    });

    it('does not turn an unanswered question into an absence', () => {
        // An older server, or a list that skipped the check, reports no event without saying why.
        expect(frigateEventReading(detection({ has_frigate_event: false }))).toBe('not_checked');
        expect(frigateEventReading(detection({ has_frigate_event: false, frigate_event_check: 'not_checked' }))).toBe('not_checked');
    });

    it('says nothing about an event nobody reported on', () => {
        // A live update carries no availability at all.
        expect(frigateEventReading(detection())).toBe('unknown');
        expect(frigateEventReading(detection({ has_frigate_event: true, frigate_event_check: 'not_checked' }))).toBe('unknown');
    });
});

describe('the words for each reading', () => {
    it('claims "no longer has" for a gone event alone', () => {
        expect(frigateEventNotice('gone', t)).toBe('Frigate no longer has this event or media.');
        for (const reading of ['unreachable', 'timed_out', 'failed', 'not_checked'] as const) {
            expect(frigateEventNotice(reading, t)).not.toContain('no longer has');
        }
    });

    it('gives each unanswered check its cause and a next step', () => {
        expect(frigateEventNotice('unreachable', t)).toBe(
            'YA-WAMF could not reach Frigate, so it is not known whether Frigate still has this event. Check that Frigate is running, then reopen this record.'
        );
        expect(frigateEventNotice('timed_out', t)).toBe(
            'Frigate did not answer in time, so it is not known whether it still has this event. Reopen this record in a moment. If it keeps happening, check how busy Frigate is.'
        );
        expect(frigateEventNotice('failed', t)).toBe(
            "Frigate answered with an error, so it is not known whether it still has this event. Check Frigate's log, then reopen this record."
        );
        expect(frigateEventNotice('not_checked', t)).toBe(
            'Frigate has not been asked about this event yet. Reopen this record to check.'
        );
    });

    it('has nothing to say when the event was found or nothing was reported', () => {
        expect(frigateEventNotice('found', t)).toBeNull();
        expect(frigateEventNotice('unknown', t)).toBeNull();
    });
});
