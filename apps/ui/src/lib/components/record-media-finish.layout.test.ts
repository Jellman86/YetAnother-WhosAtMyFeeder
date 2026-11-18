import { describe, expect, it } from 'vitest';
import modalSource from './DetectionModal.svelte?raw';

/** The record's small finishing details, from the Mac polish pass (NIGGLES 7, 11 and 12). */
describe('the record draws its media controls, conditions and reference photo cleanly', () => {
    const mediaActions = modalSource.slice(
        modalSource.indexOf('data-detection-media-actions>'),
        modalSource.indexOf('data-detection-details-column')
    );

    it('casts a shadow from its media buttons only where they float over the photo', () => {
        // From `sm` the buttons sit in the black band under the photo, and a shadow there spilled
        // onto the white panel below it as a grey smudge.
        expect(mediaActions).not.toMatch(/[\s"]shadow-(lg|xl)\s/);
        expect(mediaActions.match(/max-sm:shadow-(lg|xl)/g)?.length).toBeGreaterThanOrEqual(5);
    });

    it('never starts a wrapped Conditions line with a separator, or parts a label from its figure', () => {
        expect(modalSource).toContain("return parts.join('\\u00a0· ');");
        expect(modalSource).not.toContain("return parts.join(' · ');");
        // A label stays with its figure, so "Cloud cover" never ends a line without its percentage.
        expect(modalSource).toContain("parts.push(`${$_('detection.weather_cloud')}\\u00a0${Math.round(detection.weather_cloud_cover)}%`);");
    });

    it('gives the species reference photo a ground while it loads', () => {
        expect(modalSource).toContain('class="h-12 w-12 shrink-0 rounded-full border border-line bg-surface-raised object-cover"');
    });
});
