import { test, expect, type Page } from '@playwright/test';

// A tall crop drawn into a wide card was cut to a band through its middle: feathers, not a bird
// (#481). It is now shown whole over a soft fill; scenes and near-square photos still fill the card.

const SHAPES: Record<string, [number, number]> = {
    tall: [187, 293], // a woodpecker on a pole, from a live install
    square: [500, 500],
    scene: [1920, 1080]
};

function svg([width, height]: [number, number]): string {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="${width}" height="${height}" fill="#3f6212"/><rect x="${width * 0.3}" y="${height * 0.05}" width="${width * 0.4}" height="${height * 0.9}" fill="#f8fafc"/></svg>`;
}

async function open(page: Page) {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const url = new URL(route.request().url());
        const id = url.pathname.match(/\/frigate\/([^/]+)\/thumbnail\.jpg$/)?.[1];
        if (id && SHAPES[id]) return route.fulfill({ contentType: 'image/svg+xml', body: svg(SHAPES[id]) });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/photo-fit.html');
    return errors;
}

test('a tall crop is shown whole over a fill; a scene and a square still fill the card', async ({ page }) => {
    const errors = await open(page);
    const photo = (id: string) => page.locator(`[data-photo-case="${id}"] [data-card-photo-fit]`);

    await expect(photo('tall')).toHaveAttribute('data-card-photo-fit', 'contain');
    await expect(photo('square')).toHaveAttribute('data-card-photo-fit', 'cover');
    await expect(photo('scene')).toHaveAttribute('data-card-photo-fit', 'cover');
    await expect(page.locator('[data-photo-case="tall"] [data-card-photo-fill]')).toHaveCount(1);
    await expect(page.locator('[data-photo-case="scene"] [data-card-photo-fill]')).toHaveCount(0);

    // The whole bird is inside the card: the drawn image keeps the photo's shape within its box.
    const drawn = await photo('tall').evaluate((image: HTMLImageElement) => {
        const box = image.getBoundingClientRect();
        const scale = Math.min(box.width / image.naturalWidth, box.height / image.naturalHeight);
        return { visibleHeight: image.naturalHeight * scale, boxHeight: box.height, fit: getComputedStyle(image).objectFit };
    });
    expect(drawn.fit).toBe('contain');
    expect(drawn.visibleHeight).toBeLessThanOrEqual(drawn.boxHeight + 0.5);
    expect(errors).toEqual([]);
});
