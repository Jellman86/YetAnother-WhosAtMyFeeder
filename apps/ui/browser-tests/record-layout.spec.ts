import { expect, test, type Page } from '@playwright/test';
import { openRecordLayout } from './record-layout-fixture';

/**
 * The record's layout rules. From 1024 px a record with a reference to read stands in two columns
 * that each scroll: the photograph with the decision under it, and the reference beside them. No
 * column is left with a large empty area. A record with nothing to put in a second column is one
 * narrow column, as tall as what it holds.
 */
const WIDE = [
    { width: 1024, height: 768 }, { width: 1280, height: 800 }, { width: 1440, height: 900 },
    { width: 1920, height: 1080 }, { width: 2560, height: 1440 }
];
/** The most empty ground a column may show under its last line while the dialog is open. */
const MOST_EMPTY = 96;

interface ColumnReading { empty: number; scrolls: boolean; left: number; right: number; top: number; bottom: number }

/** How far a column's last drawn content ends above the column's own bottom edge. */
async function column(page: Page, selector: string): Promise<ColumnReading> {
    return page.locator(selector).evaluate((node) => {
        const box = node.getBoundingClientRect();
        const padding = parseFloat(getComputedStyle(node).paddingBottom);
        return {
            empty: Math.max(0, node.clientHeight - (node.scrollHeight - padding)),
            scrolls: node.scrollHeight > node.clientHeight + 1,
            left: box.left, right: box.right, top: box.top, bottom: box.bottom
        };
    });
}

async function noSidewaysScroll(page: Page): Promise<void> {
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    const wide = await page.locator('[data-detection-evidence-column], [data-detection-details-column]').evaluateAll((nodes) =>
        nodes.filter((node) => node.scrollWidth > node.clientWidth + 1).length);
    expect(wide).toBe(0);
}

for (const size of WIDE) {
    for (const theme of ['light', 'dark'] as const) {
        test(`a long record at ${size.width} × ${size.height} (${theme}) fills both columns, and the decision sits under the photograph`, async ({ page }) => {
            await openRecordLayout(page, size, { theme });
            const evidence = await column(page, '[data-detection-evidence-column]');
            const reference = await column(page, '[data-detection-details-column]');
            // Two columns side by side, the same height, ending together at the dialog's foot.
            expect(reference.left).toBeGreaterThanOrEqual(evidence.right - 1);
            expect(Math.abs(evidence.top - reference.top)).toBeLessThan(2);
            expect(Math.abs(evidence.bottom - reference.bottom)).toBeLessThan(2);
            const dialog = await page.locator('[data-detection-detail-modal] [role="document"]').first().boundingBox();
            expect(dialog && Math.abs(dialog.y + dialog.height - evidence.bottom)).toBeLessThan(3);
            // Neither column ends well above the foot of the dialog.
            expect(evidence.empty, 'empty ground under the decision').toBeLessThanOrEqual(MOST_EMPTY);
            expect(reference.empty, 'empty ground under the reference').toBeLessThanOrEqual(MOST_EMPTY);

            // The decision is in the photograph's column, under it, and named on the first screen.
            const photo = await page.locator('[data-detection-photograph]').boundingBox();
            const identity = await page.locator('[data-detection-identity]').boundingBox();
            const confirm = await page.locator('[data-detection-confirm]').boundingBox();
            expect(photo && identity && confirm).toBeTruthy();
            if (!photo || !identity || !confirm) return;
            expect(identity.y).toBeGreaterThanOrEqual(photo.y + photo.height - 1);
            expect(identity.x).toBeGreaterThanOrEqual(evidence.left - 1);
            expect(confirm.x + confirm.width).toBeLessThanOrEqual(evidence.right + 1);
            await expect(page.locator('[data-detection-identity]')).toBeInViewport({ ratio: 1 });
            // The reference is the other column: the family tree, the description and the sightings.
            for (const part of ['[data-taxonomy-lineage]', '[data-detection-reference]', '[data-detection-technical-identity]']) {
                const box = await page.locator(part).boundingBox();
                expect(box && box.x, part).toBeGreaterThanOrEqual(reference.left - 1);
            }
            await noSidewaysScroll(page);
        });
    }
}

test('the photograph is framed, not in a wide band, and a tall crop is shown whole', async ({ page }) => {
    await openRecordLayout(page, { width: 1920, height: 1080 });
    const photo = await page.locator('[data-detection-photograph]').boundingBox();
    // No taller than 4:3, and where the screen allows no flatter than 3:2: the old frame was 16:9.
    expect(photo && photo.height <= photo.width * 3 / 4 + 1).toBe(true);
    expect(photo && photo.height / photo.width).toBeGreaterThan(0.62);
    const fit = await page.locator('[data-detection-photograph] img:not([data-detection-media-ambient])').first()
        .evaluate((image) => getComputedStyle(image).objectFit);
    expect(fit).toBe('contain');
});

test('the photograph\'s frame is the same size before and after its picture arrives', async ({ page }) => {
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route((url) => /\.(?:jpg|jpeg|png|webp)$/.test(url.pathname) && url.pathname.startsWith('/api/'), async (route) => {
        await held;
        await route.fallback();
    });
    await openRecordLayout(page, { width: 1440, height: 900 }, { awaitPictures: false });
    const before = await page.locator('[data-detection-photograph]').boundingBox();
    const identityBefore = await page.locator('[data-detection-identity]').boundingBox();
    release();
    await expect(page.locator('[data-detection-media-ambient]')).toHaveCount(1);
    const after = await page.locator('[data-detection-photograph]').boundingBox();
    const identityAfter = await page.locator('[data-detection-identity]').boundingBox();
    expect(after).toEqual(before);
    expect(identityAfter?.y).toBe(identityBefore?.y);
});

for (const theme of ['light', 'dark'] as const) {
    test(`a short record at 1440 px (${theme}) is one narrow column as tall as what it holds`, async ({ page }) => {
        await openRecordLayout(page, { width: 1440, height: 900 }, { record: 'short', theme });
        const dialog = await page.locator('[data-detection-detail-modal] [role="document"]').first().boundingBox();
        expect(dialog?.width ?? 0).toBeLessThanOrEqual(700);
        // One column: the identification under the photograph, the identifiers under that.
        const photo = await page.locator('[data-detection-photograph]').boundingBox();
        const identity = await page.locator('[data-detection-identity]').boundingBox();
        expect(photo && identity && identity.y >= photo.y + photo.height - 1).toBe(true);
        expect(photo && dialog && dialog.width - photo.width).toBeLessThanOrEqual(40);
        // The dialog ends where its content ends: no empty box under the last line.
        const empty = await page.locator('[data-detection-technical-identity]').evaluate((last) => {
            const dialogBox = last.closest('[role="document"]')?.getBoundingClientRect();
            const scroller = last.closest('[data-detection-details-column]')?.parentElement;
            if (!dialogBox || !scroller) return Number.NaN;
            scroller.scrollTop = scroller.scrollHeight;
            return dialogBox.bottom - last.getBoundingClientRect().bottom;
        });
        expect(empty).toBeLessThanOrEqual(40);
        await noSidewaysScroll(page);
    });
}

test('a visitor\'s long record keeps the two columns, with no owner actions', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { guest: true });
    await expect(page.locator('[data-detection-confirm]')).toHaveCount(0);
    const evidence = await column(page, '[data-detection-evidence-column]');
    const reference = await column(page, '[data-detection-details-column]');
    expect(reference.left).toBeGreaterThanOrEqual(evidence.right - 1);
    expect(reference.empty).toBeLessThanOrEqual(MOST_EMPTY);
    await noSidewaysScroll(page);
});

test('on a phone the record is one column in reading order: photograph, decision, reference', async ({ page }) => {
    await openRecordLayout(page, { width: 390, height: 844 });
    const tops = await page.evaluate(() => ['[data-detection-photograph]', '[data-detection-identity]', '[data-detection-confirm]', '[data-detection-facts]', '[data-taxonomy-lineage]', '[data-detection-reference]', '[data-detection-technical-identity]']
        .map((selector) => document.querySelector(selector)?.getBoundingClientRect().top ?? Number.NaN));
    expect(tops.every((top) => Number.isFinite(top))).toBe(true);
    expect([...tops].sort((a, b) => a - b)).toEqual(tops);
    // Full width, with no second column and no gap between the decision and the reference.
    const facts = await page.locator('[data-detection-primary-column]').boundingBox();
    const reference = await page.locator('[data-detection-secondary-column]').boundingBox();
    expect(facts && reference && reference.y - (facts.y + facts.height)).toBeLessThanOrEqual(24);
    await noSidewaysScroll(page);
});

test('held sideways on a phone the identification is beside the photograph, on the first screen', async ({ page }) => {
    await openRecordLayout(page, { width: 844, height: 390 });
    const photo = await page.locator('[data-detection-photograph]').boundingBox();
    const identity = await page.locator('[data-detection-identity]').boundingBox();
    expect(photo && identity && identity.x >= photo.x + photo.width - 1).toBe(true);
    await expect(page.locator('[data-detection-identity]')).toBeInViewport();
    await noSidewaysScroll(page);
});

for (const theme of ['dark', 'light'] as const) {
    test(`the whole scene and the photo options are drawn cleanly (${theme})`, async ({ page }) => {
        await openRecordLayout(page, { width: 1440, height: 900 }, { theme, frames: true });
        const strip = page.locator('[data-frame-strip-scroller]');
        await expect(strip.locator('button[aria-pressed="true"]')).toHaveCount(1);

        // The chosen thumbnail is marked by a check on its corner; no word is squeezed into it.
        const chosen = strip.locator('button[aria-pressed="true"]');
        await expect(chosen.locator('[data-frame-strip-chosen]')).toBeVisible();
        expect((await chosen.innerText()).trim()).toBe('');
        const thumb = await chosen.boundingBox();
        const mark = await chosen.locator('[data-frame-strip-chosen]').boundingBox();
        expect(thumb && mark && mark.width <= 20 && mark.x >= thumb.x && mark.x + mark.width <= thumb.x + thumb.width + 4).toBe(true);

        // The media object holds the photograph and its frames and ends there: nothing else is on
        // its dark ground, and no dark band runs on beneath the frames.
        const media = await page.locator('[data-detection-media]').boundingBox();
        const frames = await page.locator('[data-frame-strip]').boundingBox();
        expect(media && frames && media.y + media.height - (frames.y + frames.height)).toBeLessThanOrEqual(8);
        await expect(page.locator('[data-detection-media] [data-bird-scan-control]')).toHaveCount(0);

        // The finder is a row of the decision panel, inside its edges.
        const scan = await page.locator('[data-bird-scan-control]').boundingBox();
        const panel = await page.locator('[data-detection-decision-panel]').boundingBox();
        expect(scan && panel && scan.x > panel.x && scan.x + scan.width < panel.x + panel.width).toBe(true);
        const identity = await page.locator('[data-detection-identity]').boundingBox();
        expect(scan && identity && Math.abs(scan.x - identity.x)).toBeLessThan(2);

        // Pinned, the whole scene names the crop from outside its outline.
        await page.locator('[data-detection-whole-scene-peek]').click();
        const outline = page.locator('[data-detection-whole-scene-outline]');
        await expect(outline).toBeVisible();
        const box = await outline.boundingBox();
        const label = await page.locator('[data-detection-whole-scene-label]').boundingBox();
        expect(box && label).toBeTruthy();
        if (!box || !label) return;
        const clear = label.y + label.height <= box.y + 1 || label.y >= box.y + box.height - 1;
        expect(clear, 'the label covers the crop it names').toBe(true);
        const photo = await page.locator('[data-detection-photograph]').boundingBox();
        expect(photo && label.x >= photo.x && label.x + label.width <= photo.x + photo.width).toBe(true);

        // One action under the photograph, the kit's primary button on one line; the way back is on
        // the photograph, in its row of controls, level with the star.
        const use = page.locator('[data-detection-whole-scene-actions] button');
        await expect(use).toHaveCount(1);
        await expect(use).toHaveClass(/\bbtn-primary\b/);
        expect((await use.boundingBox())?.height).toBeLessThanOrEqual(48);
        const back = page.getByRole('button', { name: 'Back to the crop' }).and(page.locator('[data-detection-whole-scene-back]'));
        await expect(back).toHaveClass(/\bphoto-chip\b/);
        const backBox = await back.boundingBox();
        const star = await page.locator('[data-detection-media-actions] button').first().boundingBox();
        expect(backBox && star && photo && Math.abs(backBox.y - star.y) < 2 && backBox.y + backBox.height <= photo.y + photo.height).toBe(true);
        await back.click();
        await expect(outline).toHaveCount(0);
        await noSidewaysScroll(page);
    });
}

test('a crop at the top of the frame is named from under its outline', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { frames: true, cropAtTop: true });
    await page.locator('[data-detection-whole-scene-peek]').click();
    const box = await page.locator('[data-detection-whole-scene-outline]').boundingBox();
    const label = await page.locator('[data-detection-whole-scene-label]').boundingBox();
    const photo = await page.locator('[data-detection-photograph]').boundingBox();
    expect(box && label && photo).toBeTruthy();
    if (!box || !label || !photo) return;
    expect(label.y).toBeGreaterThanOrEqual(box.y + box.height - 1);
    expect(label.y).toBeGreaterThanOrEqual(photo.y);
});

test('the dialog keeps its width while the lineage is read, and when the catalogue does not hold the species', async ({ page }) => {
    // The shape comes from what the record holds when it opens. A read that answers late, answers
    // with nothing or fails moves nothing: the reference column still has the description to show.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await openRecordLayout(page, { width: 1440, height: 900 }, { lineage: false, lineageHeld: held });
    const dialog = page.locator('[data-detection-detail-modal] [role="document"]').first();
    const photograph = page.locator('[data-detection-photograph]');
    const before = { dialog: await dialog.boundingBox(), photograph: await photograph.boundingBox() };
    expect(before.dialog?.width ?? 0).toBeGreaterThan(1100);
    const answered = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/taxonomy/lineage');
    release();
    await answered;
    await page.waitForTimeout(300);
    await expect(page.locator('[data-taxonomy-lineage]')).toHaveCount(0);
    expect(await dialog.boundingBox()).toEqual(before.dialog);
    expect(await photograph.boundingBox()).toEqual(before.photograph);
    // The reference keeps its column, beside the decision.
    const reference = await page.locator('[data-detection-reference]').boundingBox();
    const facts = await page.locator('[data-detection-facts]').boundingBox();
    expect(reference && facts && reference.x >= facts.x + facts.width - 1).toBe(true);
});

test('a lineage read that fails leaves the record in its two columns', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { lineage: 'fails' });
    await page.waitForTimeout(300);
    const dialog = await page.locator('[data-detection-detail-modal] [role="document"]').first().boundingBox();
    expect(dialog?.width ?? 0).toBeGreaterThan(1100);
});

/**
 * The decision is on the first screen. Opened and not scrolled, the name, the score and both
 * identification buttons are whole inside the dialog, on laptops as well as on large screens, with
 * or without a reference column, and with the whole scene pinned and its own action showing.
 */
const FIRST_SCREEN = [{ width: 1280, height: 800 }, { width: 1366, height: 768 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }];
const STATES = [
    { name: 'a long record', options: {}, pin: false },
    { name: 'a long record with kept frames', options: { frames: true }, pin: false },
    { name: 'a long record with the whole scene pinned', options: { frames: true }, pin: true },
    { name: 'a short record', options: { record: 'short' as const }, pin: false }
];
for (const size of FIRST_SCREEN) {
    for (const state of STATES) {
        test(`${state.name} at ${size.width} × ${size.height} shows the name, the score and both buttons without scrolling`, async ({ page }) => {
            await openRecordLayout(page, size, state.options);
            if (state.pin) {
                await page.locator('[data-detection-whole-scene-peek]').click();
                await expect(page.locator('[data-detection-whole-scene-actions] button')).toBeVisible();
                await expect(page.locator('[data-detection-whole-scene-outline]')).toBeVisible();
            }
            // What can be seen without scrolling: the photograph's column where it scrolls by itself,
            // else the dialog's one scrolling body.
            const seen = await page.locator('[data-detection-evidence-column]').evaluate((column) => {
                const scroller = getComputedStyle(column).overflowY === 'auto' ? column : column.parentElement as HTMLElement;
                const box = scroller.getBoundingClientRect();
                return { top: box.top, bottom: Math.min(box.bottom, innerHeight), scrolled: scroller.scrollTop };
            });
            expect(seen.scrolled).toBe(0);
            for (const part of ['[data-detection-identity]', '[data-record-score-bar]', '[data-detection-confirm]', '[data-detection-pick]']) {
                const box = await page.locator(part).boundingBox();
                expect(box, part).toBeTruthy();
                if (!box) continue;
                expect(box.y, `${part} starts on the first screen`).toBeGreaterThanOrEqual(seen.top);
                expect(box.y + box.height, `${part} ends on the first screen`).toBeLessThanOrEqual(seen.bottom);
            }
            // The photograph is still a picture, not a sliver, and the outline still sits on its crop.
            const photo = await page.locator('[data-detection-photograph]').boundingBox();
            expect(photo?.height ?? 0).toBeGreaterThanOrEqual(150);
            if (state.pin && photo) {
                // Pinning made room under the photograph for the scene's action. The crop is the
                // middle of the scene, so its outline settles on the middle of the smaller frame.
                const offCentre = async (): Promise<number> => {
                    const outline = await page.locator('[data-detection-whole-scene-outline]').boundingBox();
                    if (!outline) return Number.POSITIVE_INFINITY;
                    return Math.max(Math.abs(outline.x + outline.width / 2 - (photo.x + photo.width / 2)), Math.abs(outline.y + outline.height / 2 - (photo.y + photo.height / 2)));
                };
                await expect.poll(offCentre).toBeLessThan(12);
            }
        });
    }
}

test('a short record\'s photograph is no larger than a long record\'s', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 });
    const long = await page.locator('[data-detection-photograph]').boundingBox();
    await openRecordLayout(page, { width: 1440, height: 900 }, { record: 'short' });
    const short = await page.locator('[data-detection-photograph]').boundingBox();
    expect(long && short && short.height <= long.height + 1 && short.width <= long.width * 1.2).toBe(true);
});

test('a visit with no kept frames says so in one compact row under the photograph', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 });
    const footer = await page.locator('[data-detection-media-footer]').boundingBox();
    expect(footer?.height ?? 0).toBeLessThanOrEqual(72);
    const words = await page.locator('[data-frame-strip-status]').boundingBox();
    const again = await page.locator('[data-frame-strip] button').last().boundingBox();
    expect(words && again && words.y < again.y + again.height && again.y < words.y + words.height).toBe(true);
});

test('a crop the full height of the frame keeps its name on the picture, clear of the buttons', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { frames: true, cropAtTop: true, cropFullHeight: true });
    await page.locator('[data-detection-whole-scene-peek]').click();
    await expect(page.locator('[data-detection-whole-scene-outline]')).toBeVisible();
    const label = await page.locator('[data-detection-whole-scene-label]').boundingBox();
    const photo = await page.locator('[data-detection-photograph]').boundingBox();
    const controls = await page.locator('[data-detection-media-actions]').boundingBox();
    expect(label && photo && controls).toBeTruthy();
    if (!label || !photo || !controls) return;
    expect(label.y >= photo.y && label.y + label.height <= photo.y + photo.height).toBe(true);
    expect(label.y + label.height).toBeLessThanOrEqual(controls.y);
});
