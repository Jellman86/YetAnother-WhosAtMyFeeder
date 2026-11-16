import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';

describe('Settings › Models runtime line', () => {
    it('reads on entry, then follows the pushed model revision without dropping one that lands mid-read', () => {
        expect(settingsSource).toMatch(/const follower = followRevisions\(\s*loadClassifierStatus,/);
        expect(settingsSource).toContain('follower.start();');
        expect(settingsSource).toContain('systemStatusStore.subscribe((snapshot) => follower.observe(snapshot.model.revision))');
    });
});
