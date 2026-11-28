import { expect, test, type Page } from '@playwright/test';
import { openSettings, saveButton } from './settings-page-mock';

// A camera linked to a BirdNET-Go source by name loses it when the source is renamed (#1111).
// Settings links by stream ID: the picker saves the ID, a linked ID reads as the stream's current
// name, and a camera still linked by an old name offers to add the ID, which only takes effect on save.

type Source = {
    source_name: string;
    mapping_value: string;
    source_id: string | null;
    source_node: string | null;
    installs_sharing_id: string[];
    last_seen: string;
    names: Array<{ name: string; last_seen: string | null; current: boolean; offer_link_by_id: boolean }>;
};

function stream(name: string, id: string, lastSeen: string, earlier: Source['names'] = [], node = 'BirdNET-Go', sharing: string[] = []): Source {
    return {
        source_name: name,
        mapping_value: id,
        source_id: id,
        source_node: node,
        installs_sharing_id: sharing,
        last_seen: lastSeen,
        names: [{ name, last_seen: lastSeen, current: true, offer_link_by_id: false }, ...earlier]
    };
}

const RENAMED_SOURCES: Source[] = [
    stream('ESP32 v2.4', 'rtsp_47526eb4', '2026-11-28T08:10:00Z'),
    stream('ESP32 v3.0 X', 'rtsp_52d54d7d', '2026-11-28T08:00:00Z', [
        { name: 'ESP32 v3.0', last_seen: '2026-11-27T09:00:00Z', current: false, offer_link_by_id: true }
    ]),
    stream('Reolink TEST', 'rtsp_68763a4d', '2026-11-28T07:30:00Z', [
        { name: 'Reolink', last_seen: '2026-11-12T09:00:00Z', current: false, offer_link_by_id: true }
    ])
];

async function openBirdnetMapping(page: Page, mapping: Record<string, string>, sources: Source[] = RENAMED_SOURCES) {
    const limits: string[] = [];
    page.on('request', (request) => {
        const url = new URL(request.url());
        if (url.pathname.endsWith('/audio/sources')) limits.push(url.searchParams.get('limit') ?? '');
    });
    const harness = await openSettings(
        page,
        { birdnet_enabled: true, audio_topic: 'birdnet/text', camera_audio_mapping: mapping },
        {
            route: '/settings/integrations',
            respond: (path) => {
                if (path.endsWith('/audio/sources')) return { json: sources };
                if (path.endsWith('/frigate/config')) return { json: { cameras: { birdcam: {} } } };
                return undefined;
            }
        }
    );
    await page.getByRole('button', { name: 'Audio buffer & sensor mapping' }).click();
    await expect(mappingInput(page)).toBeVisible();
    // Every stream is asked for, so a linked source resolves on any realistic install.
    expect(limits).toContain('100');
    return harness;
}

const mappingInput = (page: Page) => page.getByLabel('BirdNET source name for birdcam');
const links = (page: Page) => page.getByLabel('Mapped BirdNET sources for birdcam').locator('[data-audio-link-token]');

test('a camera linked by a renamed source\'s old name is offered the stream ID, added only on Save', async ({ page }) => {
    const harness = await openBirdnetMapping(page, { birdcam: 'ESP32 v3.0, ESP32 v2.4' });

    const notice = page.locator('[data-audio-link-renamed]');
    await expect(notice).toHaveCount(1);
    await expect(notice).toContainText('ESP32 v3.0 is now called ESP32 v3.0 X.');
    // The old name is shown as typed, with when a call last carried it, as a fact.
    await expect(links(page).first()).toContainText('ESP32 v3.0');
    await expect(links(page).first()).toContainText('Last heard');

    // The button's name starts with what it says, then its context.
    await notice.getByRole('button', { name: 'Link by stream ID rtsp_52d54d7d for birdcam' }).click();
    await expect(notice).toHaveCount(0);
    await expect(mappingInput(page)).toHaveValue('ESP32 v3.0, rtsp_52d54d7d, ESP32 v2.4');
    await expect(links(page).nth(1)).toContainText('ESP32 v3.0 X');
    await expect(links(page).nth(1)).toContainText('rtsp_52d54d7d');
    // Focus lands on the link that was added, never on the page.
    await expect(page.getByRole('button', { name: 'Remove ESP32 v3.0 X from birdcam' })).toBeFocused();
    expect(harness.writes).toHaveLength(0);

    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0].camera_audio_mapping).toEqual({ birdcam: 'ESP32 v3.0, rtsp_52d54d7d, ESP32 v2.4' });
});

test('the picker and the detected list save a stream by its ID and show it by its current name', async ({ page }) => {
    await openBirdnetMapping(page, { birdcam: 'Shed mic' });
    await page.getByLabel('Add detected BirdNET source for birdcam').selectOption({ label: 'Reolink TEST · rtsp_68763a4d' });
    await expect(mappingInput(page)).toHaveValue('Shed mic, rtsp_68763a4d');
    // A hand-typed name no stream carries is shown verbatim, with no time.
    await expect(links(page).first()).toHaveText(/^\s*Shed mic\s*×\s*$/);
    await expect(links(page).nth(1)).toContainText('Reolink TEST');
    await expect(links(page).nth(1)).toContainText('rtsp_68763a4d');

    await page.getByRole('button', { name: /^ESP32 v2\.4/ }).click();
    await expect(mappingInput(page)).toHaveValue('Shed mic, rtsp_68763a4d, rtsp_47526eb4');
    await expect(page.locator('[data-audio-link-renamed]')).toHaveCount(0);

    // The remove control is at least 24 px square.
    const box = await page.getByRole('button', { name: 'Remove Reolink TEST from birdcam' }).boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(24);
    expect(box?.height).toBeGreaterThanOrEqual(24);
});

test('two installs sending the same stream ID are told apart by install', async ({ page }) => {
    const card = 'audio_card_22a9b331';
    await openBirdnetMapping(page, { birdcam: card }, [
        stream('House Mic', card, '2026-11-28T09:00:00Z', [], 'House', ['House', 'Shed']),
        stream('Shed Mic', card, '2026-11-28T08:00:00Z', [], 'Shed', ['House', 'Shed'])
    ]);
    await expect(links(page).first()).toContainText('House Mic, Shed Mic');
    // The installs sit on their own line, never after a dot that could wrap away from them.
    await expect(links(page).first().getByText('House, Shed', { exact: true })).toBeVisible();
    await expect(links(page).first()).not.toContainText('· House');
    await expect(page.getByLabel('Add detected BirdNET source for birdcam').locator('option')).toHaveText([
        'Add detected source…',
        `House Mic · ${card} · House`,
        `Shed Mic · ${card} · Shed`
    ]);
});
