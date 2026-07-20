import { describe, expect, it } from 'vitest';

import { selectReclassificationStrategy } from './reclassification';

describe('selectReclassificationStrategy', () => {
    it('uses video when the Frigate event reports a clip', () => {
        expect(selectReclassificationStrategy(true, 'idle')).toBe('video');
    });

    it('uses video when a full-visit clip was fetched into the local cache', () => {
        expect(selectReclassificationStrategy(false, 'ready')).toBe('video');
    });

    it('uses a snapshot only when neither video source is ready', () => {
        expect(selectReclassificationStrategy(false, 'failed')).toBe('snapshot');
    });
});
