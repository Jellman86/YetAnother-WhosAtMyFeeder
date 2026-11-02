import type { EventFilterSpecies } from '../api';

/** The most recorded species first; the Explorer search finds any of them by name. */
export function sortExplorerSpecies<T extends EventFilterSpecies>(species: T[]): T[] {
    return [...species].sort(
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
    { expanded, selected }: { expanded: boolean; selected: string }
): { items: T[]; more: number } {
    if (expanded || sorted.length <= SHORT_LIST + 1) return { items: sorted, more: 0 };
    const items = sorted.slice(0, SHORT_LIST);
    const chosen = selected ? sorted.find((item) => item.value === selected) : undefined;
    if (chosen && !items.includes(chosen)) items.push(chosen);
    return { items, more: sorted.length - items.length };
}
