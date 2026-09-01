import { describe, expect, it } from 'vitest';
import dashboard from './Dashboard.svelte?raw';
import events from './Events.svelte?raw';

/**
 * An action a person took must say when it fails. Logging to the browser console
 * and returning quietly leaves them looking at a screen that did nothing, with no
 * way to tell a failure from a slow network. The worst case shipped: confirming
 * "the record and its media leave the history permanently", the delete failing,
 * and the interface saying nothing at all.
 */
function silentCatches(source: string): string[] {
    const lines = source.split('\n');
    const offenders: string[] = [];
    lines.forEach((line, index) => {
        if (!line.includes('console.error')) return;
        let end = index;
        while (end < lines.length && !/^\s*\}/.test(lines[end])) end += 1;
        const block = lines.slice(Math.max(0, index - 4), end).join(' ');
        const tellsUser = /toastStore|error\s*=|errorMessage/.test(block);
        // A fallback that still gives the person a usable result is not a silent failure.
        const degradesGracefully = /bulkSearchResults\s*=|AbortError/.test(block);
        if (!tellsUser && !degradesGracefully) offenders.push(lines[index].trim());
    });
    return offenders;
}

describe('a failed action is never silent', () => {
    it('reports every failed owner action on the dashboard', () => {
        expect(silentCatches(dashboard)).toEqual([]);
    });

    it('reports every failed owner action in the explorer', () => {
        expect(silentCatches(events)).toEqual([]);
    });

    it('says a permanent delete failed rather than leaving the dialog as it was', () => {
        // The confirm promises the record leaves history for good. If the request
        // fails the person must be told, or they cannot know which happened.
        expect(dashboard).toContain("console.error('Failed to delete detection', e)");
        const deleteBlock = dashboard.slice(dashboard.indexOf('async function handleDelete'));
        expect(deleteBlock.slice(0, 900)).toContain('toastStore.show(getErrorMessage(e)');
    });
});
