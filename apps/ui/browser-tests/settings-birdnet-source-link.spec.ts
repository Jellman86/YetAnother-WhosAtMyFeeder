import { expect, test, type Page } from '@playwright/test';
import { openSettings, saveButton } from './settings-page-mock';

// A camera linked to a BirdNET-Go source by name loses it when the source is renamed (#1111).
// Settings links by stream ID: the picker saves the ID, a linked ID reads as the stream's current
// name, and a camera still linked by an old name offers the swap, which only takes effect on save.

const RENAMED_SOURCES = [
    {
        source_name: 'ESP32 v3.0 X',
        mapping_value: 'rtsp_52d54d7d',
        source_id: 'rtsp_52d54d7d',
        earlier_names: [{ name: 'ESP32 v3.0', last_seen: '2026-11-27T09:00:00Z', has_calls_without_id: false }],
        last_seen: '2026-11-28T08:00:00Z',
        seen_count: 812
    },
    {
        source_name: 'Reolink TEST',
        mapping_value: 'rtsp_68763a4d',
        source_id: 'rtsp_68763a4d',
        earlier_names: [{ name: 'Reolink', last_seen: '2026-11-12T09:00:00Z', has_calls_without_id: true }],
        last_seen: '2026-11-28T07:30:00Z',
        seen_count: 4078
    },
    {
        source_name: 'ESP32 v2.4',
        mapping_value: 'rtsp_47526eb4',
        source_id: 'rtsp_47526eb4',
        earlier_names: [],
        last_seen: '2026-11-28T08:10:00Z',
        seen_count: 1520
    }
];

async function openBirdnetMapping(page: Page, mapping: Record<string, string>) {
    const harness = await openSettings(
        page,
        { birdnet_enabled: true, audio_topic: 'birdnet/text', cameras: ['birdcam'], camera_audio_mapping: mapping },
        {
            route: '/settings/integrations',
            respond: (path) => {
                if (path.endsWith('/audio/sources')) return { json: RENAMED_SOURCES };
                if (path.endsWith('/frigate/config')) return { json: { cameras: { birdcam: {} } } };
                return undefined;
            }
        }
    );
    await page.getByRole('button', { name: 'Audio buffer & sensor mapping' }).click();
    await expect(page.getByLabel('BirdNET source name for birdcam')).toBeVisible();
    return harness;
}

const mappingInput = (page: Page) => page.getByLabel('BirdNET source name for birdcam');
const tokens = (page: Page) => page.getByLabel('Mapped BirdNET sources for birdcam').locator('[data-audio-link-token]');

test('a camera linked by a renamed source\'s old name is offered the stream ID, saved only on Save', async ({ page }) => {
    const harness = await openBirdnetMapping(page, { birdcam: 'ESP32 v3.0, ESP32 v2.4' });

    const notice = page.locator('[data-audio-link-renamed]');
    await expect(notice).toHaveCount(1);
    await expect(notice).toContainText('ESP32 v3.0 is now called ESP32 v3.0 X.');
    // The old name is shown as typed, with when a call last carried it, as a fact.
    await expect(tokens(page).first()).toContainText('ESP32 v3.0');
    await expect(tokens(page).first()).toContainText('Last heard');

    await notice.getByRole('button', { name: 'Link birdcam to ESP32 v3.0 X by stream ID rtsp_52d54d7d' }).click();
    await expect(notice).toHaveCount(0);
    await expect(mappingInput(page)).toHaveValue('rtsp_52d54d7d, ESP32 v2.4');
    await expect(tokens(page).first()).toContainText('ESP32 v3.0 X · rtsp_52d54d7d');
    expect(harness.writes).toHaveLength(0);

    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0].camera_audio_mapping).toEqual({ birdcam: 'rtsp_52d54d7d, ESP32 v2.4' });
});

test('the swap keeps an old name that calls from before stream IDs still match', async ({ page }) => {
    await openBirdnetMapping(page, { birdcam: 'Reolink' });
    await page.locator('[data-audio-link-renamed]').getByRole('button', { name: /by stream ID/ }).click();
    await expect(mappingInput(page)).toHaveValue('Reolink, rtsp_68763a4d');
    await expect(page.locator('[data-audio-link-renamed]')).toHaveCount(0);
});

test('the picker and the detected list save a stream by its ID and show it by its current name', async ({ page }) => {
    await openBirdnetMapping(page, { birdcam: 'Shed mic' });
    await page.getByLabel('Add detected BirdNET source for birdcam').selectOption({ label: 'Reolink TEST · rtsp_68763a4d' });
    await expect(mappingInput(page)).toHaveValue('Shed mic, rtsp_68763a4d');
    // A hand-typed name no stream carries is shown verbatim, with no time.
    await expect(tokens(page).first()).toHaveText(/^\s*Shed mic\s*×\s*$/);
    await expect(tokens(page).nth(1)).toContainText('Reolink TEST · rtsp_68763a4d');

    await page.getByRole('button', { name: /^ESP32 v2\.4/ }).click();
    await expect(mappingInput(page)).toHaveValue('Shed mic, rtsp_68763a4d, rtsp_47526eb4');
    await expect(page.locator('[data-audio-link-renamed]')).toHaveCount(0);
});
