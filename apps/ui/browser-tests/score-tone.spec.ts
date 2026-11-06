import { test, expect, type Locator, type Page } from '@playwright/test';

// Boundary fixture: the real Explorer card, list row and record drawing the same scores, with
// the HTTP boundary supplied here. Proves one score is one colour in every view and in both
// colour themes (EXP-02), that success and warning never share a colour (NT-02), and that white
// text on a chosen fill passes WCAG AA (KIT-02). It is not backend E2E.

type Theme = 'classic' | 'bluetit';
type Mode = 'light' | 'dark';

const AMBER_500 = 'rgb(245, 158, 11)';
const SUCCESS_500 = 'rgb(16, 185, 129)';
const BRAND_500: Record<Theme, string> = { classic: 'rgb(20, 184, 166)', bluetit: 'rgb(59, 130, 246)' };

// layout-patterns §6: under 60 amber, under 85 brand, else green.
const FILL: Record<Theme, Record<string, string>> = {
    classic: { '0.55': AMBER_500, '0.62': BRAND_500.classic, '0.81': BRAND_500.classic, '0.94': SUCCESS_500 },
    bluetit: { '0.55': AMBER_500, '0.62': BRAND_500.bluetit, '0.81': BRAND_500.bluetit, '0.94': SUCCESS_500 }
};
const TEXT: Record<Mode, Record<Theme, Record<string, string>>> = {
    light: {
        classic: { '0.55': 'rgb(146, 64, 14)', '0.62': 'rgb(15, 118, 110)', '0.81': 'rgb(15, 118, 110)', '0.94': 'rgb(4, 120, 87)' },
        bluetit: { '0.55': 'rgb(146, 64, 14)', '0.62': 'rgb(29, 78, 216)', '0.81': 'rgb(29, 78, 216)', '0.94': 'rgb(4, 120, 87)' }
    },
    dark: {
        classic: { '0.55': 'rgb(252, 211, 77)', '0.62': 'rgb(94, 234, 212)', '0.81': 'rgb(94, 234, 212)', '0.94': 'rgb(110, 231, 183)' },
        bluetit: { '0.55': 'rgb(252, 211, 77)', '0.62': 'rgb(147, 197, 253)', '0.81': 'rgb(147, 197, 253)', '0.94': 'rgb(110, 231, 183)' }
    }
};
const SCORES = ['0.55', '0.62', '0.81', '0.94'];

async function open(page: Page, query = ''): Promise<string[]> {
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        }
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.goto(`/browser-tests/score-tone.html${query}`);
    await expect(page.locator('[data-surface="row"] [data-detection-score]')).toHaveCount(SCORES.length);
    return errors;
}

/** Set the colour theme and mode as the theme store does, on <html>. */
async function useTheme(page: Page, theme: Theme, mode: Mode): Promise<void> {
    await page.evaluate(([bluetit, dark]) => {
        const root = document.documentElement;
        root.classList.toggle('theme-bluetit', bluetit);
        root.classList.toggle('dark', dark);
    }, [theme === 'bluetit', mode === 'dark'] as const);
}

function css(locator: Locator, property: 'color' | 'background-color'): Promise<string> {
    return locator.evaluate((node, name) => getComputedStyle(node).getPropertyValue(name), property);
}

/** WCAG contrast of an element's text over its own background fill. */
function contrast(locator: Locator): Promise<number> {
    return locator.evaluate(node => {
        const channels = (value: string) => (value.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
        const luminance = (rgb: number[]) => {
            const [r, g, b] = rgb.map(channel => {
                const c = channel / 255;
                return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
            });
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const style = getComputedStyle(node);
        const text = luminance(channels(style.color));
        const fill = luminance(channels(style.backgroundColor));
        return (Math.max(text, fill) + 0.05) / (Math.min(text, fill) + 0.05);
    });
}

for (const theme of ['classic', 'bluetit'] as const) {
    test(`one score is one colour in the card, the list and the record (${theme})`, async ({ page }) => {
        const errors = await open(page, '?record=0.55');
        await useTheme(page, theme, 'light');
        for (const score of SCORES) {
            const dot = page.locator(`[data-surface="card"][data-score="${score}"] [data-detection-score]`);
            const text = page.locator(`[data-surface="row"][data-score="${score}"] [data-detection-score]`);
            expect(await css(dot, 'background-color'), `card ${score}`).toBe(FILL[theme][score]);
            expect(await css(text, 'color'), `row ${score}`).toBe(TEXT.light[theme][score]);
        }
        // The record's 55% "uncertain" bar is the same amber as the card's 55% dot.
        const bar = page.locator('[data-record-score-bar]');
        await expect(bar).toBeVisible();
        expect(await css(bar, 'background-color')).toBe(FILL[theme]['0.55']);

        await useTheme(page, theme, 'dark');
        for (const score of SCORES) {
            const text = page.locator(`[data-surface="row"][data-score="${score}"] [data-detection-score]`);
            expect(await css(text, 'color'), `dark row ${score}`).toBe(TEXT.dark[theme][score]);
        }
        expect(errors).toEqual([]);
    });

    test(`the record bands a confident score green (${theme})`, async ({ page }) => {
        const errors = await open(page, '?record=0.94');
        await useTheme(page, theme, 'light');
        const bar = page.locator('[data-record-score-bar]');
        await expect(bar).toBeVisible();
        expect(await css(bar, 'background-color')).toBe(SUCCESS_500);
        expect(await css(page.locator('[data-surface="card"][data-score="0.94"] [data-detection-score]'), 'background-color')).toBe(SUCCESS_500);
        expect(errors).toEqual([]);
    });

    test(`success and warning toasts differ, and white text on chosen fills passes AA (${theme})`, async ({ page }) => {
        const errors = await open(page, '?toasts=1');
        for (const mode of ['light', 'dark'] as const) {
            await useTheme(page, theme, mode);
            const success = page.locator('[data-toast-icon="success"]').locator('xpath=ancestor::div[contains(@class, "toast-card")]');
            const warning = page.locator('[data-toast-icon="warning"]').locator('xpath=ancestor::div[contains(@class, "toast-card")]');
            await expect(success).toBeVisible();
            // Success is green and warning is amber in every theme, so the two never match.
            expect(await css(success, 'background-color')).toBe('rgb(4, 120, 87)');
            expect(await css(warning, 'background-color')).toBe('rgb(180, 83, 9)');
            for (const toast of [success, warning]) expect(await contrast(toast)).toBeGreaterThanOrEqual(4.5);

            const chosen = page.locator('[data-surface="chosen"] button[aria-pressed="true"]');
            expect(await contrast(chosen), `${mode} chosen option`).toBeGreaterThanOrEqual(4.5);
            expect(await contrast(page.locator('[data-primary-button]')), `${mode} primary button`).toBeGreaterThanOrEqual(4.5);
        }
        expect(errors).toEqual([]);
    });
}
