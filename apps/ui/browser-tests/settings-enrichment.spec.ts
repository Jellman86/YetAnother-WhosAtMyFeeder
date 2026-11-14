import { expect, test } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// Integrations ends with which provider fills each part of a species page. It loads with that tab,
// never counts as an edit, and every save sends the stored providers back.

const SAVED_PROVIDERS = {
    enrichment_mode: 'per_enrichment',
    enrichment_summary_source: 'inaturalist',
    enrichment_taxonomy_source: 'inaturalist',
    enrichment_sightings_source: 'ebird',
    enrichment_seasonality_source: 'disabled',
    enrichment_rarity_source: 'ebird',
    enrichment_links_sources: ['ebird', 'wikipedia']
};

test('the species information sources load with Integrations, show the stored providers and save them back unchanged', async ({ page }) => {
    const harness = await openSettings(page, SAVED_PROVIDERS);
    expect(harness.moduleRequests('EnrichmentSettings.svelte')).toBe(0);

    await page.locator('[data-settings-navigation]').getByRole('link', { name: 'Integrations', exact: true }).click();
    const sightings = page.locator('[data-enrichment-summary] div').filter({ hasText: 'Nearby sightings' });
    await expect(sightings).toContainText('eBird');
    expect(harness.moduleRequests('EnrichmentSettings.svelte')).toBe(1);
    await expect(page.getByRole('region', { name: 'Unsaved changes' })).toHaveCount(0);

    await page.getByRole('link', { name: 'Connection' }).click();
    await page.locator('#mqtt-server').fill('mqtt-broker');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ ...SAVED_PROVIDERS, enrichment_single_provider: 'wikipedia' });
});
