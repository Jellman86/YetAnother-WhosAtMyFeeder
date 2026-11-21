import { describe, expect, it, vi } from 'vitest';
import { createPageLeaving } from './page-leaving';

describe('whether the reader is leaving the page', () => {
    it('is not leaving at first', () => {
        const page = createPageLeaving(new EventTarget());
        expect(page.isLeaving()).toBe(false);
    });

    it('is leaving from beforeunload until the page would have gone, then stays when it did not', () => {
        // Settings can ask the reader to stay with unsaved changes, and nothing says they chose to.
        vi.useFakeTimers();
        const target = new EventTarget();
        const page = createPageLeaving(target, 3000);
        target.dispatchEvent(new Event('beforeunload'));
        expect(page.isLeaving()).toBe(true);
        vi.advanceTimersByTime(2999);
        expect(page.isLeaving()).toBe(true);
        vi.advanceTimersByTime(1);
        expect(page.isLeaving()).toBe(false);
        vi.useRealTimers();
    });

    it('is leaving once the page is hidden for another, and back when it is shown again', () => {
        // pagehide is the signal Safari on iPhone gives; a page restored from the back cache is shown again.
        const target = new EventTarget();
        const page = createPageLeaving(target);
        target.dispatchEvent(new Event('pagehide'));
        expect(page.isLeaving()).toBe(true);
        target.dispatchEvent(new Event('pageshow'));
        expect(page.isLeaving()).toBe(false);
    });

    it('stops listening when disposed', () => {
        const target = new EventTarget();
        const page = createPageLeaving(target);
        page.dispose();
        target.dispatchEvent(new Event('pagehide'));
        expect(page.isLeaving()).toBe(false);
    });
});
