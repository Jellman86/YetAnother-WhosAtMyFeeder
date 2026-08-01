import { describe, expect, it } from 'vitest';
import page from './ManualObservation.svelte?raw';
import app from '../../App.svelte?raw';
import sidebar from '../components/Sidebar.svelte?raw';

describe('manual observation flow layout', () => {
    it('uses a full-page connected four-step workflow instead of a dialog', () => {
        expect(page).toContain("steps.upload");
        expect(page).toContain("steps.analyse");
        expect(page).toContain("steps.review");
        expect(page).toContain("steps.save");
        expect(page).toContain('lg:grid-cols-[16rem_minmax(0,1fr)]');
        expect(page).not.toContain('role="dialog"');
    });

    it('keeps upload accessible and analysis recovery explicit', () => {
        expect(page).toContain('type="file"');
        expect(page).toContain('ondrop={handleDrop}');
        expect(page).toContain('role="alert"');
        expect(page).toContain('retryManualObservation');
        expect(page).toContain('aria-live="polite"');
    });

    it('is a lazy owner route exposed in the observation navigation', () => {
        expect(app).toContain("import('./lib/pages/ManualObservation.svelte')");
        expect(app).toContain("currentRoute.startsWith('/observations/new')");
        expect(sidebar).toContain("path: '/observations/new'");
        expect(sidebar).toContain('requiresAuth: true');
    });
});
