import { expect, test, type Page } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// Settings → AI shows a dollar amount only for usage that has a price. A model with no price is
// "not priced", a total over part of the usage says what it covers, and usage with no prices at
// all is "Cost not estimated: add prices", never a measured-looking zero.
test.use({ viewport: { width: 1440, height: 900 } });

const row = (provider: string, model: string, calls: number, cost: number | null) => ({
    provider, model, feature: 'analysis', calls, input_tokens: calls * 1000, output_tokens: calls * 100,
    total_tokens: calls * 1100, estimated_cost_usd: cost, priced: cost !== null
});

async function openUsage(page: Page, usage: Record<string, unknown>): Promise<void> {
    await openSettings(page, { llm_enabled: true, llm_provider: 'gemini', llm_api_key: '***REDACTED***', llm_model: 'gemini-3.1-pro-preview' }, {
        respond: (path) => (path === '/api/stats/ai/usage'
            ? { json: { span: '30d', from_date: '2026-10-17T00:00:00', to_date: '2026-11-16T00:00:00', input_tokens: 5000, output_tokens: 500, total_tokens: 5500, daily: [], ...usage } }
            : undefined)
    });
    await page.getByRole('link', { name: 'AI', exact: true }).click();
    await page.getByRole('button', { name: /AI usage dashboard/ }).click();
}

test('usage with no prices says the cost is not estimated, and names the models to price', async ({ page }, testInfo) => {
    await openUsage(page, {
        calls: 5, estimated_cost_usd: null, pricing_configured: false, priced_calls: 0, unpriced_calls: 5,
        unpriced_models: ['gemini/gemini-3.1-pro-preview'], breakdown: [row('gemini', 'gemini-3.1-pro-preview', 5, null)]
    });
    const cost = page.locator('[data-ai-cost]');
    await expect(cost).toHaveAttribute('data-ai-cost', 'not_estimated');
    await expect(cost).toHaveText('Cost not estimated: add prices');
    await expect(page.locator('[data-ai-cost-coverage]')).toHaveText('No price is set for gemini/gemini-3.1-pro-preview. Add one under Pricing and prompt templates.');
    await expect(page.locator('[data-ai-cost-row]')).toHaveText('Not priced');
    // No currency amount anywhere in the usage panel.
    await expect(page.locator('[data-ai-cost]').locator('xpath=ancestor::div[1]')).not.toContainText('$');
    await cost.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('ai-cost-not-estimated.png') });
});

test('a total over part of the usage states what it covers and what it leaves out', async ({ page }, testInfo) => {
    await openUsage(page, {
        calls: 5, estimated_cost_usd: 0.3, pricing_configured: true, priced_calls: 2, unpriced_calls: 3,
        unpriced_models: ['claude/claude-opus-4-8'],
        breakdown: [row('gemini', 'gemini-3.1-pro-preview', 2, 0.3), row('claude', 'claude-opus-4-8', 3, null)]
    });
    await expect(page.locator('[data-ai-cost]')).toContainText('$0.30');
    await expect(page.locator('[data-ai-cost-coverage]')).toHaveText('Covers 2 of 5 requests. Not priced, so not included: claude/claude-opus-4-8.');
    await expect(page.locator('[data-ai-cost-row="priced"]')).toHaveText('$0.30');
    await expect(page.locator('[data-ai-cost-row="not_priced"]')).toHaveText('Not priced');
    await page.locator('[data-ai-cost]').scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('ai-cost-partial.png') });
});

test('fully priced usage gives its total for all requests', async ({ page }) => {
    await openUsage(page, {
        calls: 2, estimated_cost_usd: 0.004, pricing_configured: true, priced_calls: 2, unpriced_calls: 0,
        unpriced_models: [], breakdown: [row('gemini', 'gemini-3.1-pro-preview', 2, 0.004)]
    });
    await expect(page.locator('[data-ai-cost]')).toContainText('< $0.01');
    await expect(page.locator('[data-ai-cost-coverage]')).toHaveText('Covers all 2 requests.');
});
