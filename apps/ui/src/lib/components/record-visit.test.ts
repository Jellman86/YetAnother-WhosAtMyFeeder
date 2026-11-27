import { describe, expect, it } from 'vitest';
import { recordVisit } from './record-visit';
import recordDialogsSource from './RecordDialogs.svelte?raw';
import dashboardSource from '../pages/Dashboard.svelte?raw';
import eventsSource from '../pages/Events.svelte?raw';

const span = { startTime: '2026-11-26T12:44:07Z', endTime: '2026-11-26T12:46:29Z' };

describe('the visit a record states beside its capture', () => {
    it('names the capture it was opened on, with the visit it belongs to', () => {
        expect(recordVisit('cforck', { captureCount: 6, ...span })).toEqual({ frigateEvent: 'cforck', captureCount: 6, ...span });
    });

    it('says nothing for a single-capture visit, which is the capture itself, or without a visit', () => {
        expect(recordVisit('cforck', { captureCount: 1, ...span })).toBeNull();
        expect(recordVisit('cforck', span)).toBeNull();
        expect(recordVisit('cforck', undefined)).toBeNull();
    });

    it('reaches the record through the shared opener, and only for the capture it was opened on', () => {
        expect(recordDialogsSource).toContain('visit={visit?.frigateEvent === record.frigate_event ? visit : null}');
        for (const page of [eventsSource, dashboardSource]) expect(page).toContain('bind:visit={openedVisit}');
        // Closing the record, or swapping it for the player, takes the visit with it.
        expect(recordDialogsSource).toContain('visit = $bindable(null)');
        expect(recordDialogsSource.match(/\brecord = null\b/g)).toHaveLength(1);
    });
});
