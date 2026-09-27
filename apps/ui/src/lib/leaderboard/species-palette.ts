/**
 * One colour per species slot, shared by the stacked timeline and the composition chart so a
 * species wears the same colour in both. The order is the colour-blind safety mechanism, not
 * decoration: it clears the adjacent-pair CVD and normal-vision checks on both of the app's
 * surfaces (dark #0a1225, light #ffffff). The previous palette put teal beside pink, which a
 * deuteranope cannot tell apart. Re-validate before reordering or adding a slot.
 */
const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7'];
const SERIES_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9'];
const OTHER_LIGHT = '#94a3b8';
const OTHER_DARK = '#64748b';

/** Slots before the rest fold into "Other". Keep in step with the compare cap in stats.py. */
export const SPECIES_SERIES_SLOTS = SERIES_LIGHT.length;

export function speciesSeriesColor(slot: number, dark: boolean): string {
    const palette = dark ? SERIES_DARK : SERIES_LIGHT;
    return palette[slot] ?? otherSeriesColor(dark);
}

export function otherSeriesColor(dark: boolean): string {
    return dark ? OTHER_DARK : OTHER_LIGHT;
}
