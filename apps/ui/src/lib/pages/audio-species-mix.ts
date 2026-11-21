export interface AudioMixSlice {
    species: string;
    count: number;
    /** The slice for every species the ring does not name. */
    other: boolean;
}

/**
 * The slices of the species ring. It names the most heard species and gathers the rest into
 * one slice, so its total is the same "Heard" figure the page states for the window.
 */
export function audioSpeciesMix(
    topSpecies: readonly { species: string; count: number }[],
    total: number | null | undefined,
    otherLabel: string,
    named: number
): AudioMixSlice[] {
    const slices: AudioMixSlice[] = topSpecies.slice(0, named).map((item) => ({ species: item.species, count: item.count, other: false }));
    const rest = (total ?? 0) - slices.reduce((sum, slice) => sum + slice.count, 0);
    if (rest > 0) slices.push({ species: otherLabel, count: rest, other: true });
    return slices;
}
