import type { Page } from '@playwright/test';

/**
 * Every meter as Chromium draws it, at 3:1 (WCAG 1.4.11): a meter's fill against its track, a
 * chart bar against the ground behind it, and a live indicator against its track. Computed colours
 * are read through a canvas, so a translucent or colour-mixed fill counts as it is seen, and the
 * element's and its ancestors' opacity count too, at the lowest a running animation reaches.
 */
type Measured = { meters: number; failures: string[] };

export async function measureMeters(page: Page): Promise<Measured> {
    return page.evaluate(() => {
        // Any computed colour (rgb, oklab from a colour-mix) as sRGB with its alpha, through a canvas.
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        if (!context) throw new Error('no 2d canvas');
        const parse = (value: string): [number, number, number, number] => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = '#000';
            context.fillStyle = value;
            context.fillRect(0, 0, 1, 1);
            const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
            return [r, g, b, a / 255];
        };
        const luminance = ([r, g, b]: number[]) => {
            const channel = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
            return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        // How see-through an element is at its faintest: its own opacity and every ancestor's, each
        // at the lowest value a running animation takes it to, so a pulse is measured at its dip.
        const faintest = (node: Element, stopAt: Element | null): number => {
            let result = 1;
            for (let at: Element | null = node; at && at !== stopAt; at = at.parentElement) {
                let lowest = Number.parseFloat(getComputedStyle(at).opacity);
                for (const animation of at.getAnimations()) {
                    const effect = animation.effect;
                    if (!(effect instanceof KeyframeEffect)) continue;
                    for (const frame of effect.getKeyframes()) {
                        if (frame.opacity !== undefined) lowest = Math.min(lowest, Number.parseFloat(String(frame.opacity)));
                    }
                }
                result *= Number.isFinite(lowest) ? lowest : 1;
            }
            return result;
        };
        const contrast = (a: number[], b: number[]) => {
            const [x, y] = [luminance(a), luminance(b)];
            return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
        };
        const failures: string[] = [];
        let meters = 0;
        for (const track of document.querySelectorAll<HTMLElement>('.bg-track')) {
            const fill = [...track.children].find((child) => (child as HTMLElement).style.width) as HTMLElement | undefined;
            if (!fill || fill.getBoundingClientRect().width < 1) continue;
            meters += 1;
            const ground = parse(getComputedStyle(track).backgroundColor);
            const [r, g, b, own] = parse(getComputedStyle(fill).backgroundColor);
            // Against its own track, so only the fill's opacity (and anything between) counts.
            const a = own * faintest(fill, track);
            const drawn = [r * a + ground[0] * (1 - a), g * a + ground[1] * (1 - a), b * a + ground[2] * (1 - a)];
            const ratio = contrast(drawn, ground);
            if (ratio < 3) {
                const where = fill.closest('[data-field-log-row], tr, li, section')?.textContent?.trim().slice(0, 40) ?? '';
                failures.push(`${getComputedStyle(fill).backgroundColor} on ${getComputedStyle(track).backgroundColor}: ${ratio.toFixed(2)} (${where})`);
            }
        }
        // A chart bar is measured against the first opaque ground behind it, and a live indicator
        // inside a meter against that meter's track.
        const groundOf = (node: Element): number[] => {
            for (let at: Element | null = node.parentElement; at; at = at.parentElement) {
                const colour = parse(getComputedStyle(at).backgroundColor);
                if (colour[3] >= 0.99) return colour.slice(0, 3);
            }
            return parse(getComputedStyle(document.body).backgroundColor).slice(0, 3);
        };
        for (const mark of document.querySelectorAll<HTMLElement>('[data-chart-bar], [data-meter-indicator]')) {
            const box = mark.getBoundingClientRect();
            if (box.width < 1 || box.height < 1) continue;
            meters += 1;
            const ground = groundOf(mark);
            const [r, g, b, own] = parse(getComputedStyle(mark).backgroundColor);
            const a = own * faintest(mark, null);
            const drawn = [r * a + ground[0] * (1 - a), g * a + ground[1] * (1 - a), b * a + ground[2] * (1 - a)];
            const ratio = contrast(drawn, ground);
            if (ratio < 3) failures.push(`${mark.dataset.chartBar !== undefined ? 'bar' : 'indicator'} ${getComputedStyle(mark).backgroundColor}: ${ratio.toFixed(2)}`);
        }
        return { meters, failures };
    });
}
