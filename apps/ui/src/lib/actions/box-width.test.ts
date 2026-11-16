import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { roomFor } from './box-width';

type Callback = () => void;
const observers: { callback: Callback; targets: Element[]; disconnected: boolean }[] = [];

class FakeResizeObserver {
    private readonly record: { callback: Callback; targets: Element[]; disconnected: boolean };
    constructor(callback: Callback) {
        this.record = { callback, targets: [], disconnected: false };
        observers.push(this.record);
    }
    observe(target: Element): void { this.record.targets.push(target); }
    disconnect(): void { this.record.disconnected = true; }
}

function box(width: number, ruler?: { clientWidth: number }) {
    return { clientWidth: width, querySelector: () => ruler ?? null } as unknown as HTMLElement & { clientWidth: number };
}

function notify(): void {
    for (const observer of observers) if (!observer.disconnected) observer.callback();
}

beforeEach(() => {
    observers.length = 0;
    vi.stubGlobal('ResizeObserver', FakeResizeObserver);
});
afterEach(() => vi.unstubAllGlobals());

describe('roomFor', () => {
    it('says whether the box is at least as wide as its ruler, which grows with the reader\'s text size', () => {
        const ruler = { clientWidth: 896 };
        const node = box(900, ruler);
        const onRoom = vi.fn();
        const action = roomFor(node, onRoom);
        // Answered as it mounts, so the page never paints without either arrangement.
        expect(onRoom).toHaveBeenLastCalledWith(true);
        // Doubled text doubles the ruler, not the box.
        ruler.clientWidth = 1792;
        notify();
        expect(onRoom).toHaveBeenLastCalledWith(false);
        expect(observers[0].targets).toHaveLength(2);

        action.destroy();
        expect(observers[0].disconnected).toBe(true);
    });

    it('decides at the boundary by one measurement: exactly the ruler\'s width fits, a pixel less does not', () => {
        const ruler = { clientWidth: 896 };
        const onRoom = vi.fn();
        roomFor(box(896, ruler), onRoom);
        expect(onRoom).toHaveBeenLastCalledWith(true);
        roomFor(box(895, ruler), onRoom);
        expect(onRoom).toHaveBeenLastCalledWith(false);
    });
});
