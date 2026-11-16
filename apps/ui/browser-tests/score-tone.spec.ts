import { test, expect, type Locator, type Page } from '@playwright/test';

// Boundary fixture: the real Explorer card, list row and record drawing the same scores, with
// the HTTP boundary supplied here. Proves one score is one colour in every view and in both
// colour themes (EXP-02), that success and warning never share a colour (NT-02), and that white
// text on a chosen fill passes WCAG AA (KIT-02). It is not backend E2E.

type Theme = 'classic' | 'bluetit';
type Mode = 'light' | 'dark';

// A score's dot and bar are its status tone's edge colour (app.css, `--status-*-line`): 3:1 on
// every ground, the same colour in the card, the list and the record.
const ATTENTION_LINE = 'rgb(180, 83, 9)';
const OK_LINE = 'rgb(5, 150, 105)';
const INFO_LINE: Record<Theme, string> = { classic: 'rgb(13, 148, 136)', bluetit: 'rgb(37, 99, 235)' };

// layout-patterns §6: under 60 amber, under 85 brand, else green.
const FILL: Record<Theme, Record<string, string>> = {
    classic: { '0.55': ATTENTION_LINE, '0.62': INFO_LINE.classic, '0.81': INFO_LINE.classic, '0.94': OK_LINE },
    bluetit: { '0.55': ATTENTION_LINE, '0.62': INFO_LINE.bluetit, '0.81': INFO_LINE.bluetit, '0.94': OK_LINE }
};
const TEXT: Record<Mode, Record<Theme, Record<string, string>>> = {
    light: {
        classic: { '0.55': 'rgb(146, 64, 14)', '0.62': 'rgb(15, 118, 110)', '0.81': 'rgb(15, 118, 110)', '0.94': 'rgb(4, 120, 87)' },
        bluetit: { '0.55': 'rgb(146, 64, 14)', '0.62': 'rgb(29, 78, 216)', '0.81': 'rgb(29, 78, 216)', '0.94': 'rgb(4, 120, 87)' }
    },
    dark: {
        classic: { '0.55': 'rgb(253, 230, 138)', '0.62': 'rgb(94, 234, 212)', '0.81': 'rgb(94, 234, 212)', '0.94': 'rgb(110, 231, 183)' },
        bluetit: { '0.55': 'rgb(253, 230, 138)', '0.62': 'rgb(147, 197, 253)', '0.81': 'rgb(147, 197, 253)', '0.94': 'rgb(110, 231, 183)' }
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
        // Measure the settled colours, not a colour transition caught half way.
        if (!document.getElementById('no-transitions')) {
            const style = document.createElement('style');
            style.id = 'no-transitions';
            style.textContent = '*, *::before, *::after { transition: none !important; }';
            document.head.append(style);
        }
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
        // Any CSS colour (rgb, oklch from Tailwind's palette) is painted on a canvas and read back as sRGB.
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        const paint = canvas.getContext('2d', { willReadFrequently: true });
        const channels = (value: string) => {
            if (!paint) throw new Error('No 2D canvas');
            paint.clearRect(0, 0, 1, 1);
            paint.fillStyle = value;
            paint.fillRect(0, 0, 1, 1);
            return [...paint.getImageData(0, 0, 1, 1).data.slice(0, 3)];
        };
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
        expect(await css(bar, 'background-color')).toBe(OK_LINE);
        expect(await css(page.locator('[data-surface="card"][data-score="0.94"] [data-detection-score]'), 'background-color')).toBe(OK_LINE);
        expect(errors).toEqual([]);
    });

    test(`success and warning toasts differ, and the chosen option and primary button read at AA (${theme})`, async ({ page }) => {
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
