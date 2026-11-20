import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The shell on a desktop that is wide but not tall, and on a very wide one. Every place in the
 * navigation stays fully in view: on a short window it is System status that gives way and scrolls
 * inside itself. Past a 1920 px desktop the page is centred with growing gutters rather than
 * stretched across the screen.
 */
const READY = { timeout: 15_000 };

async function open(page: Page, size: { width: number; height: number }, options: { german?: boolean; readingFont?: boolean } = {}): Promise<void> {
    await page.setViewportSize(size);
    if (options.german) await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await replayFeeder(page, 'light', {}, (json, url) =>
        options.readingFont && url.pathname === '/api/settings' ? { ...(json as Record<string, unknown>), accessibility_dyslexia_font: true } : json
    );
    await page.goto('/about');
    await expect(page.locator('#app-sidebar nav')).toBeVisible(READY);
    await settled(page);
}

async function hiddenPlaces(page: Page): Promise<string[]> {
    return page.locator('#app-sidebar nav').evaluate((nav) => {
        const frame = nav.getBoundingClientRect();
        return [...nav.querySelectorAll('button')]
            .filter((item) => {
                const box = item.getBoundingClientRect();
                return box.top < frame.top - 1 || box.bottom > frame.bottom + 1 || box.bottom > innerHeight + 1;
            })
            .map((item) => item.getAttribute('aria-label') ?? '');
    });
}

for (const size of [{ width: 1920, height: 900 }, { width: 1440, height: 800 }, { width: 1280, height: 720 }, { width: 1024, height: 768 }]) {
    for (const options of [{}, { german: true }, { german: true, readingFont: true }]) {
        const name = [options.german ? 'German' : 'English', options.readingFont ? 'the reading font' : ''].filter(Boolean).join(' with ');
        test(`at ${size.width} × ${size.height} in ${name} every place in the navigation is in view`, async ({ page }) => {
            await open(page, size, options);
            expect(await page.locator('#app-sidebar nav button').count()).toBeGreaterThanOrEqual(8);
            expect(await hiddenPlaces(page)).toEqual([]);
            const status = page.locator('[data-sidebar-status]');
            const link = status.locator('[data-sidebar-status-link]');
            const readings = page.locator('[data-sidebar-status-readings]');
            if (!options.readingFont) {
                await expect(status).toBeVisible();
                // The issues link is whole and in view without scrolling anything, under the status heading
                // and its first reading: only the rest of the readings give way.
                await expect(link).toBeInViewport({ ratio: 1 });
                const card = await page.locator('[data-sidebar-status-card]').boundingBox();
                const linkBox = await link.boundingBox();
                expect(card && linkBox && linkBox.y + linkBox.height <= card.y + card.height + 1, 'the issues link is inside its card').toBe(true);
                expect((await readings.boundingBox())?.height ?? 0).toBeGreaterThan(30);
                expect(await page.locator('[data-sidebar-scroll]').evaluate((node) => node.scrollHeight - node.clientHeight)).toBeLessThanOrEqual(1);
            } else {
                // With the much wider reading font the card's floor (its heading, first reading and a Health
                // link that wraps onto three lines) is taller than the room under the places at these sizes,
                // so the card gives way entirely rather than being squashed with no reading in it. Where it
                // does show, it is whole, and its link is reached by scrolling the column if need be.
                await expect.poll(() => cardFaults(page), READY).toEqual([]);
                if (await status.isVisible()) {
                    // Scrolled to the middle of the column, as a reader would bring it into view, not flush
                    // with its edge where a fraction of a pixel can stay under the clip.
                    await link.evaluate((node) => node.scrollIntoView({ block: 'center' }));
                    await expect(link).toBeInViewport({ ratio: 1 });
                }
            }
        });
    }
}

// A 13-inch MacBook Air's whole screen and a 1080p monitor: the status readings fit their card, so they
// do not scroll. Their CPU and NPU line once overhung its 16px line by about 2px, which made the readings
// scroll by that much at every size.
for (const size of [{ width: 1470, height: 956 }, { width: 1920, height: 1080 }]) {
    for (const options of [{}, { german: true }]) {
        test(`at ${size.width} × ${size.height} in ${options.german ? 'German' : 'English'} the status readings fit, with nothing to scroll`, async ({ page }) => {
            await open(page, size, options);
            const readings = page.locator('[data-sidebar-status-readings]');
            await expect(readings.locator('[data-telemetry-readout]')).toBeVisible(READY);
            const fit = await readings.evaluate((node) => ({
                overflow: node.scrollHeight - node.clientHeight,
                // Inline text's box is as tall as its font, whatever the line: the readings are boxes on the
                // line, so no font can make them overhang it. (The fixture's fallback font happens to fit
                // either way; the app's own faces did not.)
                inlineReadings: [...node.querySelectorAll('[data-telemetry-readout] > *')].filter((child) => getComputedStyle(child).display === 'inline').length
            }));
            expect(fit.overflow).toBeLessThanOrEqual(0);
            expect(fit.inlineReadings).toBe(0);
        });
    }
}

// A MacBook window: Safari on a 13-inch Air's 1470 × 956 screen leaves about 820 px under its menu bar
// and toolbar, and a window with the Dock in view is shorter still. The readings scroll inside their card
// there, and at rest they show whole lines only: every line is wholly in view or wholly below it, never
// cut through its letters. Each width is checked across a run of heights, so wherever the card's room
// happens to end, no line is left in part.
async function linesCutAtTheFoot(page: Page): Promise<string[]> {
    return page.locator('[data-sidebar-status-readings]').evaluate((node) => {
        const box = node.getBoundingClientRect();
        // A line is a row of words: a list that holds rows runs past the fold by design.
        return [...node.querySelectorAll<HTMLElement>(':scope > *, li')]
            .filter((line) => !line.querySelector('li'))
            .map((line) => line.getBoundingClientRect())
            .filter((line) => line.height > 0 && line.top < box.bottom - 1 && line.bottom > box.bottom + 1)
            .map((line) => `${Math.round(line.top - box.top)}–${Math.round(line.bottom - box.top)} in ${Math.round(box.height)} at ${innerHeight}`);
    });
}

for (const size of [{ width: 1470, height: 820 }, { width: 1440, height: 760 }]) {
    for (const options of [{}, { german: true }]) {
        test(`at ${size.width} × ${size.height} and around it, in ${options.german ? 'German' : 'English'}, the status readings show only whole lines`, async ({ page }) => {
            await open(page, size, options);
            await expect(page.locator('[data-sidebar-status-readings] [data-status-row]').first()).toBeVisible(READY);
            for (let height = size.height - 40; height <= size.height + 40; height += 4) {
                await page.setViewportSize({ width: size.width, height });
                await expect.poll(() => linesCutAtTheFoot(page), { timeout: 3_000 }).toEqual([]);
            }
        });
    }
}

// The readings are a tab stop, and their focus ring is drawn outside their box. Whether or not they scroll
// (a short window, and one where they fit), the ring is drawn: the pixels just below the box change when
// they take keyboard focus. A mask on the readings once clipped the ring away entirely.
for (const size of [{ width: 1440, height: 760 }, { width: 1470, height: 956 }]) {
    test(`at ${size.width} × ${size.height} the status readings show their focus ring`, async ({ page }) => {
        await open(page, size);
        const readings = page.locator('[data-sidebar-status-readings]');
        // The telemetry row is always drawn; its reading may not be, since the graph samples only while
        // its row is on screen, and at 1440 × 760 the row sits below the readings' whole lines.
        await expect(readings.locator('[data-system-telemetry]')).toBeAttached(READY);
        const box = await readings.boundingBox();
        expect(box).not.toBeNull();
        if (!box) return;
        const band = { x: Math.floor(box.x), y: Math.ceil(box.y + box.height) + 1, width: Math.floor(box.width), height: 3 };
        const resting = await page.screenshot({ clip: band, animations: 'allow' });
        await page.keyboard.press('Tab');
        await readings.focus();
        await expect(readings).toBeFocused();
        expect(await readings.evaluate((node) => node.matches(':focus-visible'))).toBe(true);
        const focused = await page.screenshot({ clip: band, animations: 'allow' });
        expect(focused.equals(resting), 'the focus ring is drawn below the readings').toBe(false);
    });
}

test('at 2560 px the page and its footer are centred with gutters, and at 1920 px they use the width', async ({ page }) => {
    await open(page, { width: 2560, height: 1440 });
    const sidebar = await page.locator('#app-sidebar').boundingBox();
    const main = await page.locator('#main-content').boundingBox();
    const footer = await page.locator('footer > div').first().boundingBox();
    expect(sidebar).not.toBeNull();
    expect(main).not.toBeNull();
    expect(footer).not.toBeNull();
    if (!sidebar || !main || !footer) return;
    const left = main.x - (sidebar.x + sidebar.width);
    const right = 2560 - (main.x + main.width);
    expect(left).toBeGreaterThan(80);
    expect(Math.abs(left - right)).toBeLessThan(2);
    expect(Math.abs(footer.x - main.x)).toBeLessThan(2);

    await page.setViewportSize({ width: 1920, height: 1080 });
    const wide = await page.locator('#main-content').boundingBox();
    const rail = await page.locator('#app-sidebar').boundingBox();
    expect(wide && rail && wide.x + wide.width).toBeGreaterThan(1920 - 2);
    expect(wide && rail && wide.x - (rail.x + rail.width)).toBeLessThan(2);
});

test('with the sidebar collapsed the page is still centred past 1920 px, and fills the window at 1920 px', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
    await open(page, { width: 2560, height: 1440 });
    const rail = await page.locator('#app-sidebar').boundingBox();
    const main = await page.locator('#main-content').boundingBox();
    expect(rail).not.toBeNull();
    expect(main).not.toBeNull();
    if (!rail || !main) return;
    expect(rail.width).toBeLessThan(120);
    const left = main.x - (rail.x + rail.width);
    const right = 2560 - (main.x + main.width);
    expect(left).toBeGreaterThan(80);
    expect(Math.abs(left - right)).toBeLessThan(2);

    await page.setViewportSize({ width: 1920, height: 1080 });
    // The collapsed rail leaves 1840 px, more than the container holds, so it is centred with modest gutters.
    const wide = await page.locator('#main-content').boundingBox();
    const narrowRail = await page.locator('#app-sidebar').boundingBox();
    expect(wide && narrowRail).toBeTruthy();
    if (!wide || !narrowRail) return;
    const gutter = wide.x - (narrowRail.x + narrowRail.width);
    expect(Math.abs(gutter - (1920 - (wide.x + wide.width)))).toBeLessThan(2);
    expect(wide.width / 1920).toBeGreaterThan(0.8);
});


// Signed in, the account band takes room from the column the places and the status share, so a window
// that suits the status signed out may not suit it signed in. Across those heights the card is either
// absent or whole: its heading, its first reading and the way to Health each drawn in full inside it,
// never squashed to an empty bar (a phone at 390 × 700 once showed the card about 20 px tall). Where it
// shows at rest it shows whole, and at worst the places and the status scroll together.
async function cardFaults(page: Page): Promise<string[]> {
    return page.locator('[data-sidebar-scroll]').evaluate((column) => {
        const card = column.querySelector<HTMLElement>('[data-sidebar-status-card]');
        // A card left out waits above the window, so its load meters, which sample only on screen, stop.
        if (card && !card.checkVisibility({ visibilityProperty: true })) {
            return card.getBoundingClientRect().bottom > 0 ? [`the unseen card is over the window at ${innerWidth} × ${innerHeight}`] : [];
        }
        if (!card) return [];
        const faults: string[] = [];
        const at = `at ${innerWidth} × ${innerHeight}`;
        const readings = card.querySelector<HTMLElement>('[data-sidebar-status-readings]');
        const parts = {
            heading: card.querySelector<HTMLElement>('#sidebar-status-title'),
            'first reading': card.querySelector<HTMLElement>('[data-status-row]'),
            'Health link': card.querySelector<HTMLElement>('[data-sidebar-status-link]')
        };
        const view = column.getBoundingClientRect();
        const box = card.getBoundingClientRect();
        // At rest, never a sliver: the card is wholly in view, or wholly below the places.
        if (box.top < view.bottom - 1 && box.bottom > view.bottom + 1) faults.push(`the card is cut at the foot of the column at rest ${at}`);
        // Scrolled as far as it goes, every part is whole in the column, in the card, and (the heading and
        // first reading) in the readings' own scrolled clip.
        column.scrollTop = column.scrollHeight;
        const shown = column.getBoundingClientRect();
        const cardBox = card.getBoundingClientRect();
        const clip = readings?.getBoundingClientRect();
        for (const [name, part] of Object.entries(parts)) {
            if (!part) { faults.push(`no ${name} ${at}`); continue; }
            const r = part.getBoundingClientRect();
            if (r.height < 1) faults.push(`the ${name} is not drawn ${at}`);
            if (r.top < cardBox.top - 1 || r.bottom > cardBox.bottom + 1) faults.push(`the ${name} spills out of the card ${at}`);
            if (r.top < shown.top - 1 || r.bottom > shown.bottom + 1) faults.push(`the ${name} cannot be scrolled into view ${at}`);
            if (clip && name !== 'Health link' && (r.top < clip.top - 1 || r.bottom > clip.bottom + 1)) faults.push(`the ${name} is clipped by the readings ${at}`);
        }
        column.scrollTop = 0;
        return faults;
    });
}

async function openShell(page: Page, size: { width: number; height: number }, signedIn = true, german = false): Promise<void> {
    await page.setViewportSize(size);
    if (german) await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await replayFeeder(page, 'dark', {}, (json, url) =>
        signedIn && url.pathname === '/api/auth/status' ? { ...(json as Record<string, unknown>), auth_required: true, is_authenticated: true, username: 'owner' } : json
    );
    await page.goto('/');
    if (size.width < 768) await page.locator('button[aria-controls="app-sidebar"]').click();
    await expect(page.locator('#app-sidebar nav')).toBeVisible(READY);
    await expect(page.locator('[data-sidebar-account-band]')).toHaveCount(signedIn ? 1 : 0);
    await settled(page);
}

for (const range of [{ width: 390, from: 672, to: 800, signedIn: true }, { width: 1280, from: 680, to: 780, signedIn: true }, { width: 390, from: 672, to: 800, signedIn: false }]) {
    test(`signed ${range.signedIn ? 'in' : 'out'} at ${range.width} px wide and ${range.from} to ${range.to} px tall the status card is whole or absent, never squashed`, async ({ page }) => {
        await openShell(page, { width: range.width, height: range.to }, range.signedIn);
        await expect(page.locator('[data-sidebar-status-readings] [data-status-row]').first()).toBeAttached(READY);
        for (let height = range.from; height <= range.to; height += 8) {
            await page.setViewportSize({ width: range.width, height });
            await expect.poll(() => hiddenPlaces(page), { timeout: 3_000 }).toEqual([]);
            await expect.poll(() => cardFaults(page), { timeout: 3_000 }).toEqual([]);
        }
    });
}

// A phone tall enough for the status keeps it: the drawer is not emptied where the card fits, and where
// every reading fits, the load meters included, every one is drawn with nothing to scroll.
test('signed in on a 390 × 844 phone the menu shows the whole status card, its load meters too', async ({ page }) => {
    await openShell(page, { width: 390, height: 844 });
    const card = page.locator('[data-sidebar-status-card]');
    await expect(card).toBeVisible(READY);
    await expect(card.locator('[data-sidebar-status-link]')).toBeInViewport({ ratio: 1 });
    await expect(card.locator('[data-telemetry-readout]')).toBeInViewport({ ratio: 1 });
    const readings = page.locator('[data-sidebar-status-readings]');
    expect(await readings.evaluate((node) => node.scrollHeight - node.clientHeight)).toBeLessThanOrEqual(0);
    expect(await cardFaults(page)).toEqual([]);
});

// At rest the readings end at their last whole line of words: no blank band under it, where a line was
// counted that draws nothing. The load meters once emptied themselves whenever the readings ended above
// them (they sample only while seen, and judged that by their own clip), which gave their room back, so
// the readings grew to show an empty meter row, the meters filled, and round again on every frame.
async function blankUnderLastLine(page: Page): Promise<string | null> {
    return page.locator('[data-sidebar-status-readings]').evaluate(async (node) => {
        const frames = async (count: number): Promise<number[]> => {
            const heights: number[] = [];
            for (let frame = 0; frame < count; frame += 1) {
                await new Promise((done) => requestAnimationFrame(done));
                heights.push(Math.round(node.getBoundingClientRect().height));
            }
            return heights;
        };
        const heights = await frames(12);
        // A card left out has nothing at rest to judge.
        if (!node.checkVisibility({ visibilityProperty: true })) return null;
        if (new Set(heights).size > 1) return `the readings do not hold still at ${innerWidth} × ${innerHeight}: ${heights.join(' ')}`;
        const box = node.getBoundingClientRect();
        const bottom = box.top + node.clientHeight;
        const words = [...node.querySelectorAll<HTMLElement>('*')]
            .filter((element) => element.children.length === 0 && (element.textContent ?? '').trim() !== '')
            .map((element) => element.getBoundingClientRect())
            .filter((line) => line.height > 0 && line.bottom <= bottom + 1);
        const line = node.querySelector('h2')?.getBoundingClientRect().height ?? 16;
        const last = Math.max(...words.map((word) => word.bottom));
        return bottom - last > line + 1 ? `${Math.round(bottom - last)} px blank under the last line at ${innerWidth} × ${innerHeight}` : null;
    });
}

for (const german of [false, true]) {
    test(`signed in on a phone 780 to 900 px tall in ${german ? 'German' : 'English'}, the status readings end at their last line`, async ({ page }) => {
        await openShell(page, { width: 390, height: 900 }, true, german);
        await expect(page.locator('[data-sidebar-status-readings] [data-telemetry-readout]')).toBeVisible(READY);
        for (let height = 780; height <= 900; height += 4) {
            await page.setViewportSize({ width: 390, height });
            await expect.poll(() => blankUnderLastLine(page), { timeout: 3_000 }).toBeNull();
        }
    });
}

// The collapsed icon rail holds the same status as icons, with the way to Health under them. It has no
// readings to give way, so the group is all or nothing: whole and in view where the room under the
// places holds it, and otherwise left out (Health is still one of the places), never cut at the foot.
async function railFaults(page: Page): Promise<string[]> {
    return page.locator('[data-sidebar-scroll]').evaluate((column) => {
        const group = column.querySelector<HTMLElement>('[data-sidebar-status-card]');
        const at = `at ${innerWidth} × ${innerHeight}`;
        if (!group) return [];
        if (!group.checkVisibility({ visibilityProperty: true })) {
            // Left out only where it does not fit: the room under the places is less than the whole group.
            const holder = group.closest<HTMLElement>('[data-sidebar-status]');
            const places = column.querySelector('nav')?.getBoundingClientRect().height ?? 0;
            const room = column.clientHeight - places;
            return holder && holder.getBoundingClientRect().height <= room ? [`the group is left out where it fits ${at}`] : [];
        }
        const view = column.getBoundingClientRect();
        const box = group.getBoundingClientRect();
        const parts = [...group.querySelectorAll<HTMLElement>('[data-status-row], [data-sidebar-status-link]')];
        const faults: string[] = [];
        if (parts.length === 0) faults.push(`the group shows no icons ${at}`);
        if (group.scrollHeight > group.clientHeight + 1) faults.push(`the group is squashed below its icons (${group.clientHeight} of ${group.scrollHeight} px) ${at}`);
        if (box.top < view.top - 1 || box.bottom > view.bottom + 1) faults.push(`the group is not wholly in view ${at}`);
        for (const part of parts) {
            const r = part.getBoundingClientRect();
            const name = part.dataset.statusRow ?? 'Health link';
            if (r.top < box.top - 1 || r.bottom > box.bottom + 1) faults.push(`the ${name} icon spills out of the group ${at}`);
            if (r.top < view.top - 1 || r.bottom > view.bottom + 1) faults.push(`the ${name} icon is cut by the column ${at}`);
        }
        return faults;
    });
}

for (const signedIn of [true, false]) {
    test(`with the sidebar collapsed, signed ${signedIn ? 'in' : 'out'}, at 1280 × 640 to 800 the rail's status is whole and in view or left out`, async ({ page }) => {
        await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
        await openShell(page, { width: 1280, height: 800 }, signedIn);
        await expect(page.locator('[data-sidebar-status-card] [data-status-row]').first()).toBeAttached(READY);
        for (let height = 640; height <= 800; height += 8) {
            await page.setViewportSize({ width: 1280, height });
            await expect.poll(() => railFaults(page), { timeout: 3_000 }).toEqual([]);
        }
        // A window tall enough keeps it.
        await page.setViewportSize({ width: 1280, height: 960 });
        await expect(page.locator('[data-sidebar-status-card]')).toBeVisible();
        await expect.poll(() => railFaults(page), { timeout: 3_000 }).toEqual([]);
    });
}
