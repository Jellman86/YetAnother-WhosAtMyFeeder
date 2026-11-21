import { describe, expect, it } from 'vitest';
import modalSource from './DetectionModal.svelte?raw';

/** The record's small finishing details, from the Mac polish pass (NIGGLES 7, 11 and 12). */
describe('the record draws its media controls, conditions and reference photo cleanly', () => {
    const mediaActions = modalSource.slice(
        modalSource.indexOf('data-detection-media-actions>'),
        modalSource.indexOf('data-detection-details-column')
    );

    it('casts a shadow from its media buttons, which float over the photo at every width', () => {
        // The buttons sit on the photograph's lower edge on every screen, so each keeps the shadow that
        // lifts it off the picture; none is left to a band of its own under the photo.
        expect(mediaActions.match(/[\s"]shadow-(lg|xl)\s/g)?.length).toBeGreaterThanOrEqual(5);
        expect(mediaActions).not.toContain('max-sm:shadow-');
        expect(modalSource).toContain('pointer-events-none absolute inset-x-4 bottom-full z-30 mb-3 flex flex-wrap items-center gap-2" data-detection-media-actions');
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
