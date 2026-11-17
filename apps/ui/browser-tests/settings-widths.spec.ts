import { expect, test, type Page } from '@playwright/test';

// Settings uses the screen it has (M9): at every width no sideways scroll and no line of text
// longer than a comfortable measure; the section list beside the settings from 1024 px; from
// 1440 px the status and the section's parts in a column of their own; and at 1920 px the page's
// columns fill most of the window instead of one narrow strip.

const SECTIONS = ['cameras', 'identification', 'alerts', 'sharing', 'storage', 'display'] as const;
const WIDTHS = [390, 768, 1024, 1440, 1920] as const;
/** About 70ch is the aim; no line may pass 80ch. */
const MAX_LINE_CH = 80;

async function openOwnerShell(page: Page): Promise<string[]> {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, cameras: ['patio'], classification_threshold: 0.7 },
            '/api/update-status': { update_available: false }
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in the settings width fixture' } });
    });
    await page.route((url) => url.pathname === '/health', (route) => route.fulfill({ json: { status: 'healthy' } }));
    return errors;
}

interface Measure {
    overflow: number;
    longLines: string[];
    rail: { right: number; visible: boolean } | null;
    main: { left: number; right: number };
    aside: { left: number; top: number; afterMain: boolean } | null;
    used: number;
    /** List rows (each item of a divided list) narrower than their list, and how many were measured. */
    shortRows: string[];
    rows: number;
}

function measure(page: Page): Promise<Measure> {
    return page.evaluate((maxCh) => {
        const layout = document.querySelector('[data-settings-layout]') as HTMLElement;
        const main = layout.querySelector('.settings-layout-main') as HTMLElement;
        const railNav = document.querySelector('[data-settings-navigation]') as HTMLElement | null;
        // The status is in the page twice, before the settings for a phone and after them for a
        // column beside them; only one is shown.
        const aside = [...layout.querySelectorAll<HTMLElement>('[data-settings-aside]')].find((each) => each.getBoundingClientRect().width > 0) ?? null;
        const canvas = document.createElement('canvas').getContext('2d') as CanvasRenderingContext2D;
        const longLines: string[] = [];
        const walker = document.createTreeWalker(layout, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const text = node.textContent?.trim() ?? '';
            const parent = node.parentElement;
            if (text.length < 20 || !parent || parent.closest('[aria-hidden="true"], .sr-only')) continue;
            const style = getComputedStyle(parent);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            canvas.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
            const ch = canvas.measureText('0').width;
            const range = document.createRange();
            range.selectNodeContents(node);
            for (const line of range.getClientRects()) {
                if (line.width > ch * maxCh) longLines.push(`${Math.round(line.width / ch)}ch: ${text.slice(0, 60)}`);
            }
        }
        const shortRows: string[] = [];
        let rows = 0;
        for (const list of layout.querySelectorAll<HTMLElement>('[data-settings-content] :is(ul, ol)[class*="divide-y"]')) {
            const style = getComputedStyle(list);
            const inner = list.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
            for (const item of list.children) {
                const box = item.getBoundingClientRect();
                if (box.width === 0) continue;
                rows += 1;
                if (box.width < inner - 1) shortRows.push(`${Math.round(box.width)} of ${Math.round(inner)} px: ${(item.textContent ?? '').trim().slice(0, 40)}`);
            }
        }
        const children = [...layout.children].map((child) => child.getBoundingClientRect()).filter((box) => box.width > 0);
        const used = Math.max(...children.map((box) => box.right)) - Math.min(...children.map((box) => box.left));
        const railBox = railNav?.getBoundingClientRect();
        const mainBox = main.getBoundingClientRect();
        const asideBox = aside?.getBoundingClientRect();
        return {
            overflow: document.documentElement.scrollWidth - window.innerWidth,
            longLines: [...new Set(longLines)].slice(0, 10),
            rail: railBox ? { right: railBox.right, visible: railBox.width > 0 } : null,
            main: { left: mainBox.left, right: mainBox.right },
            aside: asideBox && aside ? { left: asideBox.left, top: asideBox.top, afterMain: Boolean(main.compareDocumentPosition(aside) & Node.DOCUMENT_POSITION_FOLLOWING) } : null,
            used,
            shortRows: shortRows.slice(0, 10),
            rows
        };
    }, MAX_LINE_CH);
}

for (const width of WIDTHS) {
    test.describe(`at ${width} px`, () => {
        test.use({ viewport: { width, height: 900 } });

        test('every section fits the window, keeps a readable measure, and uses the width it has', async ({ page }) => {
            const errors = await openOwnerShell(page);
            let rows = 0;
            for (const section of SECTIONS) {
                await page.goto(`/settings/${section}`);
                await expect(page.locator('[data-settings-content]')).toBeVisible({ timeout: 15_000 });
                await expect(page.locator('[data-settings-section-status]:visible')).toHaveCount(1);
                await page.waitForTimeout(400);
                const found = await measure(page);
                expect(found.overflow, `${section}: sideways scroll`).toBeLessThanOrEqual(1);
                expect(found.longLines, `${section}: lines over ${MAX_LINE_CH}ch`).toEqual([]);
                // The measure is for sentences: a row of a divided list keeps its list's width, so
                // its divider and the value at its right edge reach the card's edge.
                expect(found.shortRows, `${section}: list rows cut short`).toEqual([]);
                rows += found.rows;
                if (width >= 1024) {
                    // The section list sits beside the settings, not above them.
                    expect(found.rail?.visible, `${section}: section list`).toBe(true);
                    expect(found.rail?.right ?? Infinity, `${section}: section list beside`).toBeLessThanOrEqual(found.main.left);
                }
                if (width >= 1440) {
                    // Status and parts take a column of their own beside the settings.
                    expect(found.aside?.left ?? 0, `${section}: status column beside`).toBeGreaterThanOrEqual(found.main.right);
                    // The keyboard reaches it after the settings, in the order it is seen.
                    expect(found.aside?.afterMain, `${section}: status column after the settings`).toBe(true);
                }
                if (width >= 1920) {
                    expect(found.used / width, `${section}: share of the window used`).toBeGreaterThanOrEqual(0.7);
                }
                if (width < 1024) {
                    // On a phone or tablet the status comes before the settings, never beside them.
                    expect(found.aside?.left ?? 0, `${section}: status above the settings`).toBeLessThan(found.main.right);
                    expect(found.aside?.afterMain, `${section}: status before the settings`).toBe(false);
                }
            }
            // Some divided lists were on these pages, so the row check above measured something.
            expect(rows).toBeGreaterThan(0);
            expect(errors).toEqual([]);
        });
    });
}
