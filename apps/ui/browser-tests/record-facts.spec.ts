import { expect, test, type Page } from '@playwright/test';

/**
 * The record's facts on a phone: a value too long for the label's line starts under the label text,
 * as a column, and a figure keeps its unit on its own line.
 */
async function openRecord(page: Page): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="3"/>' });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/browser-tests/modal-text-layout.html?light=471&wind=true');
    await expect(page.locator('[data-detection-weather-row]')).toBeVisible({ timeout: 15_000 });
}

test('on a phone the Conditions value starts level with its label, and a unit stays with its figure', async ({ page }) => {
    await openRecord(page);
    const measured = await page.locator('[data-detection-weather-row]').evaluate((row) => {
        const label = row.querySelector('dt');
        const value = row.querySelector('dd');
        if (!label || !value) throw new Error('Conditions row is incomplete');
        const words = [...label.childNodes].find((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim());
        if (!words) throw new Error('Conditions label has no words');
        const labelRange = document.createRange();
        labelRange.selectNodeContents(words);
        const labelStart = [...labelRange.getClientRects()].find((rect) => rect.width > 0)?.left ?? NaN;
        const valueRange = document.createRange();
        valueRange.selectNodeContents(value);
        const lines = [...valueRange.getClientRects()].filter((rect) => rect.width > 0);
        const text = value.textContent ?? '';
        const node = [...value.childNodes].find((child) => child.nodeType === Node.TEXT_NODE && child.textContent?.includes('lx'));
        let unitLines = 0;
        if (node?.textContent) {
            const at = node.textContent.indexOf('471');
            const unit = document.createRange();
            unit.setStart(node, at);
            unit.setEnd(node, node.textContent.indexOf('lx', at) + 2);
            unitLines = new Set([...unit.getClientRects()].filter((rect) => rect.width > 0).map((rect) => Math.round(rect.top))).size;
        }
        return { labelStart, valueStart: Math.min(...lines.map((rect) => rect.left)), lines: new Set(lines.map((rect) => Math.round(rect.top))).size, text, unitLines };
    });
    expect(measured.text).toContain('471');
    expect(measured.lines, 'the value wraps at 390 px, which is the case being checked').toBeGreaterThan(1);
    expect(Math.abs(measured.valueStart - measured.labelStart)).toBeLessThanOrEqual(1);
    expect(measured.unitLines).toBe(1);
});
