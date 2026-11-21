import { afterEach, describe, expect, it, vi } from 'vitest';

import { whenNearViewport } from './near-viewport';

type Callback = (entries: Array<{ isIntersecting: boolean }>) => void;

function installObserver(): { report(isIntersecting: boolean): void; disconnected(): boolean; margin(): string | undefined } {
    let callback: Callback = () => {};
    let disconnected = false;
    let margin: string | undefined;
    vi.stubGlobal('IntersectionObserver', class {
        constructor(cb: Callback, options?: { rootMargin?: string }) {
            callback = cb;
            margin = options?.rootMargin;
        }
        observe(): void {}
        disconnect(): void { disconnected = true; }
    });
    return { report: (isIntersecting) => callback([{ isIntersecting }]), disconnected: () => disconnected, margin: () => margin };
}

afterEach(() => vi.unstubAllGlobals());

describe('whenNearViewport', () => {
    const node = {} as Element;

    it('waits until the node is near the viewport, then runs once and stops watching', () => {
        const observer = installObserver();
        const onNear = vi.fn();
        whenNearViewport(node, onNear);

        observer.report(false);
        expect(onNear).not.toHaveBeenCalled();
        observer.report(true);
        observer.report(true);
        expect(onNear).toHaveBeenCalledOnce();
        expect(observer.disconnected()).toBe(true);
    });

    it('starts before the node is on screen so the work is done by the time it scrolls in', () => {
        const observer = installObserver();
        whenNearViewport(node, vi.fn());
        expect(observer.margin()).toBe('300px');
    });

    it('stops watching when the node is removed first', () => {
        const observer = installObserver();
        const onNear = vi.fn();
        whenNearViewport(node, onNear).destroy();
        expect(observer.disconnected()).toBe(true);
        expect(onNear).not.toHaveBeenCalled();
    });

    it('runs straight away where the browser cannot observe', () => {
        vi.stubGlobal('IntersectionObserver', undefined);
        const onNear = vi.fn();
        whenNearViewport(node, onNear);
        expect(onNear).toHaveBeenCalledOnce();
    });
});
