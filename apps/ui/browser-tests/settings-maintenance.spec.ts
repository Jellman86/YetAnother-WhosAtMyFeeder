import { test, expect, type Page } from '@playwright/test';
import { openMoreOptions, openSettings } from './settings-page-mock';

// Maintenance says, for every job, when it last ran and what it found, and why a button that
// cannot run yet is disabled. The last runs come from the server's durable record.
test.use({ viewport: { width: 1440, height: 900 } });

const lastRuns = {
    runs: [
        { kind: 'taxonomy', status: 'completed', finished_at: '2026-11-15T09:30:00Z', checked: 120, changed: 7 },
        { kind: 'detections', status: 'failed', finished_at: '2026-11-14T22:00:00Z', checked: null, changed: null }
    ]
};

async function openMaintenance(
    page: Page,
    preview: { summary: Record<string, number>; candidates: unknown[] } | null = null,
    runs: { runs: unknown[] } = lastRuns
): Promise<void> {
    await openSettings(page, {}, {
        respond: (path) => {
            if (path === '/api/maintenance/last-runs') return { json: runs };
            if (path === '/api/maintenance/timezone-repair/preview' && preview) return { json: preview };
            return undefined;
        }
    });
    await page.getByRole('link', { name: 'Storage & upkeep', exact: true }).click();
    // The jobs are under Storage & upkeep's More options.
    await openMoreOptions(page);
    await expect(page.getByRole('heading', { name: 'Timezone repair', exact: true })).toBeVisible();
}

test('each job says when it last ran and what it found, or that no run is recorded', async ({ page }) => {
    await openMaintenance(page);
    await expect(page.getByText(/Last run .*: 7 of 120 names repaired\./)).toBeVisible();
    await expect(page.locator('[data-maintenance-last-run="detections"]')).toHaveText(/^The last run, .*, did not finish\.$/);
    await expect(page.locator('[data-maintenance-last-run="timezone_scan"]')).toHaveText('No run recorded yet.');
});

test('Apply timezone repair says why it cannot run before a scan, and after a scan that found nothing', async ({ page }) => {
    await openMaintenance(page, {
        summary: { scanned_count: 40, repair_candidate_count: 0, ok_count: 40, missing_frigate_event_count: 0, unsupported_delta_count: 0, lookup_error_count: 0 },
        candidates: []
    });
    const apply = page.getByRole('button', { name: 'Apply timezone repair', exact: true });
    await expect(apply).toBeDisabled();
    await expect(apply).toHaveAccessibleDescription(/^Scan first\./);
    await page.getByRole('button', { name: 'Scan for timezone issues', exact: true }).click();
    await expect(apply).toHaveAccessibleDescription('The scan found nothing to repair.');
    await expect(apply).toBeDisabled();
});

test('after a recorded scan that found nothing, the reason says so instead of asking for another scan', async ({ page }) => {
    await openMaintenance(page, null, { runs: [{ kind: 'timezone_scan', status: 'completed', finished_at: '2026-11-13T20:21:00Z', checked: 500, changed: 0 }] });
    const apply = page.getByRole('button', { name: 'Apply timezone repair', exact: true });
    await expect(apply).toBeDisabled();
    await expect(apply).toHaveAccessibleDescription('Nothing to repair: the last scan found no detections that need it.');
    await expect(page.locator('[data-maintenance-last-run="timezone_scan"]')).toContainText('none of 500 detections need a repair');
});

test('a scan whose Frigate lookups failed is never shown as an all-clear', async ({ page }) => {
    await openMaintenance(page, null, { runs: [{ kind: 'timezone_scan', status: 'completed', finished_at: '2026-11-13T20:21:00Z', checked: 40, changed: 0, unchecked: 40 }] });
    await expect(page.locator('[data-maintenance-last-run="timezone_scan"]')).toHaveText(/could not check 40 of 40 detections \(Frigate did not answer\)\. Scan again\.$/);
    await expect(page.getByRole('button', { name: 'Apply timezone repair', exact: true }))
        .toHaveAccessibleDescription('The last scan could not check 40 detections (Frigate did not answer). Scan again.');
});

test('a backfill that is still running says so and when it started', async ({ page }) => {
    await openMaintenance(page, null, { runs: [{ kind: 'detections', status: 'running', started_at: '2026-11-16T01:00:00Z', finished_at: null, checked: 10, changed: 0, unchecked: 0 }] });
    await expect(page.locator('[data-maintenance-last-run="detections"]')).toHaveText(/^Running now, started .+\.$/);
});

test('the job sections are plain headings, with no collapsed sections to open', async ({ page }) => {
    await openMaintenance(page);
    for (const name of ['Jobs at once', 'Delete data']) {
        await expect(page.getByRole('button', { name, exact: true })).toHaveCount(0);
    }
});
