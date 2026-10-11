import { describe, expect, it } from 'vitest';
import settings from './Settings.svelte?raw';
import connection from '../components/settings/ConnectionSettings.svelte?raw';
import app from '../../App.svelte?raw';
import sidebar from '../components/Sidebar.svelte?raw';

describe('independent garden camera option', () => {
    it('loads, checks dirty state, saves and binds the camera and label settings', () => {
        for (const name of ['gardenCameras', 'gardenLabels']) expect(settings).toContain(`bind:${name}`);
        expect(settings).toContain('garden_cameras: gardenCameras');
        expect(settings).toContain('garden_labels: gardenLabels');
        expect(connection).toContain('aria-pressed={gardenCameras.includes(camera)}');
        expect(connection).not.toContain("[camera]: 'garden'");
    });
    it('gates navigation and direct route access to the owner', () => {
        expect(sidebar).toMatch(/path: '\/garden'.*requiresAuth: true/);
        expect(app).toContain("currentRoute.startsWith('/garden')");
        expect(app).toContain('loader={loadGardenPage}');
    });
});
