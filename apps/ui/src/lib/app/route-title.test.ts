import { describe, expect, it } from 'vitest';
import { documentTitle, routeIdFor } from './route-title';

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
