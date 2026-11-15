import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import { advance, createReviewSession, refreshCurrent, remaining } from './review-session';

function detection(id: string): Detection {
    return {
        frigate_event: id,
        display_name: 'Unknown Bird',
        score: 0.51,
        detection_time: '2026-08-11T05:19:00Z',
        camera_name: 'birdcam'
    } as Detection;
}

const queue = [detection('a'), detection('b'), detection('c')];

describe('review session', () => {
    it('starts on the longest-waiting item with nothing yet resolved', () => {
        const session = createReviewSession(queue);

        expect(session.current?.frigate_event).toBe('a');
        expect(session.position).toBe(1);
        expect(session.total).toBe(3);
        expect(session.resolved).toBe(0);
    });

    it('moves to the next item and counts the one just handled', () => {
        const session = advance(createReviewSession(queue), 'resolved');

        expect(session.current?.frigate_event).toBe('b');
        expect(session.position).toBe(2);
        expect(session.resolved).toBe(1);
    });

    it('counts a skip as progress through the queue but not as work done', () => {
        const session = advance(createReviewSession(queue), 'skipped');

        expect(session.current?.frigate_event).toBe('b');
        expect(session.resolved).toBe(0);
        expect(session.skipped).toBe(1);
    });

    it('finishes after the last item rather than wrapping around', () => {
        let session = createReviewSession(queue);
        session = advance(session, 'resolved');
        session = advance(session, 'resolved');
        session = advance(session, 'resolved');

        expect(session.current).toBeNull();
        expect(session.done).toBe(true);
        expect(session.resolved).toBe(3);
        expect(remaining(session)).toBe(0);
    });

    it('reports an empty queue as already done', () => {
        const session = createReviewSession([]);

        expect(session.done).toBe(true);
        expect(session.current).toBeNull();
        expect(session.total).toBe(0);
    });

    it('leaves the source queue untouched', () => {
        const session = createReviewSession(queue);
        advance(session, 'resolved');

        expect(queue.map((item) => item.frigate_event)).toEqual(['a', 'b', 'c']);
        expect(session.index).toBe(0);
    });

    it('knows how many are still ahead', () => {
        expect(remaining(createReviewSession(queue))).toBe(3);
        expect(remaining(advance(createReviewSession(queue), 'skipped'))).toBe(2);
    });
});

describe('refreshCurrent', () => {
    it('shows what a visit says now, in place, without moving the session on', () => {
        const items = [
            { frigate_event: 'a', display_name: 'Eurasian Bullfinch', category_name: 'Pyrrhula pyrrhula' },
            { frigate_event: 'b', display_name: 'Dunnock', category_name: 'Prunella modularis' }
        ] as Detection[];
        const session = createReviewSession(items);
        const refreshed = refreshCurrent(session, { display_name: 'Common Chaffinch', category_name: 'Fringilla coelebs', manual_tagged: true });
        expect(refreshed.current).toMatchObject({ frigate_event: 'a', display_name: 'Common Chaffinch', category_name: 'Fringilla coelebs', manual_tagged: true });
        expect(refreshed.position).toBe(1);
        expect(refreshed.resolved).toBe(0);
        expect(refreshed.items[1]).toBe(items[1]);
    });

    it('leaves a finished session alone', () => {
        const done = advance(createReviewSession([{ frigate_event: 'a' } as Detection]), 'resolved');
        expect(refreshCurrent(done, { display_name: 'Robin' })).toBe(done);
    });
});
