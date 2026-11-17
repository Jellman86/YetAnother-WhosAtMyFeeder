import { expect, test, type Page } from '@playwright/test';
import { openMoreOptions, openSettings, saveButton } from './settings-page-mock';

// A Settings tab reads its own helper data (Frigate's recording support, the BirdNET-Go sources,
// the classifier) when it opens. A save reads again what the save may have changed; leaving the
// tab or the page cancels a read still under way; the page's refresh reads each thing once.

const tabLink = (page: Page, name: string) => page.locator('[data-settings-navigation]').getByRole('link', { name, exact: true });

interface StalledRead {
    path: string;
    aborted: boolean;
    reason: string;
}

/** The page's fetch answers `path` with headers, then a body that never ends; each read records its abort. */
async function stallBodies(page: Page, path: string): Promise<void> {
    await page.addInitScript((stalledPath) => {
        const reads: StalledRead[] = [];
        (window as unknown as { __stalledReads: StalledRead[] }).__stalledReads = reads;
        const realFetch = window.fetch.bind(window);
        window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
            const url = new URL(input instanceof Request ? input.url : String(input), location.href);
            if (url.pathname !== stalledPath) return realFetch(input, init);
            const read: StalledRead = { path: url.pathname, aborted: false, reason: '' };
            reads.push(read);
            const signal = init?.signal ?? undefined;
            const body = new ReadableStream<Uint8Array>({
                start(controller) {
                    controller.enqueue(new TextEncoder().encode('{"partial": '));
                    signal?.addEventListener('abort', () => {
                        read.aborted = true;
                        read.reason = String((signal.reason as { message?: unknown } | undefined)?.message ?? signal.reason);
                        controller.error(new DOMException('The operation was aborted.', 'AbortError'));
                    });
                }
            });
            return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } }));
        };
    }, path);
}

const stalledReads = (page: Page): Promise<StalledRead[]> =>
    page.evaluate(() => (window as unknown as { __stalledReads: StalledRead[] }).__stalledReads);

async function expectCancelledOnLeaving(page: Page, leave: () => Promise<void>): Promise<void> {
    await expect.poll(async () => (await stalledReads(page)).length, { timeout: 15_000 }).toBeGreaterThan(0);
    expect((await stalledReads(page)).every((read) => !read.aborted)).toBe(true);
    await leave();
    // Well inside the reads' own deadlines, so only the cancel can have ended them.
    await expect.poll(async () => (await stalledReads(page)).every((read) => read.aborted), { timeout: 3_000 }).toBe(true);
    for (const read of await stalledReads(page)) expect(read.reason).not.toMatch(/timed out/i);
}

test('saving a new Frigate address reads its recording support again', async ({ page }) => {
    let server = 'http://frigate:5000';
    let capabilityReads = 0;
    await openSettings(page, { recording_clip_enabled: true }, {
        respond: (path) => {
            if (!path.endsWith('/frigate/recording-clip-capability')) return undefined;
            capabilityReads += 1;
            return server === 'http://frigate:5000'
                ? { json: { supported: true, recordings_enabled: true, retention_days: 7, eligible_cameras: ['patio'], ineligible_cameras: {} } }
                : { json: { supported: false, reason: 'recordings_disabled', recordings_enabled: false, retention_days: null, eligible_cameras: [], ineligible_cameras: {} } };
        },
        refuseWrite: (payload) => {
            if (typeof payload.frigate_url === 'string') server = payload.frigate_url;
            return undefined;
        }
    });
    await openMoreOptions(page);
    await page.getByText('Show advanced options').first().click();
    await expect(page.getByText('Continuous coverage is ready for the selected camera.')).toBeVisible();
    const before = capabilityReads;
    await page.locator('#frigate-url').fill('http://frigate-new:5000');
    await saveButton(page).click();
    await expect(page.locator('[data-toast]').filter({ hasText: 'Settings saved' })).toHaveCount(1);
    await expect.poll(() => capabilityReads).toBe(before + 1);
    await expect(page.getByText('Continuous coverage is ready for the selected camera.')).toHaveCount(0);
});

test('a recording-support answer from before a save never replaces the answer after it', async ({ page }) => {
    let server = 'http://frigate:5000';
    let newServerReads = 0;
    const ready = { json: { supported: true, recordings_enabled: true, retention_days: 7, eligible_cameras: ['patio'], ineligible_cameras: {} } };
    let releaseOld: () => void = () => undefined;
    // The old Frigate answers only after the save, as a slow one would.
    const oldAnswer = new Promise<typeof ready>((resolve) => { releaseOld = () => resolve(ready); });
    await openSettings(page, { recording_clip_enabled: true }, {
        respond: (path) => {
            if (!path.endsWith('/frigate/recording-clip-capability')) return undefined;
            if (server === 'http://frigate:5000') return oldAnswer;
            newServerReads += 1;
            return { json: { supported: false, reason: 'recordings_disabled', recordings_enabled: false, retention_days: null, eligible_cameras: [], ineligible_cameras: {} } };
        },
        refuseWrite: (payload) => {
            if (typeof payload.frigate_url === 'string') server = payload.frigate_url;
            return undefined;
        }
    });
    await openMoreOptions(page);
    await page.getByText('Show advanced options').first().click();
    await expect(page.getByText('Checking saved Frigate recording support…')).toBeVisible();
    await page.locator('#frigate-url').fill('http://frigate-new:5000');
    await saveButton(page).click();
    await expect(page.locator('[data-toast]').filter({ hasText: 'Settings saved' })).toHaveCount(1);
    await expect.poll(() => newServerReads).toBe(1);
    await expect(page.getByText('Checking saved Frigate recording support…')).toHaveCount(0);
    releaseOld();
    // Long enough for the old answer to land and be drawn, were it accepted.
    await page.waitForTimeout(1_000);
    await expect(page.getByText('Continuous coverage is ready for the selected camera.')).toHaveCount(0);
});

test("leaving Connection cancels its recording-support read while the body is still arriving", async ({ page }) => {
    await stallBodies(page, '/api/frigate/recording-clip-capability');
    await openSettings(page, { recording_clip_enabled: true });
    await expectCancelledOnLeaving(page, () => tabLink(page, 'Display').click());
});

test('leaving Cameras & connection cancels its BirdNET-Go sources read while the body is still arriving', async ({ page }) => {
    await stallBodies(page, '/api/audio/sources');
    await openSettings(page, {}, { route: '/settings/cameras' });
    await expectCancelledOnLeaving(page, () => tabLink(page, 'Display').click());
});

test('leaving Settings altogether cancels the open tab\'s helper read', async ({ page }) => {
    await stallBodies(page, '/api/audio/sources');
    await openSettings(page, {}, { route: '/settings/cameras' });
    await expectCancelledOnLeaving(page, () => page.getByRole('button', { name: 'Leave Settings', exact: true }).click());
});

test("the page's refresh on Data reads the classifier once", async ({ page }) => {
    let classifierReads = 0;
    await openSettings(page, {}, {
        route: '/settings/data',
        respond: (path) => {
            if (path === '/api/classifier/status') classifierReads += 1;
            return undefined;
        }
    });
    await expect.poll(() => classifierReads).toBe(1);
    await page.evaluate(() => window.dispatchEvent(new Event('test-page-refresh')));
    await expect.poll(() => classifierReads).toBe(2);
    // Settle: a second read for the same refresh would arrive straight after the first.
    await page.waitForTimeout(1_000);
    expect(classifierReads).toBe(2);
});
