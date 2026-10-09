import { describe, expect, it } from 'vitest';
import connectionSource from './ConnectionSettings.svelte?raw';

describe('the Active Cameras list', () => {
    it('grows with the page instead of scrolling inside its card', () => {
        // A capped inner scroller slid the first camera under the card header and clipped
        // the nest window beneath the list, which read as a broken panel.
        const list = connectionSource.match(/<div class="([^"]*)" data-camera-list>/)?.[1] ?? '';
        expect(list).not.toMatch(/overflow-y-auto|max-h-/);
    });

    it('keeps the nest window after the cameras, in the same flow', () => {
        expect(connectionSource.indexOf('data-nest-dedupe')).toBeGreaterThan(connectionSource.indexOf('data-camera-list'));
    });
});
