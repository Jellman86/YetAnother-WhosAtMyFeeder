import { describe, expect, it } from 'vitest';
import { installMediaFallback } from './media-fallback';

/** Just enough of an element to carry the mark: a tag name and attributes. */
class FakeElement extends EventTarget {
    readonly attributes = new Set<string>();
    constructor(readonly tagName: string) {
        super();
    }
    toggleAttribute(name: string, force: boolean): boolean {
        if (force) this.attributes.add(name);
        else this.attributes.delete(name);
        return force;
    }
}

/**
 * A document that counts its capture listeners. Error and load events do not bubble, so the
 * handler listens on the way down; here an event is delivered to the document with the element
 * as its target, as capture would.
 */
class FakeDocument extends EventTarget {
    readonly listening = new Map<string, number>();
    override addEventListener(type: string, listener: EventListenerOrEventListenerObject | null, options?: boolean | AddEventListenerOptions): void {
        this.listening.set(type, (this.listening.get(type) ?? 0) + 1);
        super.addEventListener(type, listener, options);
    }
    override removeEventListener(type: string, listener: EventListenerOrEventListenerObject | null, options?: boolean | EventListenerOptions): void {
        this.listening.set(type, (this.listening.get(type) ?? 0) - 1);
        super.removeEventListener(type, listener, options);
    }
    deliver(type: 'error' | 'load', target: EventTarget): void {
        const event = new Event(type);
        Object.defineProperty(event, 'target', { value: target });
        this.dispatchEvent(event);
    }
}

describe('installMediaFallback', () => {
    it('marks a picture that fails and clears the mark when it later loads', () => {
        const root = new FakeDocument();
        installMediaFallback(root);
        const image = new FakeElement('IMG');
        root.deliver('error', image);
        expect(image.attributes.has('data-media-failed')).toBe(true);
        root.deliver('load', image);
        expect(image.attributes.has('data-media-failed')).toBe(false);
    });

    it('leaves anything that is not a picture alone', () => {
        const root = new FakeDocument();
        installMediaFallback(root);
        const script = new FakeElement('SCRIPT');
        root.deliver('error', script);
        expect(script.attributes.size).toBe(0);
    });

    it('listens while installed and stops when cleaned up', () => {
        const root = new FakeDocument();
        const cleanup = installMediaFallback(root);
        expect(root.listening).toEqual(new Map([['error', 1], ['load', 1]]));
        cleanup();
        expect(root.listening).toEqual(new Map([['error', 0], ['load', 0]]));
        const image = new FakeElement('IMG');
        root.deliver('error', image);
        expect(image.attributes.has('data-media-failed')).toBe(false);
    });
});
