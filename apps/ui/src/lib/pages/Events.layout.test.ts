import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';

describe('Explorer page layout', () => {
    it('uses a compact desktop grid for the primary filters', () => {
        expect(eventsSource).toContain('card-base rounded-2xl p-4 space-y-3');
        expect(eventsSource).toContain('class="grid gap-3 lg:grid-cols-3"');
        expect(eventsSource).toContain('class="select-base min-w-0 w-full"');
    });

    it('labels the page-level selection toggle as Multi Select', () => {
        expect(eventsSource).toContain('{#if authStore.hasOwnerAccess}');
        expect(eventsSource).toContain("$_('common.multi_select', { default: 'Multi Select' })");
        expect(eventsSource).not.toContain("selectionMode ? $_('common.cancel') : $_('common.select', { default: 'Select' })");
    });

    it('keeps selection wording in the bulk toolbar instead of inside each card', () => {
        expect(eventsSource).toContain('{#if authStore.hasOwnerAccess && selectionMode}');
        expect(eventsSource).toContain('{#if authStore.hasOwnerAccess && showBulkTagModal}');
        expect(eventsSource).toContain("selectedEventIds.length");
        expect(eventsSource).toContain("$_('common.selected', { default: 'selected' })");
        expect(eventsSource).toContain("$_('common.select', { default: 'Select' }) + ' events to act on.'");
    });

    it('treats AI analysis fields as part of selected-event sync state', () => {
        expect(eventsSource).toContain('asText(d.ai_analysis)');
        expect(eventsSource).toContain('asText(d.ai_analysis_timestamp)');
    });
});
