import type { components } from '../api/generated/openapi';

/**
 * Domestic birds an owner can keep. A declared one is a Garden animal on every camera and never
 * a bird detection. Matching a bird record is by exact catalogue identity, as the server
 * reports it; names are never compared loosely.
 */
export type DomesticBirdKey = components['schemas']['GardenDomesticBirdOption']['key'];
export type DomesticBirdOption = components['schemas']['GardenDomesticBirdOption'];

export const DOMESTIC_BIRD_KEYS: readonly DomesticBirdKey[] = [
    'chicken',
    'domestic_duck',
    'domestic_goose',
    'turkey',
    'guinea_fowl',
    'peafowl',
    'domestic_pigeon',
    'quail'
];

type Translate = (key: string, options: { default: string; values?: Record<string, string> }) => string;

const NAMES: Record<DomesticBirdKey, [string, string]> = {
    chicken: ['Chicken', 'Chickens'],
    domestic_duck: ['Domestic duck', 'Domestic ducks'],
    domestic_goose: ['Domestic goose', 'Domestic geese'],
    turkey: ['Turkey', 'Turkeys'],
    guinea_fowl: ['Guineafowl', 'Guineafowl'],
    peafowl: ['Peafowl', 'Peafowl'],
    domestic_pigeon: ['Domestic pigeon or dove', 'Domestic pigeons or doves'],
    quail: ['Quail', 'Quail']
};

/** One bird's name, as a record title: "Chicken". */
export function domesticBirdName(key: DomesticBirdKey, t: Translate): string {
    return t(`garden.domestic_birds.name.${key}`, { default: NAMES[key][0] });
}

/** The kind an owner keeps, as a chip or a question: "Chickens". */
export function domesticBirdKind(key: DomesticBirdKey, t: Translate): string {
    return t(`garden.domestic_birds.kind.${key}`, { default: NAMES[key][1] });
}

/** The domestic bird a bird record stands for, by its catalogue id or exact scientific name. */
export function domesticBirdForRecord(
    record: { species_id?: number | null; scientific_name?: string | null },
    options: readonly DomesticBirdOption[]
): DomesticBirdOption | null {
    const name = (record.scientific_name ?? '').split(/\s+/).filter(Boolean).join(' ').toLowerCase();
    return (
        options.find(
            (option) =>
                (record.species_id != null && option.species_ids.includes(record.species_id))
                || (name !== '' && option.scientific_names.some((candidate) => candidate.toLowerCase() === name))
        ) ?? null
    );
}

const DISMISSED_KEY = 'yawamf.domesticBirdSuggestionsDismissed';

/** Suggestions the owner has dismissed on this device, so a "Do you keep…?" is asked once. */
export function dismissedDomesticSuggestions(storage: Pick<Storage, 'getItem'> | null): Set<DomesticBirdKey> {
    try {
        const parsed: unknown = JSON.parse(storage?.getItem(DISMISSED_KEY) ?? '[]');
        return new Set(
            Array.isArray(parsed) ? parsed.filter((key): key is DomesticBirdKey => (DOMESTIC_BIRD_KEYS as readonly unknown[]).includes(key)) : []
        );
    } catch {
        return new Set();
    }
}

export function dismissDomesticSuggestion(storage: Pick<Storage, 'getItem' | 'setItem'> | null, key: DomesticBirdKey): void {
    const keys = dismissedDomesticSuggestions(storage);
    keys.add(key);
    try {
        storage?.setItem(DISMISSED_KEY, JSON.stringify([...keys]));
    } catch {
        // Storage can be full or blocked; the suggestion then simply returns next time.
    }
}
