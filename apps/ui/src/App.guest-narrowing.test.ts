import { describe, expect, it } from 'vitest';
import appSource from './App.svelte?raw';

function handlerBody(name: string): string {
    const start = appSource.indexOf(`${name}: () => {`);
    expect(start, `${name} handler`).toBeGreaterThan(-1);
    const end = appSource.indexOf('\n      },', start);
    expect(end).toBeGreaterThan(start);
    return appSource.slice(start, end);
}

describe('a visitor told that records left their history', () => {
    it('marks answers in flight out of date before the scheduled refresh is asked for', () => {
        const body = handlerBody('onPublicHistoryNarrowed');
        const marked = body.indexOf('detectionsStore.markPublicHistoryNarrowed();');
        const refreshed = body.indexOf('publicHistoryRefresh.notify();');
        expect(marked).toBeGreaterThan(-1);
        expect(refreshed).toBeGreaterThan(marked);
    });

    it('marks answers in flight out of date before reloading for a change of sharing', () => {
        const body = handlerBody('onPublicAccessChanged');
        const guestOnly = body.indexOf('if (!authStore.isGuest) return;');
        const marked = body.indexOf('detectionsStore.markPublicHistoryNarrowed();');
        const reloaded = body.indexOf('window.location.reload();');
        expect(guestOnly).toBeGreaterThan(-1);
        expect(marked).toBeGreaterThan(guestOnly);
        expect(reloaded).toBeGreaterThan(marked);
    });
});
