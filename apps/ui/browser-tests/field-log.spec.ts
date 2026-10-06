import { test, expect, type Locator, type Page } from '@playwright/test';

// Set FIELD_LOG_SHOTS to a directory to keep review screenshots outside the test output.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.FIELD_LOG_SHOTS;

function capture(visit: string, index: number) {
    const at = new Date(Date.parse('2026-10-02T10:42:21Z') + index * 11_000).toISOString();
    return {
        frigate_event: index === 0 ? visit : `${visit}-${index}`, display_name: 'Turdus merula', scientific_name: 'Turdus merula',
        common_name: 'Eurasian Blackbird', camera_name: 'birdcam', detection_time: at, score: 0.78 + (index % 5) / 25, has_clip: true,
        ...(index === 4 ? { bird_summary: { counted: 3, unknown: 0, excluded: 0, species: [], hint_only: false } } : {}),
        ...(index === 6 ? { audio_confirmed: true } : {}),
        ...(index === 1 ? { display_name: 'Parus major', scientific_name: 'Parus major', common_name: 'Great Tit', score: 0.81 } : {})
    };
}

async function open(page: Page, query: string) {
    const errors: string[] = [];
    const captureReads: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        const match = url.pathname.match(/\/api\/visits\/([^/]+)\/captures$/);
        if (match) {
            captureReads.push(match[1]);
            const total = match[1] === 'blackbird' ? 13 : 3;
            return route.fulfill({ json: { captures: Array.from({ length: total }, (_, index) => capture(match[1], index)), total } });
        }
        if (url.pathname.endsWith('.jpg')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#3f6212"/></svg>' });
        }
        return route.fulfill({ status: 503, json: { detail: 'not part of this fixture' } });
    });
    await page.goto(`/browser-tests/field-log.html${query}`);
    return { errors, captureReads };
}

function row(page: Page, visitId: string): Locator {
    return page.locator(`[data-field-log-visit="${visitId}"]`);
}

test('expanded field log captures state their own species and confidence', async ({ page }) => {
    await open(page, '');
    await row(page, 'blackbird').locator('[data-field-log-time-toggle]').click();
    const capture = page.locator('[data-visit-capture="blackbird-1"]');
    await expect(capture.getByText('Great Tit', { exact: true })).toBeVisible();
    await expect(capture.getByText('Parus major', { exact: true })).toBeVisible();
    await expect(capture.locator('[data-visit-capture-score]:visible')).toHaveText('81%');
});

test('expanded capture species follow scientific name preferences', async ({ page }) => {
    await open(page, '?names=scientific');
    await row(page, 'blackbird').locator('[data-field-log-time-toggle]').click();
    const capture = page.locator('[data-visit-capture="blackbird-1"]');
    await expect(capture.getByRole('button', { name: /^Parus major/ }).locator('span').first()).toHaveText('Parus major');
    await expect(capture.getByText('Great Tit', { exact: true })).toBeVisible();
});

async function box(locator: Locator) {
    const found = await locator.boundingBox();
    if (!found) throw new Error('element has no box');
    return found;
}

async function noHorizontalOverflow(page: Page) {
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

for (const clock of ['24h', '12h']) {
    for (const width of [320, 390]) {
        test(`a server-backed visit opens from its time inside a ${width}px field log (${clock} clock)`, async ({ page }, testInfo) => {
            await page.setViewportSize({ width, height: 1200 });
            const { errors, captureReads } = await open(page, `?clock=${clock}`);
            await expect(page.locator('[data-field-log-row]')).toHaveCount(4);
            expect(captureReads).toEqual([]);

            const visitRow = row(page, 'blackbird');
            const toggle = visitRow.locator('[data-field-log-time-toggle]');
            await expect(toggle).toHaveAttribute('aria-expanded', 'false');
            await expect(toggle).toHaveAccessibleName(/13 captures$/);
            await toggle.focus();
            await page.keyboard.press('Enter');
            await expect(toggle).toHaveAttribute('aria-expanded', 'true');
            const lines = visitRow.locator('[data-visit-capture]');
            await expect(lines).toHaveCount(13);
            expect(captureReads).toEqual(['blackbird']);
            await noHorizontalOverflow(page);

            const rowBox = await box(visitRow);
            for (const line of await lines.all()) {
                const lineBox = await box(line);
                const thumb = await box(line.locator('[data-detection-preview] button'));
                const time = line.locator('time');
                const timeBox = await box(time);
                const play = await box(line.getByRole('button', { name: /Play/ }));
                const score = await box(line.locator('[data-visit-capture-score]:visible'));
                // Everything a capture needs is inside its own line and its visit's row.
                expect(lineBox.x).toBeGreaterThanOrEqual(rowBox.x - 0.5);
                expect(lineBox.x + lineBox.width).toBeLessThanOrEqual(rowBox.x + rowBox.width + 0.5);
                for (const part of [thumb, timeBox, play, score]) {
                    expect(part.x).toBeGreaterThanOrEqual(lineBox.x - 0.5);
                    expect(part.x + part.width).toBeLessThanOrEqual(lineBox.x + lineBox.width + 0.5);
                }
                // Left to right without collisions: time, thumbnail, score, clip.
                expect(timeBox.x + timeBox.width).toBeLessThanOrEqual(thumb.x + 0.5);
                expect(thumb.x + thumb.width).toBeLessThanOrEqual(score.x + 0.5);
                expect(score.x + score.width).toBeLessThanOrEqual(play.x + 0.5);
                expect(await time.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
                expect(await time.innerText()).toMatch(/\d{1,2}:\d{2}:\d{2}/);
                expect(thumb.height).toBeGreaterThanOrEqual(44);
                expect(play.height).toBeGreaterThanOrEqual(44);
                expect(play.width).toBeGreaterThanOrEqual(44);
            }

            await lines.nth(5).getByRole('button', { name: /^Open Eurasian Blackbird capture at / }).click();
            await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('blackbird-5');
            await lines.nth(2).getByRole('button', { name: /Play/ }).click();
            await expect(page.getByRole('status', { name: 'Played record' })).toHaveText('blackbird-2');
            await expect(visitRow.locator('[data-visit-capture="blackbird"]')).toContainText('Visit photo');
            await expect(visitRow.locator('[data-visit-capture="blackbird-4"]')).toContainText('3 birds');
            await page.screenshot({ path: testInfo.outputPath(`field-log-${width}-${clock}-expanded.png`), fullPage: true });
            if (shots) await page.screenshot({ path: `${shots}/field-log-after-${width}-${clock}-expanded.png`, fullPage: true });

            await toggle.click();
            await expect(lines.first()).toBeHidden();
            expect(captureReads).toEqual(['blackbird']);
            expect(errors).toEqual([]);
        });
    }
}

test('collapsed rows keep the species readable at 320px and state captures apart from birds', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 });
    const { errors } = await open(page, '');
    await noHorizontalOverflow(page);
    for (const item of await page.locator('[data-field-log-row]').all()) {
        expect((await box(item.locator('[data-field-log-name]'))).width).toBeGreaterThanOrEqual(64);
    }
    const blackbird = row(page, 'blackbird');
    await expect(blackbird.locator('[data-field-log-captures]')).toHaveText('13 captures');
    await expect(blackbird.locator('[data-field-log-birds]')).toHaveText('3 birds in one capture');
    // A single capture is already the row: no list, no count, and its record is one tap away.
    const single = row(page, 'dunnock');
    await expect(single.locator('[data-field-log-time-toggle]')).toHaveCount(0);
    await expect(single.locator('[data-field-log-captures]')).toHaveCount(0);
    await single.getByRole('button', { name: 'Open Dunnock' }).click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('dunnock');
    await expect(page.getByRole('button', { name: 'Identify' })).toHaveCount(1);
    const targets = await page.locator('[data-dashboard-field-log] button:visible').all();
    for (const target of targets) {
        const found = await box(target);
        expect(found.width).toBeGreaterThanOrEqual(44);
        expect(found.height).toBeGreaterThanOrEqual(44);
    }
    if (shots) await page.screenshot({ path: `${shots}/field-log-after-320.png`, fullPage: true });
    expect(errors).toEqual([]);
});

test('the camera is named on rows only when the log holds more than one camera', async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 900 });
    const { errors } = await open(page, '');
    await expect(page.locator('[data-field-log-row]')).toHaveCount(4);
    await expect(page.locator('[data-field-log-camera]')).toHaveCount(0);
    await expect(row(page, 'dunnock')).not.toContainText('birdcam');
    await page.goto('/browser-tests/field-log.html?cameras=two');
    await expect(page.locator('[data-field-log-camera]:visible')).toHaveCount(4);
    // A phone has no chip column: the camera is named in the row's line instead.
    await page.setViewportSize({ width: 320, height: 900 });
    await expect(page.locator('[data-field-log-camera]:visible')).toHaveCount(0);
    await expect(row(page, 'cowbird')).toContainText('nestcam');
    await expect(row(page, 'dunnock')).toContainText('birdcam');
    expect(errors).toEqual([]);
});

for (const theme of ['light', 'dark']) {
    test(`captures join their visit's thread in its columns (${theme})`, async ({ page }) => {
        await page.setViewportSize({ width: 1100, height: 1300 });
        const { errors } = await open(page, `?theme=${theme}`);
        await expect(page.locator('[data-field-log-row]')).toHaveCount(4);
        // A visit of several captures costs no extra height: its count is in words beside the name.
        const cowbird = await box(row(page, 'cowbird'));
        const dunnock = await box(row(page, 'dunnock'));
        expect(Math.abs(cowbird.height - dunnock.height)).toBeLessThanOrEqual(1);
        if (shots) await page.screenshot({ path: `${shots}/field-log-after-desktop-${theme}.png`, fullPage: true });

        const blackbird = row(page, 'blackbird');
        const toggle = blackbird.locator('[data-field-log-time-toggle]');
        await toggle.click();
        const first = blackbird.locator('[data-visit-capture]').first();
        await expect(blackbird.locator('[data-visit-capture]')).toHaveCount(13);
        // A mouse click does not leave a focus ring drawn on the time.
        expect(await toggle.evaluate(element => getComputedStyle(element).boxShadow)).toBe('none');

        const parentTime = await box(toggle);
        const childTime = await box(first.locator('time'));
        expect(Math.abs(childTime.x - (parentTime.x + 4))).toBeLessThanOrEqual(2);
        const parentPreview = await box(blackbird.locator('[data-detection-preview]').first());
        const childPreview = await box(first.locator('[data-detection-preview]'));
        expect(Math.abs(childPreview.x - parentPreview.x)).toBeLessThanOrEqual(1);
        const centre = (found: { x: number; width: number }) => found.x + found.width / 2;
        const visitDot = await blackbird.locator('[aria-hidden="true"] > .rounded-full.ring-2').first().boundingBox();
        const captureDot = await box(first.locator('[data-field-log-capture-dot]'));
        expect(Math.abs(centre(captureDot) - centre(visitDot ?? captureDot))).toBeLessThanOrEqual(1);
        // Capture and visit nodes differ in fill as well as colour.
        const hollow = blackbird.locator('[data-visit-capture]').nth(1);
        const fills = await hollow.locator('[data-field-log-capture-dot]').evaluate(node => getComputedStyle(node).backgroundColor);
        const visitFill = await blackbird.locator('[aria-hidden="true"] > .rounded-full.ring-2').first().evaluate(node => getComputedStyle(node).backgroundColor);
        expect(fills).not.toBe(visitFill);
        await expect(blackbird.locator('[data-field-log-capture-dot="shown"]')).toHaveCount(1);
        if (shots) await page.screenshot({ path: `${shots}/field-log-after-desktop-expanded-${theme}.png`, fullPage: true });
        expect(errors).toEqual([]);
    });
}

test('loading looks like the rows it stands in for, without claiming any state', async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 900 });
    const { errors } = await open(page, '');
    await expect(page.locator('[data-field-log-row]')).toHaveCount(4);
    const realHeight = (await box(row(page, 'dunnock'))).height;

    await page.goto('/browser-tests/field-log.html?state=loading');
    const placeholders = page.locator('[data-field-log-loading] [data-field-log-placeholder]');
    await expect(placeholders).toHaveCount(4);
    for (const placeholder of await placeholders.all()) {
        expect(Math.abs((await box(placeholder)).height - realHeight)).toBeLessThanOrEqual(2);
    }
    await expect(page.locator('[data-field-log-loading]')).toHaveAttribute('aria-busy', 'true');
    await expect(page.getByRole('status').filter({ hasText: 'Loading visits' })).toHaveCount(1);
    // Nothing is counted, and nothing is called healthy or empty, before it is read.
    await expect(page.locator('[data-dashboard-day-bar] dd').filter({ hasText: /^\s*0\s*$/ })).toHaveCount(0);
    await expect(page.getByText('Nothing waiting on you')).toHaveCount(0);
    await expect(page.getByText('No cameras reporting yet')).toHaveCount(0);
    await expect(page.getByText('Waiting for the first visitor')).toHaveCount(0);
    if (shots) await page.screenshot({ path: `${shots}/field-log-after-loading-desktop.png`, fullPage: true });

    await page.setViewportSize({ width: 320, height: 900 });
    await noHorizontalOverflow(page);
    if (shots) await page.screenshot({ path: `${shots}/field-log-after-loading-320.png`, fullPage: true });
    expect(errors).toEqual([]);
});

test('loading placeholders stand still under reduced motion', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const { errors } = await open(page, '?state=loading');
    const pulsing = page.locator('[data-loading-placeholder]');
    await expect(pulsing.first()).toBeVisible();
    expect(await pulsing.count()).toBeGreaterThan(10);
    for (const element of await pulsing.all()) {
        expect(await element.evaluate(node => getComputedStyle(node).animationName)).toBe('none');
    }
    expect(errors).toEqual([]);
});

test('a failed first read says so and offers a retry instead of an empty day', async ({ page }) => {
    const { errors } = await open(page, '?state=unavailable');
    await expect(page.locator('[data-field-log-unavailable]')).toContainText('Visits could not be loaded');
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect(page.getByRole('status', { name: 'Retries' })).toHaveText('1');
    await expect(page.locator('[data-dashboard-review-queue]')).toContainText('could not be checked');
    await expect(page.locator('[data-dashboard-day-bar] dd').filter({ hasText: /^\s*0\s*$/ })).toHaveCount(0);
    await expect(page.getByText('Nothing waiting on you')).toHaveCount(0);
    expect(errors).toEqual([]);
});

for (const phase of ['loading', 'unavailable'] as const) {
    test(`configured cameras are named while the day is ${phase}, with visits unknown rather than zero`, async ({ page }) => {
        const { errors } = await open(page, `?state=${phase}&cameras=configured`);
        const cameras = page.locator('[data-desk-cameras] [data-desk-camera]');
        await expect(cameras).toHaveCount(2);
        await expect(cameras.nth(0)).toContainText('birdcam');
        await expect(cameras.nth(1)).toContainText('nestcam');
        // A configured camera says nothing about how many visits it saw until the day is read.
        await expect(page.locator('[data-desk-cameras]')).not.toContainText('no visits');
        for (const camera of await cameras.all()) {
            expect(await camera.innerText()).not.toMatch(/(^|\s)0(\s|$)/);
        }
        if (phase === 'loading') {
            for (const camera of await cameras.all()) await expect(camera.locator('[data-loading-placeholder]')).toHaveCount(1);
            await expect(page.getByRole('status').filter({ hasText: 'Loading camera visits' })).toHaveCount(1);
        } else {
            await expect(page.locator('[data-desk-cameras]')).toContainText('Visit counts could not be loaded');
            await expect(cameras.nth(0).getByText('not available')).toHaveCount(1);
        }
        if (shots) await page.screenshot({ path: `${shots}/desk-cameras-${phase}.png`, fullPage: true });
        expect(errors).toEqual([]);
    });
}

test('a visit opens from its captures button, and its captures say only what is their own', async ({ page }) => {
    await open(page, '');
    const visit = row(page, 'blackbird');
    await expect(visit.locator('[data-field-log-best-capture]')).toHaveText('best capture');
    const toggle = visit.locator('[data-field-log-captures-toggle]');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(visit.locator('[data-visit-captures-caption]')).toHaveText('Captures in this visit, oldest first. Same bird unless named.');
    // The visit's own bird is not named again; a different bird in the visit is.
    const own = visit.locator('[data-visit-capture="blackbird"]');
    await expect(own.getByText('Eurasian Blackbird', { exact: true })).toHaveCount(0);
    await expect(own.locator('[data-visit-capture-open]')).toContainText('Visit photo');
    await expect(visit.locator('[data-visit-capture="blackbird-1"]').getByText('Great Tit', { exact: true })).toBeVisible();
    await toggle.click();
    await expect(visit.locator('[data-visit-capture]').first()).toBeHidden();
});
