import { expect, test } from '@playwright/test';

const id = 'a'.repeat(32);
const row = { id, camera: 'patio', frigate_label: 'cat', observed_at: '2026-10-11T18:00:00Z', reviewed_at: null, status: 'pending', snapshot_url: `/api/garden/${id}/snapshot` };

test('owner can dismiss a false capture, restore it and review at narrow widths', async ({ page }) => {
    let status = 'pending';
    await page.route(url => url.pathname.startsWith('/api/garden'), async route => {
        const url = new URL(route.request().url());
        if (url.pathname.endsWith('/snapshot')) return route.fulfill({ status: 404 });
        if (route.request().method() === 'POST') {
            status = url.pathname.endsWith('/dismiss') ? 'dismissed' : 'pending';
            return route.fulfill({ json: { ...row, status } });
        }
        const items = url.searchParams.get('status') === status ? [{ ...row, status }] : [];
        return route.fulfill({ json: { items, total: items.length, limit: 8, offset: 0 } });
    });
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByText('Frigate suggested: cat')).toBeVisible();
    await expect(page.getByText('Snapshot unavailable')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeDisabled();
    await page.getByRole('button', { name: 'Dismiss capture' }).click();
    await expect(page.getByText('No captures in this view')).toBeVisible();
    await page.getByRole('button', { name: 'Dismissed', exact: true }).click();
    await page.getByRole('button', { name: 'Return to review' }).click();
    await page.getByRole('button', { name: 'Needs review', exact: true }).click();
    await expect(page.getByText('Frigate suggested: cat')).toBeVisible();
    await page.setViewportSize({ width: 320, height: 740 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('owner confirms presence only after the photo loads', async ({ page }) => {
    let confirmed = false;
    await page.route(url => url.pathname.startsWith('/api/garden'), async route => {
        if (route.request().url().endsWith('/snapshot')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#28594a"/></svg>' });
        if (route.request().method() === 'POST') {
            confirmed = true;
            return route.fulfill({ json: { ...row, status: 'confirmed' } });
        }
        const status = new URL(route.request().url()).searchParams.get('status');
        const items = (status === 'confirmed') === confirmed ? [{ ...row, status: confirmed ? 'confirmed' : 'pending' }] : [];
        return route.fulfill({ json: { items, total: items.length, limit: 8, offset: 0 } });
    });
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
    await page.getByRole('button', { name: 'Confirm animal present' }).click();
    await expect(page.getByText('No captures in this view')).toBeVisible();
    await page.getByRole('button', { name: 'Confirmed animals', exact: true }).click();
    await expect(page.getByText('Frigate suggested: cat')).toBeVisible();
    expect(confirmed).toBe(true);
});

test('history error is visible and refresh recovers', async ({ page }) => {
    let failed = true;
    await page.route('**/api/garden?**', route => route.fulfill(failed
        ? { status: 503, json: { detail: 'History temporarily unavailable' } }
        : { json: { items: [], total: 0, limit: 8, offset: 0 } }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('alert')).toContainText('History temporarily unavailable');
    failed = false;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(page.getByText('No captures in this view')).toBeVisible();
});

test('garden camera opt-in saves independently of a Nest bird role', async ({ page }) => {
    let settings: Record<string, unknown> = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
        mqtt_auth: false, cameras: ['patio'], camera_roles: { patio: 'nest' },
        garden_cameras: [], garden_labels: ['cat', 'dog'], classification_threshold: 0.7
    };
    let written: Record<string, unknown> | null = null;
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload: unknown = request.postDataJSON();
                if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error('Expected settings object');
                written = payload as Record<string, unknown>;
                settings = { ...settings, ...written };
                return route.fulfill({ json: { status: 'ok' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: { patio: {} } } });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    const nest = page.getByRole('button', { name: 'Nest', exact: true });
    await expect(nest).toHaveAttribute('aria-pressed', 'true');
    const garden = page.getByRole('button', { name: /Garden animals/ });
    await garden.click();
    await expect(garden).toHaveAttribute('aria-pressed', 'true');
    await expect(nest).toHaveAttribute('aria-pressed', 'true');
    await page.getByLabel('Frigate animal labels', { exact: true }).fill('cat, dog, squirrel');
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => written?.garden_cameras).toEqual(['patio']);
    await expect.poll(() => written?.camera_roles).toEqual({ patio: 'nest' });
    await expect.poll(() => written?.garden_labels).toEqual(['cat', 'dog', 'squirrel']);
});
