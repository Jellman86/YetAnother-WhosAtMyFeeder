export interface SeriesName {
    name: string;
    /** What tells this series apart when another shares its name, usually the scientific name. */
    qualifier?: string | null;
}

/**
 * Labels that are guaranteed different, in the order given. Translated names are not unique across
 * taxa (German calls both Sitta europaea and the family Sittidae "Kleiber"), and a chart legend
 * needs one label per series for a reader to tell them apart.
 */
export function distinctSeriesLabels(series: readonly SeriesName[]): string[] {
    const uses = new Map<string, number>();
    for (const { name } of series) uses.set(name, (uses.get(name) ?? 0) + 1);

    const taken = new Set<string>();
    return series.map(({ name, qualifier }) => {
        const shared = (uses.get(name) ?? 0) > 1;
        const wanted = shared && qualifier && qualifier !== name ? `${name} (${qualifier})` : name;
        let label = wanted;
        for (let ordinal = 2; taken.has(label); ordinal += 1) label = `${wanted} ${ordinal}`;
        taken.add(label);
        return label;
    });
}
