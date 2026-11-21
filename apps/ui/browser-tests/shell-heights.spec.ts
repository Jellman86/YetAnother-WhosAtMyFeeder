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
            // Dashboard, Explorer, Leaderboard, Audio history, Settings, Health and About: Add observation
            // is in the header on a desktop.
            expect(await page.locator('#app-sidebar nav button').count()).toBeGreaterThanOrEqual(7);
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
                // The tier the room calls for: whole where the floor fits, else the one-line summary.
                await expect(readings.locator('[data-status-row]').first()).toBeAttached(READY);
                await expect.poll(() => faultsOf(page, 'open'), READY).toEqual([]);
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


// The status in the room under the places, in four tiers. Where its floor fits (heading, first reading
// and the way to Health; on the icon rail, the whole group) the full card shows, whole and in view. Where
// only a single line fits, the one-line summary shows instead, and where only a 24 px target fits, the
// compact summary: whole, in view, its words on one or two lines, so the sidebar is never an unexplained
// gap. Only where not even that fits does the Health place carry the status (its mark and name, for the
// owner with issues open), with the whole card just past the foot of the column: never a sliver at rest,
// never squashed (a phone at 390 × 700 once showed the card as an empty bar about 20 px tall). The tier
// is worked out here from the measured room, so a check cannot pass by always showing a summary.
type Who = 'owner' | 'open' | 'guest';

async function statusFaults(page: Page, who: Who = 'owner'): Promise<{ faults: string[]; form: string }> {
    return page.locator('[data-sidebar-scroll]').evaluate((column, who) => {
        const at = `at ${innerWidth} × ${innerHeight}`;
        const holder = column.querySelector<HTMLElement>('[data-sidebar-status]');
        const full = holder?.querySelector<HTMLElement>('[data-sidebar-status-card]');
        const summary = holder?.querySelector<HTMLElement>('[data-sidebar-status-summary]');
        const compact = holder?.querySelector<HTMLElement>('[data-sidebar-status-compact]');
        if (!holder || !full || !summary || !compact || !full.parentElement) return { faults: [`the status is missing a form ${at}`], form: 'none' };
        const seen = (element: HTMLElement): boolean => element.checkVisibility({ visibilityProperty: true });
        const form = seen(full) ? 'full' : seen(summary) ? 'summary' : seen(compact) ? 'compact' : 'none';
        if (form === 'none') return { faults: [`no form of the status shows ${at}`], form };
        const height = (element: Element): number => element.getBoundingClientRect().height;
        const outer = (element: Element): number => {
            const style = getComputedStyle(element);
            return height(element) + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
        };
        const nav = column.querySelector('nav');
        const room = column.clientHeight - (nav ? height(nav) : 0);
        const frame = height(holder) - height(full.parentElement);
        const readings = full.querySelector<HTMLElement>('[data-sidebar-status-readings]');
        const firstRow = full.querySelector<HTMLElement>('[data-status-row]');
        const floor = readings && firstRow
            ? frame + height(full) - height(readings) + firstRow.getBoundingClientRect().bottom - (readings.getBoundingClientRect().top - readings.scrollTop)
            : frame + height(full);
        const line = frame + outer(summary);
        // The compact form counts only while its words keep to one or two lines.
        const compactWords = compact.querySelector<HTMLElement>('[data-summary-row], [data-summary-issues]');
        const compactTwoLines = !compactWords || height(compactWords) <= 2 * (parseFloat(getComputedStyle(compactWords).lineHeight) || 16) + 1;
        const compactLine = compactTwoLines ? frame + outer(compact) : Number.POSITIVE_INFINITY;
        // Which tiers this room allows; within a pixel of a threshold, either side of it.
        const allowed = new Set<string>();
        for (const slack of [-1, 0, 1]) {
            const r = room + slack;
            allowed.add(r < 0 ? 'health' : floor <= r ? 'full' : line <= r ? 'summary' : compactLine <= r ? 'compact' : 'health');
        }
        const view = column.getBoundingClientRect();
        const faults: string[] = [];
        const tier = form !== 'full' ? form : full.getBoundingClientRect().top >= view.bottom - 1 ? 'health' : 'full';
        if (!allowed.has(tier)) faults.push(`${tier} shows where the room (${Math.round(room)} px; card floor ${Math.round(floor)}, summary ${Math.round(line)}, compact ${Math.round(compactLine)}) calls for ${[...allowed].join(' or ')} ${at}`);
        // The Health place carries the status (its mark, and its name with the issues) only where the
        // status does not show at rest, and only with issues open: never twice.
        const attention = holder.querySelector('[data-health-attention="true"]') !== null;
        const place = nav?.querySelector<HTMLElement>('[data-nav-path="/system-health"]');
        const marked = Boolean(place?.querySelector('[data-health-carries-status]'));
        const carries = tier === 'health' && attention && who !== 'guest';
        if (carries && !marked) faults.push(`the status does not show and the Health place does not carry it ${at}`);
        if (carries && !/: /.test(place?.getAttribute('aria-label') ?? '')) faults.push(`the Health place is not named by the open issues ${at}`);
        if (!carries && marked) faults.push(`the Health place carries the status while it shows ${at}`);
        if (tier === 'health') return { faults, form: tier };
        const shown = form === 'full' ? full : form === 'summary' ? summary : compact;
        const box = shown.getBoundingClientRect();
        // At rest, never a sliver: wholly in view, or wholly past the foot of the column.
        if (box.top < view.bottom - 1 && box.bottom > view.bottom + 1) faults.push(`the ${form} is cut at the foot of the column at rest ${at}`);
        if (shown.scrollHeight > shown.clientHeight + 1) faults.push(`the ${form} is squashed below its content ${at}`);
        if (form !== 'full') {
            if (box.height < 24) faults.push(`the ${form} summary is ${Math.round(box.height)} px tall, under a 24 px target ${at}`);
            if (box.top < view.top - 1 || box.bottom > view.bottom + 1) faults.push(`the ${form} summary is not wholly in view ${at}`);
            const link = shown.querySelector('a[href]');
            if (who === 'guest' ? link : !link) faults.push(`the ${form} summary ${who === 'guest' ? 'links a guest to Health' : 'has no way to Health'} ${at}`);
            if ((shown.textContent ?? '').trim() === '' && !shown.querySelector('[title]')) faults.push(`the ${form} summary says nothing ${at}`);
            // The compact form's words whole, on one or two lines (the full-size line wraps as its words need).
            const words = shown.querySelector<HTMLElement>('[data-summary-row], [data-summary-issues]');
            const lineHeight = parseFloat(getComputedStyle(words ?? shown).lineHeight) || 16;
            if (form === 'compact' && readings && words && height(words) > 2 * lineHeight + 1) faults.push(`the ${form} summary runs past two lines ${at}`);
            return { faults, form: tier };
        }
        // The full card: scrolled as far as it goes, every part is whole in the column, in the card, and
        // (the heading and first reading) in the readings' own scrolled clip.
        const parts: [string, HTMLElement | null][] = readings
            ? [['heading', full.querySelector('h2')], ['first reading', firstRow], ...(who === 'guest' ? [] : [['Health link', full.querySelector<HTMLElement>('[data-sidebar-status-link]')] as [string, HTMLElement | null]])]
            : [...full.querySelectorAll<HTMLElement>('[data-status-row], [data-sidebar-status-link]')].map((part): [string, HTMLElement] => [part.dataset.statusRow ?? 'Health link', part]);
        column.scrollTop = column.scrollHeight;
        const scrolled = column.getBoundingClientRect();
        const cardBox = full.getBoundingClientRect();
        const clip = readings?.getBoundingClientRect();
        for (const [name, part] of parts) {
            if (!part) { faults.push(`no ${name} ${at}`); continue; }
            const r = part.getBoundingClientRect();
            if (r.height < 1) faults.push(`the ${name} is not drawn ${at}`);
            if (r.top < cardBox.top - 1 || r.bottom > cardBox.bottom + 1) faults.push(`the ${name} spills out of the card ${at}`);
            if (r.top < scrolled.top - 1 || r.bottom > scrolled.bottom + 1) faults.push(`the ${name} cannot be scrolled into view ${at}`);
            if (clip && name !== 'Health link' && (r.top < clip.top - 1 || r.bottom > clip.bottom + 1)) faults.push(`the ${name} is clipped by the readings ${at}`);
        }
        column.scrollTop = 0;
        return { faults, form: tier };
    }, who);
}

const faultsOf = async (page: Page, who: Who = 'owner'): Promise<string[]> => (await statusFaults(page, who)).faults;

const GUEST = { auth_required: true, is_authenticated: false, public_access_enabled: true };
const OWNER = { auth_required: true, is_authenticated: true, username: 'owner' };

async function openShell(page: Page, size: { width: number; height: number }, who: Who | boolean = 'owner', german = false): Promise<void> {
    const as: Who = who === true ? 'owner' : who === false ? 'open' : who;
    await page.setViewportSize(size);
    if (german) await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await replayFeeder(page, 'dark', {}, (json, url) =>
        as !== 'open' && url.pathname === '/api/auth/status' ? { ...(json as Record<string, unknown>), ...(as === 'owner' ? OWNER : GUEST) } : json
    );
    await page.goto('/');
    if (size.width < 768) await page.locator('button[aria-controls="app-sidebar"]').click();
    await expect(page.locator('#app-sidebar nav')).toBeVisible(READY);
    await expect(page.locator('[data-sidebar-account-band]')).toHaveCount(as === 'open' ? 0 : 1);
    await settled(page);
}

/** Walks a range of heights, checking the status at each, and returns the tiers it saw. */
async function walk(page: Page, width: number, from: number, to: number, who: Who): Promise<Set<string>> {
    const tiers = new Set<string>();
    for (let height = from; height <= to; height += 8) {
        await page.setViewportSize({ width, height });
        await expect.poll(() => faultsOf(page, who), { timeout: 3_000 }).toEqual([]);
        tiers.add((await statusFaults(page, who)).form);
    }
    return tiers;
}

/** Whether the status shows at rest in some form: the card, a summary, or the Health place's mark. */
async function statusOnShow(page: Page): Promise<boolean> {
    const { form } = await statusFaults(page, 'owner');
    return form !== 'health' || (await page.locator('#app-sidebar nav [data-health-carries-status]').count()) === 1;
}

const RANGES: { name: string; width: number; from: number; to: number; who: Who; tall: number; expect: string[] }[] = [
    { name: 'the phone menu, signed in', width: 390, from: 672, to: 800, who: 'owner', tall: 900, expect: ['full', 'summary', 'compact'] },
    // On a desktop Add observation is in the header, not a place, so the room under the places is one
    // place (48 px) taller than on the phone, and the tiers change that much lower down.
    { name: 'a desktop, signed in', width: 1280, from: 632, to: 732, who: 'owner', tall: 900, expect: ['full', 'summary', 'compact'] },
    { name: 'the phone menu, signed out', width: 390, from: 672, to: 800, who: 'open', tall: 900, expect: ['full'] },
    // A guest has fewer places (no Add observation, Settings or Health), so the room runs out lower down.
    { name: 'the phone menu, as a guest', width: 390, from: 520, to: 680, who: 'guest', tall: 900, expect: ['full', 'summary'] },
    // The owner's laptop: a wide window just over 900 px tall, where the brand stacks over its mark (it
    // sits beside it only up to 900 px tall) and the text is larger with the width. With Add observation
    // in the header rather than among the places, the card's floor fits on both sides of that boundary,
    // so the card stays whole there; the walk still holds every height to the tier its room calls for.
    { name: 'a wide desktop around the brand stacking, signed in', width: 1920, from: 880, to: 1000, who: 'owner', tall: 1080, expect: ['full'] },
    // Lower down on the same wide desktop, the card does give way: measured at about 764 px tall, so a
    // walk from 720 to 840 crosses from the one-line summary to the card with the larger text.
    { name: 'a wide desktop, signed in', width: 1920, from: 720, to: 840, who: 'owner', tall: 1080, expect: ['full', 'summary'] }
];

for (const range of RANGES) {
    test(`${range.name}, at ${range.width} px wide and ${range.from} to ${range.to} px tall the status is the card, the one-line summary, or past the fold, never squashed`, async ({ page }) => {
        await openShell(page, { width: range.width, height: range.to }, range.who);
        await expect(page.locator('[data-sidebar-status-readings] [data-status-row]').first()).toBeAttached(READY);
        const tiers = await walk(page, range.width, range.from, range.to, range.who);
        for (const tier of range.expect) expect(tiers, `the range shows the ${tier} tier somewhere`).toContain(tier);
        // Shown in full where there is plenty of room.
        await page.setViewportSize({ width: range.width, height: range.tall });
        await expect(page.locator('[data-sidebar-status-card]')).toBeVisible();
        await expect.poll(async () => (await statusFaults(page, range.who)).form).toBe('full');
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
    expect(await faultsOf(page)).toEqual([]);
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

// The collapsed icon rail holds the same status as icons, with the way to Health under them. Nothing in
// the group gives way, so where the whole group does not fit, one icon stands in for it: the Health link
// with its attention mark for the owner, or the most important status for a guest.
for (const [who, from] of [['owner', 640], ['open', 640], ['guest', 480]] as const) {
    test(`with the sidebar collapsed (${who}), at 1280 × ${from} to 860 the rail's status is the whole group, one icon, a small icon or the Health place`, async ({ page }) => {
        await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
        await openShell(page, { width: 1280, height: 860 }, who);
        await expect(page.locator('[data-sidebar-status-card] [data-status-row]').first()).toBeAttached(READY);
        const tiers = await walk(page, 1280, from, 860, who);
        expect(tiers, 'the single icon shows somewhere in the range').toContain('summary');
        await page.setViewportSize({ width: 1280, height: 1000 });
        await expect(page.locator('[data-sidebar-status-card]')).toBeVisible();
        await expect.poll(() => faultsOf(page, who), { timeout: 3_000 }).toEqual([]);
    });
}

// Keyboard focus follows the tier: on the card's Health link when the window shortens, it moves to the
// summary's link, and back to the card's when the window grows. It is never left on something unseen.
test('focus on the status moves to the same control in the new tier', async ({ page }) => {
    await openShell(page, { width: 1280, height: 960 });
    const cardLink = page.locator('[data-sidebar-status-link]');
    await expect(cardLink).toBeVisible(READY);
    await cardLink.focus();
    await page.setViewportSize({ width: 1280, height: 672 });
    await expect(page.locator('[data-sidebar-status-summary]')).toBeVisible();
    await expect(page.locator('[data-sidebar-summary-link]')).toBeFocused();
    await page.setViewportSize({ width: 1280, height: 960 });
    await expect(page.locator('[data-sidebar-status-card]')).toBeVisible();
    await expect(cardLink).toBeFocused();
});

// The owner's rule: the status never vanishes. On a signed-in phone and on the collapsed rail, with
// issues open, every height shows it at rest in some form: the card, a summary, or the Health place's
// mark and name where nothing else fits.
for (const range of [{ width: 390, from: 664, to: 760, collapsed: false }, { width: 1280, from: 640, to: 860, collapsed: true }]) {
    test(`signed in, with issues open, at ${range.width} × ${range.from} to ${range.to}${range.collapsed ? ' with the sidebar collapsed' : ''} the status shows at rest in some form`, async ({ page }) => {
        if (range.collapsed) await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
        await openShell(page, { width: range.width, height: range.to });
        await expect(page.locator('[data-health-attention="true"]').first()).toBeAttached(READY);
        for (let height = range.from; height <= range.to; height += 8) {
            await page.setViewportSize({ width: range.width, height });
            await expect.poll(() => faultsOf(page), { timeout: 3_000 }).toEqual([]);
            expect(await statusOnShow(page), `the status shows at ${range.width} × ${height}`).toBe(true);
        }
    });
}

// Where the Health place carries the status, focus that was on the status moves to it.
test('focus on the status moves to the Health place when only the Health place can carry it', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
    await openShell(page, { width: 1280, height: 1000 });
    const link = page.locator('[data-sidebar-status-link]');
    await expect(link).toBeVisible(READY);
    await link.focus();
    await page.setViewportSize({ width: 1280, height: 672 });
    const place = page.locator('#app-sidebar nav [data-nav-path="/system-health"]');
    await expect(place.locator('[data-health-carries-status]')).toHaveCount(1);
    await expect(place).toHaveAccessibleName(/^Health: \d+ issues? needs? attention$/);
    await expect(place).toBeFocused();
});

// Focus parked on the Health place comes back to the status when it shows again, and the card waiting
// past the fold meanwhile is inert, so its issues are not announced a second time.
test('focus parked on the Health place returns to the status when it shows again', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
    await openShell(page, { width: 1280, height: 1000 });
    const link = page.locator('[data-sidebar-status-link]');
    await expect(link).toBeVisible(READY);
    await link.focus();
    await page.setViewportSize({ width: 1280, height: 672 });
    const place = page.locator('#app-sidebar nav [data-nav-path="/system-health"]');
    await expect(place).toBeFocused();
    await expect(page.locator('[data-sidebar-status]')).toHaveAttribute('inert', '');
    await page.setViewportSize({ width: 1280, height: 1000 });
    await expect(page.locator('[data-sidebar-status]')).not.toHaveAttribute('inert');
    await expect(link).toBeFocused();
});

// Focus the reader moved on themselves is theirs: the status showing again does not take it back.
test('focus the reader moved away from the Health place stays where they put it', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('sidebarCollapsed', 'true'));
    await openShell(page, { width: 1280, height: 1000 });
    const link = page.locator('[data-sidebar-status-link]');
    await expect(link).toBeVisible(READY);
    await link.focus();
    await page.setViewportSize({ width: 1280, height: 672 });
    await expect(page.locator('#app-sidebar nav [data-nav-path="/system-health"]')).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    const chosen = page.locator('#app-sidebar nav [data-nav-path="/settings"]');
    await expect(chosen).toBeFocused();
    await page.setViewportSize({ width: 1280, height: 1000 });
    await expect(link).toBeVisible();
    // Long enough for any move the resize set off (a task and a few frames) to have run.
    await page.waitForTimeout(300);
    await expect(chosen).toBeFocused();
});

// A resize that passes through the Health place's tier on its way to the summary ends with focus on the
// summary's link, not left on the Health place.
test('focus follows a resize through the Health place tier to the summary', async ({ page }) => {
    await openShell(page, { width: 1280, height: 960 });
    const cardLink = page.locator('[data-sidebar-status-link]');
    await expect(cardLink).toBeVisible(READY);
    await cardLink.focus();
    await page.setViewportSize({ width: 1280, height: 632 });
    await expect(page.locator('#app-sidebar nav [data-nav-path="/system-health"]')).toBeFocused();
    await page.setViewportSize({ width: 1280, height: 692 });
    await expect(page.locator('[data-sidebar-status-summary]')).toBeVisible();
    await expect(page.locator('[data-sidebar-summary-link]')).toBeFocused();
});
