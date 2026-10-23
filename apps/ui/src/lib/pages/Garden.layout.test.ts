import { describe, expect, it } from 'vitest';
import settings from './Settings.svelte?raw';
import connection from '../components/settings/ConnectionSettings.svelte?raw';
import gardenBeta from '../components/settings/GardenBetaSettings.svelte?raw';
import app from '../../App.svelte?raw';
import sidebar from '../components/Sidebar.svelte?raw';
import garden from './Garden.svelte?raw';

describe('independent garden camera option', () => {
    it('loads, checks dirty state, saves and binds every Garden setting from Beta features', () => {
        for (const [prop, state] of [['cameras', 'gardenCameras'], ['motionCameras', 'gardenMotionCameras'], ['labels', 'gardenLabels'], ['motionConfidence', 'gardenMotionConfidence']]) {
            expect(settings).toContain(`bind:${prop}={${state}}`);
        }
        expect(settings).toContain('garden_cameras: gardenCameras');
        expect(settings).toContain('garden_labels: gardenLabels');
        expect(settings).toContain('garden_motion_cameras: gardenMotionCameras');
        expect(settings).toContain('garden_motion_confidence: gardenMotionConfidence');
        expect(settings).toContain("key: 'gardenMotionConfidence'");
        expect(gardenBeta).toContain('aria-pressed={watched}');
        expect(gardenBeta).toContain('aria-pressed={motionCameras.includes(camera)}');
        expect(connection).not.toContain('gardenCameras');
        expect(connection).not.toContain("[camera]: 'garden'");
    });
    it('shows the motion threshold on the Garden page and sends changes to Beta features', () => {
        expect(garden).not.toContain('updateSettings');
        expect(garden).toContain("garden.confidence_current");
        expect(garden).toContain("onNavigate('/settings/beta')");
    });
    it('shows measured collection status and distinguishes motion evidence from Frigate labels', () => {
        expect(garden).toContain('motion.message');
        expect(garden).toContain("item.source_kind === 'motion'");
        expect(garden).not.toMatch(/installGarden(Model|Motion)/);
        expect(garden).toContain('garden.motion_download_in_settings');
        expect(garden).toContain('garden.model_download_in_settings');
        expect(garden).toContain('motion.photo_retention_days');
    });
    it('gates navigation and direct route access to the owner', () => {
        expect(sidebar).toMatch(/path: '\/garden'.*requiresAuth: true/);
        expect(app).toContain("currentRoute.startsWith('/garden')");
        expect(app).toContain('loader={loadGardenPage}');
    });
});
