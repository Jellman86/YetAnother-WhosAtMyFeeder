import { test, expect, type Page } from '@playwright/test';

// Set EXPLORER_SHOTS to a directory to keep review screenshots outside the test output.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.EXPLORER_SHOTS;

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();

function bird(id: string, at: string) {
    return {
        frigate_event: id, display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock',
        camera_name: 'birdcam', detection_time: at, score: 0.91, has_clip: false
    };
}

function capture(id: string, at: string, status: 'pending' | 'confirmed', name?: string) {
    return {
        id: id.padEnd(32, '0'), camera: 'patio', frigate_label: 'cat', observed_at: at, status, reviewed_at: null,
        snapshot_url: `/api/garden/${id.padEnd(32, '0')}/snapshot`, source_kind: 'frigate_event', motion_source: null,
        automatic_check: null, automatic_check_overridden: false,
        identification: name ? {
            outcome: 'suggestion', reason: 'confident', review: 'accepted', automatic: false, name, rank: 'species', score: 0.93,
            country: 'GBR', variant: '4.0.3b', provider: 'cpu', devices: ['cpu'], output_index: 1, input_kind: 'whole_image',
            frame_size: [160, 120], identified_at: at
        } : null
    };
}

async function openExplorer(page: Page, query = '') {
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    const visits = [bird('morning', hoursAgo(1)), bird('night', hoursAgo(5))];
    const garden = [capture('fox', hoursAgo(3), 'confirmed', 'Red fox'), capture('cat', hoursAgo(0.5), 'pending')];
    const timelineQueries: URLSearchParams[] = [];
    const confirmed: string[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/visits') {
            return route.fulfill({ json: { total: 2, gap_seconds: 60, visits: visits.map(record => ({
                visit_id: record.frigate_event, start_time: record.detection_time, end_time: record.detection_time, capture_count: 1,
                best_score: 0.91, needs_review: false, audio_confirmed: false, representative: record, latest: record, peak_capture: null
            })) } });
        }
        if (path === '/api/garden/timeline') {
            timelineQueries.push(url.searchParams);
            return route.fulfill({ json: { items: garden, total: garden.length, limit: 200, offset: 0 } });
        }
        if (path === '/api/garden/identification') {
            return route.fulfill({ json: { country: 'GBR', catalogue_ready: true, busy: false, models: [{ variant: '4.0.3b', installed: true, size_bytes: 1 }] } });
        }
        if (path.endsWith('/confirm')) {
            const id = path.split('/')[3];
            confirmed.push(id);
            return route.fulfill({ json: { ...garden.find(item => item.id === id), status: 'confirmed' } });
        }
        if (path.endsWith('/snapshot') || path.endsWith('.jpg')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        }
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 2, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${query}`);
    await expect(page.locator('[data-explorer-visit="morning"]')).toBeVisible();
    return { errors, timelineQueries, confirmed };
}

test('Garden captures sit between the visits they fell between, marked Garden in words', async ({ page }) => {
    const { errors, timelineQueries } = await openExplorer(page, '&garden=1');
    const order = page.locator('[data-explorer-visit], [data-garden-card]');
    await expect(order).toHaveCount(4);
    const kinds = await order.evaluateAll(nodes => nodes.map(node => node.getAttribute('data-explorer-visit') ?? `garden:${node.getAttribute('data-garden-card')}`));
    expect(kinds).toEqual(['garden:pending', 'morning', 'garden:confirmed', 'night']);
    await expect(page.locator('[data-garden-card="confirmed"]')).toContainText('Red fox');
    await expect(page.locator('[data-garden-card="pending"]')).toContainText('Waiting for automatic identification');
    await expect(page.locator('[data-garden-card] [data-garden-marker]').first()).toHaveText(/Garden/);
    expect(timelineQueries[0]?.get('order')).toBe('newest');
    if (shots) await page.screenshot({ path: `${shots}/garden-explorer-cards.png`, fullPage: true });

    await page.locator('[data-explorer-view-toggle="list"]').click();
    await expect(page.locator('[data-garden-row]')).toHaveCount(2);
    if (shots) await page.screenshot({ path: `${shots}/garden-explorer-list.png`, fullPage: true });
    expect(errors).toEqual([]);
});

test('Garden on its own lists only captures, and its record confirms an animal without bird actions', async ({ page }) => {
    const { errors, confirmed } = await openExplorer(page, '&garden=1');
    const option = page.locator('[data-explorer-subjects-option="garden"]');
    // On a phone the filter rail opens from the Filters button.
    if (!(await option.isVisible())) await page.locator('[data-explorer-filter-toggle]').click();
    await option.click();
    await expect(page.locator('[data-explorer-visit]')).toHaveCount(0);
    await expect(page.locator('[data-explorer-count]')).toContainText('2 Garden captures');

    await page.getByRole('button', { name: /Open Garden capture: Possible animal/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('Waiting for automatic identification');
    await expect(dialog.getByRole('button', { name: /Reclassify|Play/i })).toHaveCount(0);
    if (shots) await page.screenshot({ path: `${shots}/garden-explorer-record.png` });
    await expect(dialog.getByRole('button', { name: 'Confirm animal manually' })).not.toBeVisible();
    await dialog.getByText('Manual override', { exact: true }).click();
    await dialog.getByRole('button', { name: 'Confirm animal manually' }).click();
    await expect(dialog).toContainText('Animal confirmed');
    expect(confirmed).toEqual(['cat'.padEnd(32, '0')]);

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(page.locator('[data-garden-card="confirmed"]')).toHaveCount(2);
    expect(errors).toEqual([]);
});

test('without the Garden beta the Explorer shows birds and asks for nothing about Garden', async ({ page }) => {
    const { timelineQueries } = await openExplorer(page);
    await expect(page.locator('[data-explorer-visitors-facet]')).toHaveCount(0);
    await expect(page.locator('[data-garden-card]')).toHaveCount(0);
    expect(timelineQueries).toEqual([]);
});
