import { describe, expect, it } from 'vitest';

import appSource from './App.svelte?raw';

describe('App route loading', () => {
    it('does not put every operational page in the initial bundle', () => {
        for (const page of [
            'Dashboard',
            'Events',
            'Species',
            'AudioHistory',
            'Settings',
            'About',
            'Notifications',
            'ModelEvaluation'
        ]) {
            expect(appSource).not.toContain(`import ${page} from './lib/pages/${page}.svelte'`);
            expect(appSource).toContain(`import('./lib/pages/${page}.svelte')`);
        }
    });

    it('uses one shared, recoverable loading surface for lazy routes', () => {
        expect(appSource).toContain("import LazyRoute from './lib/components/LazyRoute.svelte'");
        expect(appSource).toContain('onLoadError={handleRouteLoadError}');
    });
});
