import { describe, expect, it } from 'vitest';
import settings from './Settings.svelte?raw';
import connection from '../components/settings/ConnectionSettings.svelte?raw';
import app from '../../App.svelte?raw';
import sidebar from '../components/Sidebar.svelte?raw';
import garden from './Garden.svelte?raw';

describe('independent garden camera option', () => {
    it('loads, checks dirty state, saves and binds the camera and label settings', () => {
        for (const name of ['gardenCameras', 'gardenLabels', 'gardenMotionCameras']) expect(settings).toContain(`bind:${name}`);
        expect(settings).toContain('garden_cameras: gardenCameras');
        expect(settings).toContain('garden_labels: gardenLabels');
        expect(connection).toContain('aria-pressed={gardenCameras.includes(camera)}');
        expect(connection).not.toContain("[camera]: 'garden'");
        expect(settings).toContain('garden_motion_cameras: gardenMotionCameras');
        expect(connection).toContain('aria-pressed={gardenMotionCameras.includes(camera)}');
    });
    it('shows measured collection status and distinguishes motion evidence from Frigate labels', () => {
        expect(garden).toContain('motion.message');
        expect(garden).toContain("item.source_kind === 'motion'");
        expect(garden).toContain('downloadMotionDetector');
        expect(garden).toContain('motion.photo_retention_days');
    });
    it('gates navigation and direct route access to the owner', () => {
        expect(sidebar).toMatch(/path: '\/garden'.*requiresAuth: true/);
        expect(app).toContain("currentRoute.startsWith('/garden')");
        expect(app).toContain('loader={loadGardenPage}');
    });
});
