import type { EventFilterSpecies } from '../api';

export function filterExplorerSpecies(
    species: EventFilterSpecies[],
    search: string
): EventFilterSpecies[] {
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
