import { expect, test } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// Settings → Enrichment shows which provider fills each part of a species page. It loads only
// when opened, never counts as an edit, and every save sends the stored providers back.

const SAVED_PROVIDERS = {
    enrichment_mode: 'per_enrichment',
    enrichment_summary_source: 'inaturalist',
    enrichment_taxonomy_source: 'inaturalist',
    enrichment_sightings_source: 'ebird',
    enrichment_seasonality_source: 'disabled',
    enrichment_rarity_source: 'ebird',
    enrichment_links_sources: ['ebird', 'wikipedia']
};

test('Enrichment loads on first open, shows the stored providers and saves them back unchanged', async ({ page }) => {
    const harness = await openSettings(page, SAVED_PROVIDERS);
    expect(harness.moduleRequests('EnrichmentSettings.svelte')).toBe(0);

    await page.getByRole('link', { name: 'Enrichment' }).click();
    const sightings = page.getByText('Nearby Sightings', { exact: true }).locator('..');
    await expect(sightings).toContainText('eBird');
    expect(harness.moduleRequests('EnrichmentSettings.svelte')).toBe(1);
    await expect(page.getByText('Unsaved Changes', { exact: true })).toHaveCount(0);

    await page.getByRole('link', { name: 'Connection' }).click();
    await page.locator('#mqtt-server').fill('mqtt-broker');
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ ...SAVED_PROVIDERS, enrichment_single_provider: 'wikipedia' });
});
