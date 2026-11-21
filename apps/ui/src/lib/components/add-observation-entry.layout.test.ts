import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import app from '../../App.svelte?raw';
import sidebar from './Sidebar.svelte?raw';
import header from './AppPageHeader.svelte?raw';
import link from './AddObservationLink.svelte?raw';
import explorer from '../pages/Events.svelte?raw';

// Read from disk: a stylesheet imported with ?raw is empty under the test runner.
const css: string = readFileSync(new URL('../../app.css', import.meta.url), 'utf8');

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
    });

    it('is a labelled kit button on the Explorer, for the owner only, that loads the page early like the header', () => {
        expect(app).toMatch(/loader=\{loadEventsPage\}\s*props=\{\{\s*onNavigate: navigate,\s*onPrefetch: \(path\) => void prefetchRoute\(path\)\s*\}\}/);
        // The Explorer is never the Add observation page, so only the owner rule applies.
        expect(explorer).toMatch(/\{#if authStore\.showSettings\}\s*<AddObservationLink variant="labelled" \{onNavigate\} \{onPrefetch\} \/>/);
        expect(link).toContain('btn btn-secondary');
    });

    it('is drawn in the Explorer header row on a desktop only, never as a row of its own', () => {
        expect(explorer).not.toContain('data-explorer-add-observation');
        expect(explorer).toMatch(/\{@render multiSelectToggle\(\)\}\s*\{@render addObservation\(\)\}/);
    });

    it('marks its page as the bell and Settings mark theirs: one shared current style in the kit', () => {
        expect(css).toContain('@utility header-control {');
        expect(css).toContain('@utility header-control-current {');
        expect(link).toContain("current ? 'header-control-current' : 'header-control'");
        expect(header).toContain("buttonClass={notificationsCurrent ? 'relative header-control-current' : 'relative header-control'}");
        expect(header).toContain("aria-current={settingsCurrent ? 'page' : undefined}");
        expect(header).toContain("class={settingsCurrent ? 'header-control-current' : 'header-control'}");
        expect(app).toContain("settingsCurrent={routeId === 'settings'}");
    });
});
