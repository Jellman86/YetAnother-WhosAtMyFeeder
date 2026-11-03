import { expect, test } from '@playwright/test';
import { openSettings, unsavedChanges } from './settings-page-mock';

// Settings → AI keeps its fields in the one Settings draft and loads its tab body, with the
// built-in prompt templates, only when opened. Apply saves it with the rest of the form.

test('AI loads on first open, follows a provider switch and saves with Apply', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const harness = await openSettings(page, {
        llm_enabled: true,
        llm_provider: 'gemini',
        llm_api_key: '***REDACTED***',
        llm_model: 'gemini-3.1-pro-preview'
    });
    expect(harness.moduleRequests('AISettings.svelte')).toBe(0);
    expect(harness.moduleRequests('llm-prompt-templates.ts')).toBe(0);

    await page.getByRole('link', { name: 'AI', exact: true }).click();
    const model = page.locator('#llm-model');
    await expect(model).toHaveValue('gemini-3.1-pro-preview');
    expect(harness.moduleRequests('AISettings.svelte')).toBe(1);
    await expect(page.locator('#llm-api-key')).toHaveValue('');
    await expect(unsavedChanges(page)).toHaveCount(0);

    await page.getByRole('button', { name: 'Claude', exact: true }).click();
    await expect(model).toHaveValue('claude-opus-4-8');
    await expect(unsavedChanges(page)).toBeVisible();

    await page.getByRole('button', { name: /Pricing & prompt templates/ }).click();
    await page.getByRole('button', { name: 'Apply Style', exact: true }).click();
    await expect(page.locator('#llm-prompt-analysis')).toHaveValue(/ornithologist/);

    await page.getByRole('link', { name: 'Connection' }).click();
    await expect(page.locator('#mqtt-server')).toBeVisible();
    await page.getByRole('link', { name: 'AI', exact: true }).click();
    await expect(model).toHaveValue('claude-opus-4-8');

    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({
        llm_enabled: true,
        llm_provider: 'claude',
        llm_model: 'claude-opus-4-8',
        llm_api_key: ''
    });
    expect(String(harness.writes[0].llm_analysis_prompt_template)).toContain('ornithologist');
    await expect(unsavedChanges(page)).toHaveCount(0);
    expect(errors).toEqual([]);
});
