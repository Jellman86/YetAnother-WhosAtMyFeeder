import { describe, expect, it } from 'vitest';
import app from '../../App.svelte?raw';
import sidebar from './Sidebar.svelte?raw';
import header from './AppPageHeader.svelte?raw';
import link from './AddObservationLink.svelte?raw';
import explorer from '../pages/Events.svelte?raw';

// Add observation is an action, not a place: it left the sidebar for the header's owner controls (the
// phone menu, where the header has no room), with a labelled entry on the Explorer, the page its
// observations join.
describe('Add observation entry points', () => {
    it('is no longer a place in the docked sidebar, while its address still opens the page', () => {
        // A place in the phone menu only, where the header has no room for it (decided in one tested function).
        expect(sidebar).not.toContain("'/observations/new'");
        expect(sidebar).toContain('const addObservation = $derived(addObservationEntry(currentRoute, authStore.showSettings, isMobile));');
        expect(sidebar).toContain('path: ADD_OBSERVATION_PATH');
        expect(sidebar).toContain('requiresAuth: true, available: addObservation.inMenu }');
        expect(app).toContain("add_observation: loadManualObservationPage");
        expect(app).toContain("{:else if routeId === 'add_observation'}");
    });

    it('is one shared link: a real address, handled in place on a plain click, named by nav.add_observation', () => {
        expect(link).toContain('href={toAppPath(ADD_OBSERVATION_PATH)}');
        expect(link).toContain('if (!onNavigate || !isPlainClick(event)) return;');
        expect(link).toContain("$_('nav.add_observation', { default: 'Add observation' })");
        expect(link).toContain("aria-current={current ? 'page' : undefined}");
    });

    it('sits in the header cluster after refresh and before the camera, for the owner only', () => {
        // The owner rule is the sidebar's own: owner access (authStore.showSettings), decided in one tested function.
        expect(app).toContain('addObservation={addObservationEntry(currentRoute, authStore.showSettings, isMobile)}');
        expect(header).toContain('{#if addObservation.inHeader}');
        const refresh = header.indexOf('pageRefreshAction.run()');
        const add = header.indexOf('<AddObservationLink');
        const camera = header.indexOf('<CameraStatus');
        expect(refresh).toBeGreaterThan(-1);
        expect(add).toBeGreaterThan(refresh);
        expect(camera).toBeGreaterThan(add);
        // An icon button like its neighbours, with its name as a tooltip and its page marked current.
        expect(header).toContain('variant="icon"');
        expect(header).toContain('current={addObservation.current}');
        expect(link).toContain("title={variant === 'icon' ? label : undefined}");
        expect(link).toContain('min-h-11 min-w-11');
        expect(link).toContain('focus-ring');
    });

    it('is a labelled kit button on the Explorer, for the owner only', () => {
        expect(app).toContain('loader={loadEventsPage}\n                      props={{ onNavigate: navigate }}');
        // The Explorer is never the Add observation page, so only the owner rule applies.
        expect(explorer).toMatch(/\{#if authStore\.showSettings\}\s*<AddObservationLink variant="labelled" \{onNavigate\} \/>/);
        expect(explorer).toContain('<AddObservationLink variant="labelled" {onNavigate} />');
        expect(link).toContain('btn btn-secondary');
    });
});
