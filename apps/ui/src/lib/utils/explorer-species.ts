import type { EventFilterSpecies } from '../api';

export function filterExplorerSpecies<T extends EventFilterSpecies>(species: T[], search: string): T[] {
    const term = search.trim().toLowerCase();
    const matched = term
        ? species.filter((item) =>
              [item.display_name, item.common_name, item.scientific_name]
                  .filter(Boolean)
                  .some((name) => String(name).toLowerCase().includes(term))
          )
        : species;

    return [...matched].sort(
        (left, right) =>
            (right.count ?? 0) - (left.count ?? 0) ||
            left.display_name.localeCompare(right.display_name)
    );
}

/** The species a short list starts with; the rest wait behind Show all. */
const SHORT_LIST = 8;

/**
 * The species the rail lists, from an already sorted facet. A short list never hides the chosen
 * species, and is not shortened by one row just to offer the rest.
 */
export function shownExplorerSpecies<T extends Pick<EventFilterSpecies, 'value'>>(
    sorted: T[],
    { expanded, searching, selected }: { expanded: boolean; searching: boolean; selected: string }
): { items: T[]; more: number } {
    if (expanded || searching || sorted.length <= SHORT_LIST + 1) return { items: sorted, more: 0 };
    const items = sorted.slice(0, SHORT_LIST);
    const chosen = selected ? sorted.find((item) => item.value === selected) : undefined;
    if (chosen && !items.includes(chosen)) items.push(chosen);
    return { items, more: sorted.length - items.length };
}
