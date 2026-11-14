/** WCAG 2 contrast arithmetic, shared by the tests that hold the kit's colours to AA. */

export type Rgb = readonly [number, number, number];

function channel(value: number): number {
    const unit = value / 255;
    return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance([red, green, blue]: Rgb): number {
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
}

/** The WCAG contrast ratio of two opaque colours, from 1 (the same) to 21 (black on white). */
export function contrastRatio(first: Rgb, second: Rgb): number {
    const [lighter, darker] = [relativeLuminance(first), relativeLuminance(second)].sort((a, b) => b - a);
    return (lighter + 0.05) / (darker + 0.05);
}

/** A translucent colour as it is seen over an opaque ground. */
export function flatten(colour: Rgb, alpha: number, ground: Rgb): Rgb {
    const mix = (index: 0 | 1 | 2): number => Math.round(colour[index] * alpha + ground[index] * (1 - alpha));
    return [mix(0), mix(1), mix(2)];
}
