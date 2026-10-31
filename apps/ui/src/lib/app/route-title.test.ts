import { describe, expect, it } from 'vitest';
import { documentTitle, routeIdFor, routeOffersRefresh } from './route-title';
import dashboardSource from '../pages/Dashboard.svelte?raw';
import eventsSource from '../pages/Events.svelte?raw';
import speciesSource from '../pages/Species.svelte?raw';
import settingsSource from '../pages/Settings.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';
import notificationsSource from '../pages/Notifications.svelte?raw';

describe('routeIdFor', () => {
    it('names the page each address opens', () => {
        expect(routeIdFor('/')).toBe('dashboard');
        expect(routeIdFor('/events')).toBe('explorer');
        expect(routeIdFor('/events?visitors=garden&review=pending')).toBe('explorer');
        expect(routeIdFor('/species')).toBe('leaderboard');
        expect(routeIdFor('/observations/new')).toBe('add_observation');
        expect(routeIdFor('/audio')).toBe('audio_history');
        expect(routeIdFor('/notifications')).toBe('notifications');
        expect(routeIdFor('/settings/health')).toBe('settings');
        expect(routeIdFor('/diagnostics/model-eval')).toBe('model_evaluation');
        expect(routeIdFor('/about')).toBe('about');
    });

    it('returns null for an address no page answers', () => {
        expect(routeIdFor('/not-a-page')).toBeNull();
        expect(routeIdFor('/diagnostics')).toBeNull();
        expect(routeIdFor('/observations')).toBeNull();
    });
});

describe('documentTitle', () => {
    it('names the page first, then the product', () => {
        expect(documentTitle('Explorer')).toBe('Explorer · YA-WAMF');
    });

    it('falls back to the product name alone', () => {
        expect(documentTitle('')).toBe('YA-WAMF');
        expect(documentTitle('   ')).toBe('YA-WAMF');
    });
});

describe('routeOffersRefresh', () => {
    it('holds the header refresh control for every page that registers one, before the page arrives', () => {
        // Otherwise the control is inserted when the lazy page mounts and the header controls move.
        const pages = [
            ['dashboard', dashboardSource],
            ['explorer', eventsSource],
            ['leaderboard', speciesSource],
            ['settings', settingsSource],
            ['about', aboutSource],
            ['notifications', notificationsSource]
        ] as const;
        for (const [route, source] of pages) {
            expect(routeOffersRefresh(route), route).toBe(source.includes('pageRefreshAction.register('));
        }
    });

    it('offers no refresh on an address no page answers', () => {
        expect(routeOffersRefresh(null)).toBe(false);
    });
});
