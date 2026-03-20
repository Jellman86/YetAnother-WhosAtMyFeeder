import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';

describe('Explorer page layout', () => {
    it('uses a compact desktop grid for the primary filters', () => {
        expect(eventsSource).toContain('card-base rounded-2xl p-4 grid gap-3 lg:grid-cols-[repeat(3,minmax(0,1fr))_auto_auto]');
        expect(eventsSource).toContain('class="select-base min-w-0 w-full"');
    });

    it('labels the page-level selection toggle as Multi Select', () => {
        expect(eventsSource).toContain("$_('common.multi_select', { default: 'Multi Select' })");
        expect(eventsSource).not.toContain("selectionMode ? $_('common.cancel') : $_('common.select', { default: 'Select' })");
    });
});
