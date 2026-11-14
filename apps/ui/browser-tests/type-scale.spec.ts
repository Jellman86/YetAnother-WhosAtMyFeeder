import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The type scale as a browser draws it, not as a formula says it should be: the size of every
 * kit step is read off rendered text, at each Appearance text size and at the browser's own text
 * size set to its default and to twice that.
 */

/** Appearance text sizes, smallest first, as `text_size` stores them. */
const APPEARANCE_STEPS = ['smallest', 'smaller', 'standard', 'large', 'larger', 'extra_large', 'largest'] as const;
/** Kit steps, smallest first. `body` is text with no step of its own. */
const KIT_STEPS = ['text-3xs', 'text-2xs', 'text-xs', 'text-sm', 'body', 'text-base', 'text-lg', 'text-xl', 'text-2xl'] as const;
type KitStep = (typeof KIT_STEPS)[number];
type Drawn = Record<KitStep, number>;

const BROWSER_DEFAULT_PX = 16;
const SMALLEST_LEGIBLE_PX = 12;
/** A step up has to be seen, not only computed. */
const VISIBLE_STEP_PX = 0.3;

// The window is 1280px wide, where the root size is the browser's own with no large-display bump.
test.use({ viewport: { width: 1280, height: 800 } });
test.skip(({ browserName }) => browserName !== 'chromium', 'The browser text size is set through Chromium.');

/** The reader's text size in the browser's own settings, which is what a percentage root follows. */
async function setBrowserTextSize(page: Page, pixels: number): Promise<void> {
    const session = await page.context().newCDPSession(page);
    await session.send('Page.setFontSizes', { fontSizes: { standard: pixels } });
}

async function openAt(page: Page, step: string, browserPx: number): Promise<void> {
    await replayFeeder(page, 'light');
    await page.addInitScript((chosen) => localStorage.setItem('text_size', chosen), step);
    await setBrowserTextSize(page, browserPx);
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 });
    await settled(page);
}

/** The rendered size of a line of text set at each kit step. */
async function drawnSizes(page: Page): Promise<Drawn> {
    return page.evaluate((steps) => {
        const host = document.createElement('div');
        document.querySelector('#main-content')?.append(host);
        const sizes: Record<string, number> = {};
        for (const step of steps) {
            const line = document.createElement('p');
            if (step !== 'body') line.className = step;
            line.textContent = 'Eurasian Blue Tit';
            host.append(line);
            sizes[step] = parseFloat(getComputedStyle(line).fontSize);
        }
        host.remove();
        return sizes;
    }, KIT_STEPS) as Promise<Drawn>;
}

/** The smallest size any words on the page are drawn at. */
async function smallestTextOnThePage(page: Page): Promise<{ size: number; text: string }> {
    return page.evaluate(() => {
        let smallest = { size: Infinity, text: '' };
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const owner = node.parentElement;
            if (!owner || !node.textContent?.trim() || owner.closest('script, style, noscript, .sr-only')) continue;
            if (!owner.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
            const size = parseFloat(getComputedStyle(owner).fontSize);
            if (size < smallest.size) smallest = { size, text: node.textContent.trim().slice(0, 40) };
        }
        return smallest;
    });
}

const drawnAt = new Map<string, Drawn>();
async function measured(page: Page, step: string, browserPx: number): Promise<Drawn> {
    const key = `${step}@${browserPx}`;
    const known = drawnAt.get(key);
    if (known) return known;
    await openAt(page, step, browserPx);
    const sizes = await drawnSizes(page);
    drawnAt.set(key, sizes);
    return sizes;
}

for (const step of APPEARANCE_STEPS) {
    test(`at the ${step} text size nothing is under 12px and each kit step is larger than the one below`, async ({ page }) => {
        const sizes = await measured(page, step, BROWSER_DEFAULT_PX);
        for (const kitStep of KIT_STEPS) expect(sizes[kitStep], kitStep).toBeGreaterThanOrEqual(SMALLEST_LEGIBLE_PX - 0.01);
        expect((await smallestTextOnThePage(page)).size).toBeGreaterThanOrEqual(SMALLEST_LEGIBLE_PX - 0.01);
        // Hierarchy by size holds at every step: small print, secondary text and normal text are
        // three sizes, and headings are larger again.
        const ladder: KitStep[] = ['text-xs', 'text-sm', 'body', 'text-lg', 'text-xl', 'text-2xl'];
        for (let rung = 1; rung < ladder.length; rung += 1) {
            expect(sizes[ladder[rung]] - sizes[ladder[rung - 1]], `${ladder[rung]} over ${ladder[rung - 1]}`).toBeGreaterThanOrEqual(VISIBLE_STEP_PX);
        }
        // The two finest steps may meet on the floor, but never invert.
        expect(sizes['text-xs']).toBeGreaterThanOrEqual(sizes['text-2xs']);
        expect(sizes['text-2xs']).toBeGreaterThanOrEqual(sizes['text-3xs']);
        expect(sizes['text-base']).toBe(sizes.body);
    });

    test(`at the ${step} text size every kit step doubles when the browser text size doubles`, async ({ page }) => {
        const normal = await measured(page, step, BROWSER_DEFAULT_PX);
        const doubled = await measured(page, step, BROWSER_DEFAULT_PX * 2);
        for (const kitStep of KIT_STEPS) {
            expect(doubled[kitStep] / normal[kitStep], kitStep).toBeGreaterThan(1.98);
            expect(doubled[kitStep] / normal[kitStep], kitStep).toBeLessThan(2.02);
        }
    });
}

test('every kit step grows with each Appearance text size, so no setting leaves text as it was', async ({ page }) => {
    for (const browserPx of [BROWSER_DEFAULT_PX, BROWSER_DEFAULT_PX * 2]) {
        let below: Drawn | null = null;
        let belowStep = '';
        for (const step of APPEARANCE_STEPS) {
            const sizes = await measured(page, step, browserPx);
            if (below) {
                for (const kitStep of KIT_STEPS) {
                    expect(sizes[kitStep] - below[kitStep], `${kitStep} from ${belowStep} to ${step} at a ${browserPx}px browser size`).toBeGreaterThanOrEqual(VISIBLE_STEP_PX * (browserPx / BROWSER_DEFAULT_PX));
                }
            }
            below = sizes;
            belowStep = step;
        }
    }
});
