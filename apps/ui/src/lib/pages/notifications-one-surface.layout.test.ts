import { describe, expect, it } from 'vitest';
import source from './Notifications.svelte?raw';
import banner from '../components/JobCircuitBanner.svelte?raw';
import {
    canonicalizeNotificationRouteForAccess,
    getCanonicalNotificationRoute
} from '../app/notifications_route';

const pageModules = import.meta.glob('./*.svelte');

describe('one notifications surface', () => {
    it('has no separate jobs view to get out of step with the timeline', () => {
        // The jobs view showed the same work three times over: four tiles, a "Work Lanes"
        // list, and an "Active Work" list, with two lanes carrying the same title. The
        // timeline already carries every job, so the second view was only a way to disagree
        // with the first.
        expect(Object.keys(pageModules)).not.toContain('./Jobs.svelte');
        expect(source).not.toContain('Jobs.svelte');
        expect(source).not.toContain('data-jobs-page');
        expect(source).not.toContain('notifications.job_manager');
    });

    it('sends anyone holding a jobs link to the timeline that replaced it', () => {
        for (const path of ['/jobs', '/jobs/anything', '/notifications/jobs']) {
            expect(getCanonicalNotificationRoute(path)).toBe('/notifications');
            expect(canonicalizeNotificationRouteForAccess(path, true)).toBe('/notifications');
            expect(canonicalizeNotificationRouteForAccess(path, false)).toBe('/notifications');
        }
    });

    it('keeps the one thing the jobs view could do that the timeline cannot', () => {
        // A paused queue is work stopped waiting for a person, and resuming it was only
        // reachable from the view being removed.
        expect(source).toContain("import JobCircuitBanner from '../components/JobCircuitBanner.svelte'");
        expect(source).toContain('<JobCircuitBanner />');
        expect(banner).toContain('resetVideoCircuit()');
        expect(banner).toContain('jobs.circuit_open_message');
        // Amber is reserved for work that needs a person, and it must not be the only signal.
        expect(banner).toContain('border-amber-200/80');
        expect(banner).toContain('role="alert"');
        for (const button of banner.match(/<button\b[\s\S]*?>/g) ?? []) {
            expect(button).toContain('min-h-11');
        }
    });

    it('is owner-only at the data boundary, not just visually', () => {
        expect(banner).toContain('authStore.showSettings');
    });
});
