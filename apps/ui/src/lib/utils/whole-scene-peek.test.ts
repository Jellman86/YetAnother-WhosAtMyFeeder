import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PEEK_INTENT_MS, WholeScenePeek } from './whole-scene-peek.svelte';

describe('WholeScenePeek (#256)', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });
    afterEach(() => {
        vi.useRealTimers();
    });

    it('starts on the crop and peeks at once for focus or touch', () => {
        const peek = new WholeScenePeek(() => true);
        expect(peek.showing).toBe(false);
        peek.show();
        expect(peek.showing).toBe(true);
        peek.leave();
        expect(peek.showing).toBe(false);
    });

    it('waits for intent before a pointer peeks, and forgets a pointer that moves on', () => {
        const peek = new WholeScenePeek(() => true);
        peek.enter();
        expect(peek.showing).toBe(false);
        vi.advanceTimersByTime(PEEK_INTENT_MS - 1);
        expect(peek.showing).toBe(false);
        vi.advanceTimersByTime(1);
        expect(peek.showing).toBe(true);

        peek.leave();
        peek.enter();
        peek.leave();
        vi.advanceTimersByTime(PEEK_INTENT_MS * 2);
        expect(peek.showing).toBe(false);
    });

    it('pins on a click, survives the pointer leaving, and unpins on the next click', () => {
        const peek = new WholeScenePeek(() => true);
        peek.toggle();
        expect(peek.pinned).toBe(true);
        expect(peek.showing).toBe(true);
        peek.leave();
        expect(peek.showing).toBe(true);
        peek.toggle();
        expect(peek.pinned).toBe(false);
        expect(peek.showing).toBe(false);
    });

    it('never shows when there is nothing to peek at, even mid-peek', () => {
        let allowed = true;
        const peek = new WholeScenePeek(() => allowed);
        peek.toggle();
        expect(peek.showing).toBe(true);
        allowed = false;
        expect(peek.showing).toBe(false);
        peek.reset();
        peek.show();
        peek.toggle();
        expect(peek.pinned).toBe(false);
    });

    it('measures the outline only while the whole scene is drawn', () => {
        const peek = new WholeScenePeek(() => true);
        const image = { naturalWidth: 1600, naturalHeight: 900, clientWidth: 800, clientHeight: 600 } as HTMLImageElement;
        peek.measure(image, [400, 225, 800, 675]);
        expect(peek.outline).toBeNull();
        peek.show();
        peek.measure(image, [400, 225, 800, 675]);
        expect(peek.outline).toEqual({ left: 200, top: 187.5, width: 200, height: 225 });
        peek.measure(null, [400, 225, 800, 675]);
        expect(peek.outline).toBeNull();
    });

    it('resets to the crop with nothing pending', () => {
        const peek = new WholeScenePeek(() => true);
        peek.enter();
        peek.toggle();
        peek.reset();
        vi.advanceTimersByTime(PEEK_INTENT_MS * 2);
        expect(peek.showing).toBe(false);
        expect(peek.pinned).toBe(false);
        expect(peek.outline).toBeNull();
    });
});
