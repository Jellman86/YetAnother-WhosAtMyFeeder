import { describe, expect, it } from 'vitest';
import page from './ManualObservation.svelte?raw';
import app from '../../App.svelte?raw';
import sidebar from '../components/Sidebar.svelte?raw';
import locationPicker from '../components/LocationPicker.svelte?raw';

describe('manual observation flow layout', () => {
    it('keeps the four steps visible without spending a sidebar on them', () => {
        expect(page).toContain("steps.upload");
        expect(page).toContain("steps.analyse");
        expect(page).toContain("steps.review");
        expect(page).toContain("steps.save");
        // The evidence needs the room, so progress lives in a slim bar, not a 16rem rail.
        expect(page).toContain('data-manual-observation-bar');
        expect(page).toContain("aria-current={stage === item.number ? 'step' : undefined}");
        expect(page).not.toContain('lg:grid-cols-[16rem_minmax(0,1fr)]');
        expect(page).not.toContain('role="dialog"');
    });

    it('keeps upload accessible and analysis recovery explicit', () => {
        expect(page).toContain('type="file"');
        expect(page).toContain('ondrop={handleDrop}');
        expect(page).toContain('role="alert"');
        expect(page).toContain('retryManualObservation');
        expect(page).toContain('aria-live="polite"');
    });

    it('shows friendly species names and retains an editable sighting location', () => {
        expect(page).toContain('prediction.common_name');
        expect(page).toContain('prediction.scientific_name');
        expect(page).toContain('<LocationPicker');
        expect(page).toContain('location_source');
        expect(page).toContain('locationOutOfRange');
        expect(page).toContain("manual_observation.location.invalid");
        expect(locationPicker).toContain("map.on('click'");
        expect(locationPicker).toContain('draggable: true');
        expect(locationPicker).toContain('aria-live="polite"');
    });

    it('is a lazy owner route exposed in the observation navigation', () => {
        expect(app).toContain("import('./lib/pages/ManualObservation.svelte')");
        expect(app).toContain("currentRoute.startsWith('/observations/new')");
        expect(sidebar).toContain("path: '/observations/new'");
        expect(sidebar).toContain('requiresAuth: true');
    });
});
