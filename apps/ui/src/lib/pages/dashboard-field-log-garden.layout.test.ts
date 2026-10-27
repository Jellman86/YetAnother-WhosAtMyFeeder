import { describe, expect, it } from 'vitest';

import dashboardSource from './Dashboard.svelte?raw';
import fieldLogSource from '../components/FieldLog.svelte?raw';
import gardenRowSource from '../components/FieldLogGardenRow.svelte?raw';

describe('Garden visits on the dashboard field log', () => {
    it('reads Garden visits only for an owner with Garden turned on, in the same window as the birds', () => {
        expect(dashboardSource).toContain(
            "const gardenAvailable = $derived(authStore.hasOwnerAccess && settingsStore.settings?.beta_garden_animals === true);"
        );
        expect(dashboardSource).toContain('const gardenRead = gardenAvailable');
        expect(dashboardSource).toContain("fetchGardenVisits({ start: window.startTime, end: window.endTime, order: 'newest', limit: VISIT_ROW_LIMIT }, signal)");
    });

    it('threads animals between bird visits without adding them to any bird total', () => {
        expect(dashboardSource).toContain('mergeFieldLog(allVisits, gardenVisits, VISIT_ROW_LIMIT)');
        expect(dashboardSource).toContain('rows={fieldLogRows}');
        // The day bar and context cards still count bird visits only.
        expect(dashboardSource).toContain('let last24hCount = $derived(summary?.visit_count ?? allVisits.length);');
        expect(dashboardSource).toContain('visits={allVisits}');
    });

    it('states a Garden read failure beside the birds instead of implying a quiet garden', () => {
        expect(dashboardSource).toContain('{gardenUnavailable}');
        expect(fieldLogSource).toContain('{#if gardenUnavailable && !loading}');
        expect(fieldLogSource).toContain('dashboard.field_log.garden_unavailable');
    });

    it('marks every Garden row in words and says what still needs a person', () => {
        expect(fieldLogSource).toContain("{:else if row.kind === 'garden'}");
        expect(gardenRowSource).toContain('<GardenExplorerMarker compact />');
        expect(gardenRowSource).toContain('data-field-log-garden-state');
        expect(gardenRowSource).toContain("dashboard.field_log.review");
        expect(gardenRowSource).toContain('aria-label={openLabel}');
    });

    it('opens the Garden record on the dashboard and refreshes the log after a review', () => {
        expect(dashboardSource).toContain('ongardenopen={(visit) => gardenViewer.open(visit)}');
        expect(dashboardSource).toContain('<GardenCaptureModal');
        expect(dashboardSource).toContain('onchanged={(next) => { gardenViewer.changed(next); void loadSummary(); }}');
        expect(dashboardSource).toContain('const version = gardenHistory.version;');
    });
});
