import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';

/**
 * axe-core over the real app, with a month of data on every page, in both themes. A serious or
 * critical violation fails the build: contrast under 4.5:1, a control with no name or a name that
 * hides its visible words, list and definition-list structure, an unnamed progress bar.
 *
 * axe cannot assess focus order, target size beyond its own rule, or meaning carried by colour, so
 * this is a floor under the manual checks, not a replacement for them.
 */
const THEMES: Theme[] = ['light', 'dark'];
// A route is its own lazy chunk; on a busy CI runner its first paint can take several seconds.
const READY = { timeout: 15_000 };

const ROUTES: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
    { name: 'Dashboard', path: '/', ready: (page) => expect(page.locator('[data-field-log-row]').first()).toBeVisible(READY) },
    { name: 'Explorer', path: '/events', ready: (page) => expect(page.locator('[data-detection-card], [data-detection-row]').first()).toBeVisible(READY) },
    { name: 'Leaderboard', path: '/species', ready: (page) => expect(page.locator('[data-capture-wall-segment]').first()).toBeVisible(READY) },
    { name: 'Audio history', path: '/audio', ready: (page) => expect(page.locator('[data-audio-top-species-button]').first()).toBeVisible(READY) },
    { name: 'Notifications', path: '/notifications', ready: (page) => expect(page.getByText('Taxonomy sync').first()).toBeVisible(READY) },
    { name: 'About', path: '/about', ready: (page) => expect(page.locator('#about-outbound-title')).toBeVisible(READY) },
    { name: 'Add observation', path: '/observations/new', ready: (page) => expect(page.getByRole('heading', { level: 1 })).toBeVisible(READY) },
    { name: 'Model evaluation', path: '/diagnostics/model-eval', ready: (page) => expect(page.getByRole('heading', { level: 1 })).toBeVisible(READY) },
    { name: 'Health', path: '/system-health', ready: (page) => expect(page.locator('[data-sidebar-status-link]')).toBeVisible(READY) },
    { name: 'Not found', path: '/no-such-page', ready: (page) => expect(page.locator('#not-found-heading')).toBeVisible(READY) }
];

interface Finding { rule: string; impact: string; target: string; summary: string }

/** Every Settings tab. Each is scanned as it opens and again with every closed section opened. */
const SETTINGS_TABS = ['connection', 'detection', 'models', 'integrations', 'ai', 'notifications', 'security', 'data', 'maintenance', 'beta', 'appearance', 'accessibility'];
const settingsReady = (page: Page) => expect(page.locator('[data-settings-content]')).toBeVisible(READY);

/** Opens every closed section of a Settings tab, nested ones too; popover triggers are left alone. */
async function openEverySection(page: Page): Promise<void> {
    for (let round = 0; round < 6; round += 1) {
        const closed = page.locator('[data-settings-content] button[aria-expanded="false"]:visible:not([aria-haspopup])');
        const count = await closed.count();
        if (count === 0) return;
        for (let index = count - 1; index >= 0; index -= 1) await closed.nth(index).click().catch(() => undefined);
    }
}

/**
 * Every serious or critical axe finding in the whole document, one line each, so a failure names
 * the element. The whole document, not a subtree: dialogs are portalled to the body, outside the
 * page they were opened from.
 */
async function seriousFindings(page: Page): Promise<Finding[]> {
    const results = await new AxeBuilder({ page }).analyze();
    return results.violations
        .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
        .flatMap((violation) => violation.nodes.map((node) => ({
            rule: violation.id,
            impact: violation.impact ?? '',
            target: node.target.join(' '),
            summary: (node.failureSummary ?? '').replace(/\s+/g, ' ').slice(0, 220)
        })));
}

const FIRST_RUN = { auth_required: false, public_access_enabled: false, is_authenticated: false, needs_initial_setup: true };

/** The main dialogs, each opened the way a person opens it. `scope` is the dialog's own root. */
interface DialogCase {
    name: string;
    path: string;
    overrides?: Record<string, unknown>;
    scope: string;
    open: (page: Page) => Promise<void>;
}

async function openRecord(page: Page): Promise<void> {
    await expect(page.locator('[data-field-log-row]').first()).toBeVisible(READY);
    await page.locator('[data-field-log-row] [data-field-log-action]').first().click();
    // The record is a lazy chunk: its actions are the last thing it draws.
    await expect(page.locator('[data-detection-delete]')).toBeVisible(READY);
}

const DIALOGS: DialogCase[] = [
    { name: 'the record dialog', path: '/', scope: '[role="dialog"]', open: openRecord },
    {
        name: 'the delete confirmation', path: '/', scope: '[role="alertdialog"]',
        open: async (page) => {
            await openRecord(page);
            await page.locator('[data-detection-delete]').click();
            await expect(page.getByRole('alertdialog')).toBeVisible();
        }
    },
    {
        // A real test flow: the fixture answers no test request, so the checklist ends on its failure summary.
        name: 'the connection test dialog', path: '/settings/connection', scope: '[role="dialog"]',
        open: async (page) => {
            await page.getByRole('button', { name: /^test connection$/i }).first().click(READY);
            const dialog = page.getByRole('dialog');
            await expect(dialog.locator('#diagnostic-title')).toBeVisible();
            await expect(dialog.locator('[data-diagnostic-actions] button').last()).toBeEnabled(READY);
            await expect(dialog.locator('[data-diagnostic-result]')).toBeVisible(READY);
        }
    },
    {
        name: 'the video player', path: '/events', scope: '[role="dialog"]',
        open: async (page) => {
            // The clip never finishes arriving, which leaves the player open on its controls.
            await page.route((url) => /\/api\/frigate\/[^/]+\/(?:recording-)?clip\.mp4$/.test(url.pathname), async (route) => {
                if (route.request().method() === 'HEAD') return route.fulfill({ status: 200 });
                await new Promise(() => {});
            });
            await page.locator('button[aria-label^="Play video of"]').first().click(READY);
            await expect(page.getByRole('dialog').getByRole('button', { name: 'Share link' })).toBeVisible(READY);
        }
    },
    {
        name: 'the setup wizard', path: '/', overrides: { '/api/auth/status': FIRST_RUN }, scope: '[role="dialog"]',
        open: async (page) => {
            await expect(page.getByRole('dialog', { name: 'Setup wizard' }).getByRole('heading', { level: 2 })).toBeVisible(READY);
        }
    }
];

for (const theme of THEMES) {
    test.describe(`${theme} theme`, () => {
        test.use({ viewport: { width: 1440, height: 900 } });

        for (const route of ROUTES) {
            test(`${route.name} has no serious accessibility violation`, async ({ page }) => {
                await replayFeeder(page, theme);
                await page.goto(route.path);
                await route.ready(page);
                await settled(page);
                expect(await seriousFindings(page)).toEqual([]);
            });
        }

        for (const dialog of DIALOGS) {
            test(`${dialog.name} has no serious accessibility violation`, async ({ page }) => {
                await replayFeeder(page, theme, dialog.overrides);
                await page.goto(dialog.path);
                await dialog.open(page);
                await settled(page);
                expect(await seriousFindings(page)).toEqual([]);
            });
        }

        test('the sign-in screen has no accessibility violation at all, and one main landmark', async ({ page }) => {
            await replayFeeder(page, theme, {
                '/api/auth/status': { auth_required: true, public_access_enabled: false, is_authenticated: false, needs_initial_setup: false }
            });
            await page.goto('/');
            await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
            await settled(page);
            const results = await new AxeBuilder({ page }).analyze();
            expect(results.violations.map((violation) => violation.id)).toEqual([]);
            await expect(page.getByRole('main')).toHaveCount(1);
            // The skip link has somewhere to go.
            await expect(page.locator('#main-content')).toHaveCount(1);
        });
    });

    for (const width of [1440, 390]) {
        test.describe(`${theme} theme, Settings at ${width}px`, () => {
            test.use({ viewport: { width, height: 900 } });

            for (const tab of SETTINGS_TABS) {
                test(`Settings ${tab} has no serious accessibility violation, closed or with every section open`, async ({ page }) => {
                    await replayFeeder(page, theme);
                    await page.goto(`/settings/${tab}`);
                    await settingsReady(page);
                    await settled(page);
                    expect(await seriousFindings(page)).toEqual([]);
                    await openEverySection(page);
                    await settled(page);
                    expect(await seriousFindings(page)).toEqual([]);
                });
            }
        });
    }

    test.describe(`${theme} theme on a phone`, () => {
        test.use({ viewport: { width: 390, height: 844 } });

        test('the Dashboard and its open navigation drawer have no serious accessibility violation', async ({ page }) => {
            await replayFeeder(page, theme);
            await page.goto('/');
            await expect(page.locator('[data-field-log-row]').first()).toBeVisible();
            await settled(page);
            expect(await seriousFindings(page)).toEqual([]);
            await page.getByRole('banner').getByRole('button').first().click();
            await expect(page.locator('[data-sidebar-drawer="open"]')).toBeVisible();
            await settled(page);
            expect(await seriousFindings(page)).toEqual([]);
        });
    });
}

test('the sidebar status is a list inside a live region, and its link is named by its words', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/about');
    const tiles = page.locator('[data-status-tiles]');
    await expect(tiles).toBeVisible();
    // The list keeps its own role; the live region is its wrapper.
    await expect(tiles).not.toHaveAttribute('role');
    await expect(page.getByRole('status').filter({ has: tiles })).toHaveCount(1);
    expect(await tiles.getByRole('listitem').count()).toBeGreaterThanOrEqual(2);
    const link = page.locator('[data-sidebar-status-link]');
    await expect(link).toHaveAccessibleName('System health');
    await expect(link).not.toHaveAttribute('aria-label');
    // The link's hit area is the whole card, apart from the tiles.
    const card = await page.locator('[data-sidebar-status-card]').boundingBox();
    expect(card).not.toBeNull();
    await page.mouse.click((card?.x ?? 0) + 12, (card?.y ?? 0) + 12);
    await expect(page).toHaveURL(/\/system-health$/);
});

/**
 * WCAG 1.4.4: text at 200% loses nothing. The root font size is doubled from whatever the page
 * computed (the app is rem throughout, so this is what a browser's text-size setting does), and
 * then every piece of text on show is measured.
 */
async function doubleTheText(page: Page): Promise<void> {
    // Every run of text on show, by the size it is drawn at, before and after the root doubles.
    const sizes = (): Promise<number[]> => page.evaluate(() => {
        const marked = (window as unknown as { textOwners?: Element[] });
        if (!marked.textOwners) {
            const owners = new Set<Element>();
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                const owner = node.parentElement;
                if (owner && node.textContent?.trim() && !owner.closest('script, style, noscript, option, canvas, .leaflet-container') && owner.checkVisibility()) owners.add(owner);
            }
            marked.textOwners = [...owners];
        }
        return marked.textOwners.map((owner) => (owner.isConnected ? parseFloat(getComputedStyle(owner).fontSize) : 0));
    });
    const before = await sizes();
    await page.evaluate(() => {
        const size = parseFloat(getComputedStyle(document.documentElement).fontSize);
        const style = document.createElement('style');
        style.textContent = `html { font-size: ${size * 2}px !important; }`;
        document.head.append(style);
    });
    await settled(page);
    const after = await sizes();
    // Doubling the root must double the text itself, the smallest print included: a size held up
    // by a floor in pixels grows less than the page around it, and its clipping is never tested.
    const grew = before.flatMap((size, index) => (size > 0 && after[index] > 0 ? [{ from: size, ratio: Math.round((after[index] / size) * 100) / 100 }] : []));
    expect(new Set(grew.map((entry) => entry.from)).size, 'several text sizes are on show').toBeGreaterThanOrEqual(3);
    const short = [...new Set(grew.filter((entry) => entry.ratio < 1.98 || entry.ratio > 2.02).map((entry) => `${entry.from}px grew ${entry.ratio}x`))];
    expect(short).toEqual([]);
}

interface TextFault { fault: 'cut off' | 'outside its control' | 'overlapped'; text: string; where: string }

/** Text that is cut by a clipping box, spills out of its control, or is drawn over other text. */
async function textFaults(page: Page, scope: string): Promise<TextFault[]> {
    return page.evaluate((scopeSelector) => {
        const roots = [...document.querySelectorAll(scopeSelector)];
        const root = roots[roots.length - 1] ?? document.body;
        const TOLERANCE = 1.5;
        const describe = (element: Element): string => {
            const hook = [...element.attributes].find((attribute) => attribute.name.startsWith('data-'));
            return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ''}${hook ? `[${hook.name}]` : ''}.${String(element.className).split(/\s+/).slice(0, 3).join('.')}`;
        };
        interface Box { left: number; top: number; right: number; bottom: number }
        interface Piece { node: Text; owner: Element; box: Box; lines: Box[]; seen: Box }
        const faults: { fault: 'cut off' | 'outside its control' | 'overlapped'; text: string; where: string }[] = [];
        const say = (node: Text, fault: 'cut off' | 'outside its control' | 'overlapped', where: Element): void => {
            faults.push({ fault, text: (node.textContent ?? '').trim().slice(0, 40), where: describe(where) });
        };
        const pieces: Piece[] = [];
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const owner = node.parentElement;
            if (!owner || !node.textContent?.trim()) continue;
            if (owner.closest('script, style, noscript, [inert], option, .sr-only, .leaflet-container, canvas')) continue;
            if (!owner.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            const box = range.getBoundingClientRect();
            if (box.width < 1 || box.height < 1) continue;
            // What can be seen of the text: its box, less whatever each clipping or scrolling box
            // around it hides. A box that clips with no way to scroll has cut the text off; a
            // scrolling box has only moved it out of view.
            const seen: Box = { left: box.left, top: box.top, right: box.right, bottom: box.bottom };
            let cutBy: Element | null = null;
            for (let around: Element | null = owner; around && around !== document.documentElement; around = around.parentElement) {
                const style = getComputedStyle(around);
                if (style.display === 'inline' || (style.overflowX === 'visible' && style.overflowY === 'visible')) continue;
                const frame = around.getBoundingClientRect();
                if (style.overflowX !== 'visible') {
                    const hides = seen.left < frame.left - TOLERANCE || seen.right > frame.right + TOLERANCE;
                    if (hides && !cutBy && (style.overflowX === 'hidden' || style.overflowX === 'clip')) cutBy = around;
                    seen.left = Math.max(seen.left, frame.left);
                    seen.right = Math.min(seen.right, frame.right);
                }
                if (style.overflowY !== 'visible') {
                    const hides = seen.top < frame.top - TOLERANCE || seen.bottom > frame.bottom + TOLERANCE;
                    if (hides && !cutBy && (style.overflowY === 'hidden' || style.overflowY === 'clip')) cutBy = around;
                    seen.top = Math.max(seen.top, frame.top);
                    seen.bottom = Math.min(seen.bottom, frame.bottom);
                }
            }
            if (seen.right - seen.left < 1 || seen.bottom - seen.top < 1) continue;
            if (cutBy) say(node as Text, 'cut off', cutBy);
            const lines = [...range.getClientRects()]
                .map((line) => ({ left: Math.max(line.left, seen.left), top: Math.max(line.top, seen.top), right: Math.min(line.right, seen.right), bottom: Math.min(line.bottom, seen.bottom) }))
                .filter((line) => line.right - line.left > 0 && line.bottom - line.top > 0);
            pieces.push({ node: node as Text, owner, box, lines, seen });
        }
        for (const piece of pieces) {
            // Outside its control: a label wider or taller than the button, link or field it names.
            const control = piece.owner.closest('button, a, [role="button"], [role="tab"], [role="switch"], summary');
            if (!control || !root.contains(control)) continue;
            const frame = control.getBoundingClientRect();
            if (piece.seen.left < frame.left - TOLERANCE || piece.seen.right > frame.right + TOLERANCE || piece.seen.top < frame.top - TOLERANCE || piece.seen.bottom > frame.bottom + TOLERANCE) {
                const by = Math.round(Math.max(frame.left - piece.seen.left, piece.seen.right - frame.right, frame.top - piece.seen.top, piece.seen.bottom - frame.bottom));
                faults.push({ fault: 'outside its control', text: (piece.node.textContent ?? '').trim().slice(0, 40), where: `${describe(control)} by ${by}px` });
            }
        }
        // Overlapped: two runs of text in the same layer drawn across each other.
        const layerOf = (element: Element): Element => {
            for (let around: Element | null = element; around; around = around.parentElement) {
                const position = getComputedStyle(around).position;
                if (position === 'fixed' || position === 'sticky') return around;
            }
            return document.body;
        };
        const layers = pieces.map((piece) => layerOf(piece.owner));
        for (let first = 0; first < pieces.length; first += 1) {
            for (let second = first + 1; second < pieces.length; second += 1) {
                const a = pieces[first];
                const b = pieces[second];
                if (layers[first] !== layers[second] || a.owner.contains(b.owner) || b.owner.contains(a.owner)) continue;
                if (a.seen.right <= b.seen.left || b.seen.right <= a.seen.left || a.seen.bottom <= b.seen.top || b.seen.bottom <= a.seen.top) continue;
                const crossing = a.lines.some((line) => b.lines.some((other) =>
                    Math.min(line.right, other.right) - Math.max(line.left, other.left) > 3 && Math.min(line.bottom, other.bottom) - Math.max(line.top, other.top) > 3));
                if (crossing) say(a.node, 'overlapped', b.owner);
            }
        }
        return faults;
    }, scope);
}

/** What makes the page scroll sideways: the innermost boxes that reach past the window's right edge. */
async function widerThanTheWindow(page: Page): Promise<string[]> {
    return page.evaluate(() => {
        if (document.documentElement.scrollWidth <= innerWidth) return [];
        const past = [...document.body.querySelectorAll('*')].filter((element) => {
            if (!element.checkVisibility()) return false;
            // Inside a box that scrolls sideways by design, or the fixed drawer, nothing widens the page.
            for (let around = element.parentElement; around; around = around.parentElement) {
                const style = getComputedStyle(around);
                if (style.overflowX !== 'visible' || style.position === 'fixed') return false;
            }
            return element.getBoundingClientRect().right > innerWidth + 1;
        });
        return past.filter((element) => !past.some((other) => other !== element && element.contains(other)))
            .slice(0, 8)
            .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).split(/\s+/).slice(0, 4).join('.')} "${(element.textContent ?? '').trim().slice(0, 30)}"`);
    });
}

for (const width of [390, 1440]) {
    test.describe(`text at 200% in a ${width}px window`, () => {
        test.use({ viewport: { width, height: 900 } });

        for (const route of ROUTES.filter((entry) => ['Dashboard', 'Explorer', 'Leaderboard', 'Audio history', 'Notifications', 'About'].includes(entry.name))) {
            test(`${route.name} and the shell keep every word whole`, async ({ page }) => {
                await replayFeeder(page, 'light');
                await page.goto(route.path);
                await route.ready(page);
                await settled(page);
                await doubleTheText(page);
                expect(await widerThanTheWindow(page)).toEqual([]);
                expect(await textFaults(page, 'body')).toEqual([]);
                if (width < 768) {
                    // The shell on a phone is the drawer: every navigation label and status word in it.
                    await page.getByRole('banner').getByRole('button').first().click();
                    await expect(page.locator('[data-sidebar-drawer="open"]')).toBeVisible();
                    await settled(page);
                    expect(await textFaults(page, '#app-sidebar')).toEqual([]);
                }
            });
        }

        for (const tab of SETTINGS_TABS) {
            test(`Settings ${tab} keeps every word whole, every section open`, async ({ page }) => {
                await replayFeeder(page, 'light');
                await page.goto(`/settings/${tab}`);
                await settingsReady(page);
                await openEverySection(page);
                await settled(page);
                await doubleTheText(page);
                expect(await widerThanTheWindow(page)).toEqual([]);
                expect(await textFaults(page, '#main-content')).toEqual([]);
            });
        }

        test('a long German page name is drawn at twice its size and shown whole', async ({ page }) => {
            await replayFeeder(page, 'light');
            await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
            await page.goto('/notifications');
            const title = page.getByRole('heading', { level: 1, name: 'Benachrichtigungen' });
            await expect(title).toBeVisible(READY);
            await settled(page);
            const size = (): Promise<number> => title.evaluate((node) => parseFloat(getComputedStyle(node).fontSize));
            const normal = await size();
            await doubleTheText(page);
            // The title is text like any other: twice its own size, not a step down to fit.
            expect(await size()).toBeGreaterThanOrEqual(normal * 2 - 0.5);
            expect(await widerThanTheWindow(page)).toEqual([]);
            expect(await textFaults(page, 'body')).toEqual([]);
            // One long word still fits its column, broken at a syllable where the browser can and anywhere if it cannot.
            const box = await title.boundingBox();
            expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width + 1);
        });

        for (const dialog of DIALOGS) {
            test(`${dialog.name} keeps every word whole`, async ({ page }) => {
                await replayFeeder(page, 'light', dialog.overrides);
                await page.goto(dialog.path);
                await dialog.open(page);
                await settled(page);
                await doubleTheText(page);
                expect(await textFaults(page, dialog.scope)).toEqual([]);
            });
        }
    });
}

test.describe('the Leaderboard at a large text size', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('ranks in a full table at the normal size and reflows into stacked rows when the text is doubled', async ({ page }) => {
        await replayFeeder(page, 'light');
        await page.goto('/species');
        const table = page.locator('[data-leaderboard-table-rankings]');
        const stacked = page.locator('[data-leaderboard-stacked-rankings]');
        await expect(table).toBeVisible(READY);
        await expect(stacked).toBeHidden();
        // Every column the table has is on show in a desktop window at the normal size.
        await expect(table.getByRole('columnheader', { name: 'Avg confidence' })).toBeVisible();
        await settled(page);
        await doubleTheText(page);
        await expect(stacked).toBeVisible();
        await expect(table).toBeHidden();
        // The stacked row still says what the table said first: rank, name and count, each whole.
        const first = stacked.getByRole('button').first();
        await expect(first).toContainText('Eurasian Blue Tit');
        await expect(first.getByLabel('Rank 1')).toBeVisible();
    });

    for (const theme of THEMES) {
        test(`the share bar names every segment in words without a pointer or focus (${theme})`, async ({ page }) => {
            await replayFeeder(page, theme);
            await page.goto('/species');
            const segments = page.locator('[data-capture-wall-segment]');
            await expect(segments.first()).toBeVisible(READY);
            await settled(page);
            const named = await segments.evaluateAll((nodes) => nodes.map((node) => (node.getAttribute('aria-label') ?? '').split(',')[0]));
            const key = page.locator('[data-capture-wall-key] li');
            await expect(key).toHaveCount(named.length);
            for (const [index, name] of named.entries()) {
                await expect(key.nth(index)).toBeVisible();
                await expect(key.nth(index)).toContainText(name);
                await expect(key.nth(index)).toContainText('%');
            }
        });
    }
});

test('the page declares the language on screen, and a long German label is shown whole', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/about');
    await expect(page.locator('html')).toHaveAttribute('lang', 'de');
    const labels = page.locator('#app-sidebar nav button span');
    await expect(labels.filter({ hasText: 'Beobachtung hinzufügen' })).toBeVisible();
    const cut = await labels.evaluateAll((nodes) => nodes.filter((node) => node.scrollWidth > node.clientWidth + 1).map((node) => node.textContent));
    expect(cut).toEqual([]);
});

for (const theme of THEMES) {
    test(`keyboard focus draws an opaque ring that stands out from the page (${theme})`, async ({ page }) => {
        await replayFeeder(page, theme);
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.goto('/events');
        await expect(page.locator('#app-sidebar nav button').first()).toBeVisible();
        await settled(page);
        const ring = await page.evaluate(() => {
            const parse = (colour: string): number[] => (colour.match(/[\d.]+/g) ?? []).map(Number);
            const luminance = ([red, green, blue]: number[]): number => {
                const channel = (value: number): number => { const unit = value / 255; return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4; };
                return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
            };
            const contrast = (first: number[], second: number[]): number => {
                const [lighter, darker] = [luminance(first), luminance(second)].sort((a, b) => b - a);
                return (lighter + 0.05) / (darker + 0.05);
            };
            const style = getComputedStyle(document.documentElement);
            const focus = parse(`rgb(${style.getPropertyValue('--focus')})`);
            const grounds = ['--surface', '--surface-raised'].map((name) => parse(`rgb(${style.getPropertyValue(name)})`));
            grounds.push(parse(getComputedStyle(document.body).backgroundColor));
            return { alpha: focus.length, ratios: grounds.map((ground) => contrast(focus, ground)) };
        });
        expect(ring.alpha, 'the focus colour is three opaque channels').toBe(3);
        for (const ratio of ring.ratios) expect(ratio).toBeGreaterThanOrEqual(3);

        // The ring is really drawn in that colour on keyboard focus, on a kit button and a kit field.
        const navButton = page.locator('#app-sidebar nav button').first();
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await page.keyboard.press('Tab');
        await expect(navButton).toBeFocused();
        const drawn = await navButton.evaluate((node) => getComputedStyle(node).boxShadow);
        const expected = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--focus').trim().split(/\s+/).join(', '));
        expect(drawn).toContain(`rgb(${expected})`);
    });
}

test('About holds still on a phone when the feeder portrait lands without a picture', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await replayFeeder(page, 'light');
    // The portrait is the slow read; the recorded feeder has no picture of its latest visit.
    await page.route((url) => url.pathname === '/api/about/portrait', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        await route.fallback();
    });
    await page.goto('/about');
    await expect(page.locator('[data-feeder-portrait-loading]')).toBeVisible();
    const before = await page.locator('#about-workflow').evaluate((node) => node.getBoundingClientRect().top + scrollY);
    await expect(page.locator('[data-feeder-portrait]')).toBeVisible();
    await expect(page.locator('[data-feeder-portrait-no-visit]')).toBeVisible();
    const after = await page.locator('#about-workflow').evaluate((node) => node.getBoundingClientRect().top + scrollY);
    // The picture's slot is kept, so what follows moves by a line of text at most, not a photograph.
    expect(Math.abs(after - before)).toBeLessThanOrEqual(24);
});

for (const width of [390, 1440]) {
    test(`Notifications draws its history once, so background jobs landing late move nothing (${width}px)`, async ({ page }) => {
        await page.setViewportSize({ width, height: 844 });
        await replayFeeder(page, 'light');
        // Nothing kept on this device, and the jobs reading is the slow one.
        await page.addInitScript(() => {
            localStorage.setItem('yawamf_notification_center', '[]');
            let total = 0;
            new PerformanceObserver((list) => {
                for (const entry of list.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) {
                    if (!entry.hadRecentInput) total += entry.value;
                }
                document.documentElement.dataset.layoutShift = String(total);
            }).observe({ type: 'layout-shift', buffered: true });
        });
        await page.route((url) => url.pathname === '/api/jobs', async (route) => {
            await new Promise((resolve) => setTimeout(resolve, 1200));
            await route.fallback();
        });
        await page.goto('/notifications');
        // Until the jobs are in, the page says it is loading and offers no page controls for a partial list.
        await expect(page.locator('[data-notifications-loading]')).toBeVisible(READY);
        await expect(page.locator('[data-notifications-pagination]')).toHaveCount(0);
        await expect(page.getByText('Taxonomy sync').first()).toBeVisible(READY);
        await expect(page.locator('[data-notifications-loading]')).toHaveCount(0);
        await settled(page);
        const shift = Number(await page.locator('html').getAttribute('data-layout-shift') ?? 0);
        expect(shift).toBeLessThan(0.02);
    });
}

for (const enlarge of ['the browser text size', 'the root size'] as const) {
    test(`at 200% by ${enlarge} in a 1440x900 window every sidebar link is reached by Tab with its focus ring on show`, async ({ page }) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await replayFeeder(page, 'light');
        if (enlarge === 'the browser text size') {
            const session = await page.context().newCDPSession(page);
            await session.send('Page.setFontSizes', { fontSizes: { standard: 32 } });
        }
        await page.goto('/about');
        const links = page.locator('#app-sidebar nav button');
        await expect(links.first()).toBeVisible(READY);
        await settled(page);
        if (enlarge === 'the root size') await doubleTheText(page);
        const total = await links.count();
        expect(total).toBeGreaterThanOrEqual(5);
        const reached: string[] = [];
        // Tab from the top of the page, as a keyboard user arrives.
        for (let presses = 0; presses < 40 && reached.length < total; presses += 1) {
            await page.keyboard.press('Tab');
            const focused = await page.evaluate(() => {
                const element = document.activeElement as HTMLElement | null;
                if (!element?.matches('#app-sidebar nav button')) return null;
                const box = element.getBoundingClientRect();
                const frame = (element.closest('nav') as HTMLElement).getBoundingClientRect();
                const style = getComputedStyle(element);
                const middle = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
                return {
                    name: (element.textContent ?? '').trim(),
                    // Scrolled wholly into the part of the sidebar that shows, and into the window.
                    inView: box.top >= frame.top - 1 && box.bottom <= frame.bottom + 1 && box.top >= 0 && box.bottom <= innerHeight,
                    onTop: middle !== null && element.contains(middle),
                    ring: style.boxShadow !== 'none' && element.matches(':focus-visible')
                };
            });
            if (!focused) continue;
            expect(focused, focused.name).toMatchObject({ inView: true, onTop: true, ring: true });
            reached.push(focused.name);
        }
        expect(reached).toHaveLength(total);
        expect(new Set(reached).size).toBe(total);
    });
}
