import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';
import appSource from '../../App.svelte?raw';
import tabsSource from '../components/settings/SettingsTabs.svelte?raw';
import panelSource from '../components/settings/SystemHealthPanel.svelte?raw';
import errorsSource from './Errors.svelte?raw';
import sidebarSource from '../components/Sidebar.svelte?raw';
import enSettings from '../i18n/locales/en/settings.json';
import enStatus from '../i18n/locales/en/status.json';
import { SETTINGS_PART_ORDER, SETTINGS_SECTION_ORDER } from '../settings/settings-route';

const en = { settings: enSettings, status: enStatus };

describe('Health page', () => {
    it('is a page of its own under Manage, not a Settings section, and old addresses land on it', () => {
        expect(SETTINGS_SECTION_ORDER).not.toContain('health');
        expect(SETTINGS_PART_ORDER).not.toContain('health');
        expect(tabsSource).not.toContain('settings.tabs.health');
        expect(settingsSource).not.toContain("activeSection === 'health'");
        expect(settingsSource).not.toContain('Errors.svelte');
        expect(appSource).toContain("routeId === 'health'");
        expect(appSource).toContain("import('./lib/pages/Errors.svelte')");
        // Bookmarks to the tab and to the older errors page both open the page.
        expect(appSource).toContain("path === '/settings/health'");
        expect(appSource).toContain("path === '/settings/errors'");
        expect(sidebarSource).toContain("path: '/system-health'");
    });

    it('opens on what the host is doing, with this app named and the rest an honest remainder', () => {
        // The health page builds the System card, so its verdict and detail live inside it.
        expect(settingsSource).not.toContain('<SystemHealthPanel');
        expect(errorsSource).toContain("<SystemHealthPanel statusRead={readState !== 'reading'}>");
        expect(errorsSource).toContain('{#snippet status()}');
        expect(errorsSource).toContain('{#snippet details()}');
        expect(errorsSource.indexOf('</SystemHealthPanel>')).toBeLessThan(errorsSource.indexOf('data-health-timeline'));
        // The chart fills its column and its markers stay round.
        expect(panelSource).toContain('preserveAspectRatio="none"');
        expect(panelSource).not.toContain('<circle');
        expect(panelSource).toContain("fetchSystemTelemetryHistory(signal)");
        // One axis, a named line per readable device with a legend, a crosshair tooltip,
        // and a text summary for the window.
        expect(panelSource).toContain('chartSeries(history, cpuLabel)');
        expect(panelSource).toContain('seriesSegments(points, line.load, windowSeconds)');
        expect(panelSource).toContain('data-system-health-tooltip');
        expect(panelSource).toContain('data-system-health-summary');
        // Every line says what its number covers: a GPU inside a container is this app's work only.
        expect(panelSource).toContain('scopeNote(line.scope)');
        expect(en.settings.system_health.scope_app).toBe('this app only');
        expect(en.settings.system_health.app_scope_note).toContain('not visible here');
        // A device that is present but unmeasurable is named rather than silently missing.
        expect(panelSource).toContain('unreadableAccelerators(history)');
        expect(en.settings.system_health.unreadable_nvidia).toContain('no utilisation counter');
        // A host whose counters cannot be read says so, in words, instead of drawing nothing.
        expect(panelSource).toContain('data-system-health-cpu-unmeasured');
        expect(panelSource).toContain('data-system-health-no-accelerator');
        expect(en.settings.system_health.cpu_unmeasured).toContain('cannot be measured');
        // Dense resource headers remain separated at phone widths without introducing
        // a nested horizontal scroller.
        expect(panelSource).toContain('<thead class="text-xs font-semibold text-ink">');
        expect(panelSource).not.toContain('data-system-health-table-container');
        // The keyboard's crosshair is a real range control, not a focusable picture, and it
        // stays out of sight until focused so it is not a handle attached to nothing.
        expect(panelSource).toContain('data-system-health-scrub');
        expect(panelSource).toContain('type="range"');
        expect(panelSource).toContain('.system-health-scrub:focus-visible');
        expect(panelSource).toContain('aria-valuetext={inspectedSpoken}');
        // The inspected sample is marked on each line, so the crosshair belongs to something.
        expect(panelSource).toContain('data-system-health-marker');
        // The remainder is a row of its own, hatched as well as grey, and says why it has no name.
        expect(panelSource).toContain("other_host: 'system-health-hatched'");
        expect(en.settings.system_health.role_other_host_note).toContain('Cannot be named');
        expect(sidebarSource).toContain("navigateAndClose('/system-health')");
        // Only the owner gets the link; its name is the words it shows, not a label over the whole card.
        expect(sidebarSource).toMatch(/\{#if authStore\.showSettings\}\s*<a\s+href="\/system-health"/);
        expect(sidebarSource).not.toMatch(/data-sidebar-status-link[\s\S]{0,200}aria-label|aria-label[^\n]*\n\s*data-sidebar-status-link/);
        // One name for the page: the sidebar item, this link and the notifications link all say Health.
        expect(en.status.open_health).toBe('Health');
    });

    it('counts open problems from the one reading that sets the verdict, so the two always agree', () => {
        // Open incidents join the connection problems in the verdict card; the panel below holds
        // only what is over, so it can never say "0 open" beside a degraded verdict.
        expect(errorsSource).toContain('let openItems = $derived(');
        expect(errorsSource).toContain('{#each openItems as item, index (item.key)}');
        expect(errorsSource).toContain('data-health-earlier-incidents');
        expect(errorsSource).not.toContain('data-health-current-issues');
        expect(errorsSource).not.toMatch(/\.length\.toLocaleString\(\)\} (open|events)/);
        // Nothing open is called healthy only when nothing is open.
        expect(errorsSource).toContain('withOpenIncidents(healthVerdict(');
        // One time line under the verdict; no second "Updated just now" beside it.
        expect(errorsSource).not.toContain('refreshedAgoText()');
        // The button says what it clears.
        expect(en.settings).toBeTruthy();
    });

    it('names each chart line once and lets a keyboard reach the table when it scrolls', () => {
        // The scope note follows the line's name, so the name itself does not repeat it.
        expect(en.settings.system_health.legend_cpu).toBe('CPU');
        expect(panelSource).toMatch(/overflow-x-auto[^>]*tabindex="0"/);
        expect(panelSource).toContain('data-system-health-table-region');
    });

    it('shows subsystems as one ruled list in opaque ink, with the state only in a worded chip', () => {
        expect(errorsSource).toContain('data-health-subsystems');
        expect(errorsSource).toContain('<ul class="mt-2 divide-y divide-line-soft" data-health-subsystems>');
        // No tinted cards and no dimmed text: those failed contrast on 64 nodes.
        expect(errorsSource).not.toMatch(/<article class="rounded-2xl border p-5 shadow-xs \{toneClass/);
        expect(errorsSource).not.toMatch(/class="[^"]*\bopacity-(60|70|80)\b/);
        expect(errorsSource).toContain('<StatusChip tone={STATUS_TONE[statusTone(tone)]} label={chip} title={rawStatus}');
        // Labels wrap rather than cut off at large text.
        expect(errorsSource).not.toMatch(/<dt class="[^"]*truncate/);
    });

    it('says what a subsystem is doing in plain words, not breaker and queue jargon', () => {
        expect(errorsSource).not.toContain('errors_metric_open_until');
        expect(errorsSource).not.toContain("'jobs.errors_metric_in_flight'");
        expect(errorsSource).not.toContain("'jobs.errors_metric_capacity'");
        expect(errorsSource).toContain('videoSummary()');
        // A quiet pipeline with the broker down is unmeasured, not healthy.
        expect(errorsSource).toContain('pipelineCardStatus(eventPipelineVerdict(');
        // The broker's errno text is worded from its cause code and kept under Technical details.
        expect(errorsSource).toContain("connectionCauseMessage(link.last_error_cause, 'mqtt'");
        expect(errorsSource).not.toContain('jobs.errors_mqtt_last_error');
        // Known backend reason codes are said in the reader's language; the raw message is a detail.
        expect(errorsSource).toContain('diagnosticWords(event.reason_code)');
        // An unknown code gets the generic cause; the raw message is never a title, for rows or incidents.
        expect(errorsSource).not.toContain('?? event.message');
        expect(errorsSource).toContain('diagnosticWords(item.incident.primaryReasonCode)');
        expect(errorsSource).toContain('{@render technicalDetails(incidentDetails(item.incident))}');
        expect(errorsSource).not.toMatch(/\{item\.incident\.(title|summary)\}/);
    });

    it('keeps reading, read, stale and failed apart, and claims nothing it did not measure', () => {
        // Freshness changes only when a read settles, in the store, so every reader of it agrees.
        expect(errorsSource).toContain('const readState = $derived(incidentWorkspaceStore.readFreshness);');
        expect(errorsSource).not.toMatch(/refreshError = ''/);
        expect(errorsSource).toContain('data-health-read-failed');
        expect(errorsSource).toContain('data-health-stale');
        // The verdict is not a fault count when nothing was read, and its space is held while reading.
        expect(errorsSource).toContain("if (!workspacePayload) return 'unknown';");
        expect(errorsSource).toContain('min-h-28');
        // The read failure is the page's own sentence; the server's words are a detail.
        expect(errorsSource).toContain('{@render technicalDetails([refreshError])}');
        // The line under the verdict says when it was read, not the pill's word again.
        expect(errorsSource).toContain("'jobs.errors_read_at'");
    });

    it('puts Clear error history with the history it clears', () => {
        expect(errorsSource).toContain('data-health-clear');
        expect(errorsSource.indexOf('data-health-clear')).toBeGreaterThan(errorsSource.indexOf('data-health-earlier-incidents'));
        expect(errorsSource).not.toContain('{#snippet headerActions()}');
    });

    it('stacks each process on a phone so no column is cut off', () => {
        expect(panelSource).toContain('data-system-health-stacked');
        expect(panelSource).toContain('sm:hidden');
        expect(panelSource).toContain('hidden overflow-x-auto rounded-lg focus-ring sm:block');
    });

    it('puts the history and the export in a side column from 1280px, beside what happened', () => {
        const main = errorsSource.indexOf('data-health-main');
        const side = errorsSource.indexOf('data-health-side');
        expect(errorsSource).toContain('<div class="grid grid-cols-1 gap-6 xl:grid-cols-12 xl:items-start">');
        expect(main).toBeGreaterThan(-1);
        expect(errorsSource.indexOf('data-health-timeline')).toBeGreaterThan(main);
        expect(side).toBeGreaterThan(errorsSource.indexOf('data-health-timeline'));
        expect(errorsSource.indexOf('data-health-earlier-incidents')).toBeGreaterThan(side);
        expect(errorsSource.indexOf('data-diagnostics-export')).toBeGreaterThan(side);
        // The two history lists sit side by side at 1024px and stack in the side column from 1280px.
        expect(errorsSource).toContain('<div class="grid grid-cols-1 gap-6 lg:grid-cols-2 xl:grid-cols-1">');
    });
});

