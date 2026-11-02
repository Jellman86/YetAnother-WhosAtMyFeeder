import { describe, expect, it } from 'vitest';
import type { GardenCapture } from '../api/garden';
import {
    dismissDomesticSuggestion,
    keptBirdCandidates,
    dismissedDomesticSuggestions,
    domesticBirdForRecord,
    domesticBirdKind,
    domesticBirdName,
    type DomesticBirdOption
} from './domestic-birds';
import { gardenEntryText, gardenEntryView, gardenVisitIdentity } from './garden-explorer';

const options: DomesticBirdOption[] = [
    { key: 'chicken', declared: true, scientific_names: ['Gallus gallus domesticus', 'Gallus gallus'], species_ids: [472, 21883] },
    { key: 'turkey', declared: false, scientific_names: ['Meleagris gallopavo'], species_ids: [395] }
];
const english = (_key: string, options: { default: string }): string => options.default;

function memoryStorage(): Pick<Storage, 'getItem' | 'setItem'> {
    const values = new Map<string, string>();
    return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => void values.set(key, value) };
}

function capture(overrides: Partial<GardenCapture> = {}): GardenCapture {
    return {
        id: 'b'.repeat(32),
        camera: 'greenhousecam',
        frigate_label: 'bird',
        observed_at: '2026-10-31T09:00:00Z',
        status: 'confirmed',
        reviewed_at: null,
        snapshot_url: null,
        identification: null,
        source_kind: 'frigate_event',
        motion_source: null,
        automatic_check: null,
        automatic_check_overridden: false,
        ...overrides
    };
}

describe('domestic birds', () => {
    it('matches a bird record by catalogue id or exact scientific name, never loosely', () => {
        expect(domesticBirdForRecord({ species_id: 472 }, options)?.key).toBe('chicken');
        expect(domesticBirdForRecord({ scientific_name: 'gallus  Gallus' }, options)?.key).toBe('chicken');
        expect(domesticBirdForRecord({ scientific_name: 'Meleagris gallopavo' }, options)?.declared).toBe(false);
        expect(domesticBirdForRecord({ scientific_name: 'Gallus' }, options)).toBeNull();
        expect(domesticBirdForRecord({ scientific_name: 'Chicken' }, options)).toBeNull();
    });

    it('names a bird for a record and a kind for a question', () => {
        expect(domesticBirdName('chicken', english)).toBe('Chicken');
        expect(domesticBirdKind('domestic_goose', english)).toBe('Domestic geese');
    });

    it('remembers a dismissed suggestion and ignores damaged storage', () => {
        const storage = memoryStorage();
        dismissDomesticSuggestion(storage, 'chicken');
        expect([...dismissedDomesticSuggestions(storage)]).toEqual(['chicken']);
        storage.setItem('yawamf.domesticBirdSuggestionsDismissed', '{not json');
        expect(dismissedDomesticSuggestions(storage).size).toBe(0);
        storage.setItem('yawamf.domesticBirdSuggestionsDismissed', '["chicken","pheasant"]');
        expect([...dismissedDomesticSuggestions(storage)]).toEqual(['chicken']);
    });

    it('titles a routed capture by the declared bird and groups it by that bird', () => {
        const routed = capture({
            domestic_route: {
                domestic_bird: 'chicken',
                origin: 'bird_detection',
                source_label: 'Gallus gallus',
                source_score: 0.93,
                routed_at: '2026-10-31T09:00:05Z'
            }
        });
        const view = gardenEntryView(routed);
        expect(view).toMatchObject({ name: 'Chicken', nameState: 'automatic', score: 0.93, review: null });
        const text = gardenEntryText(routed, view, (_key, fallback) => fallback, 'owner');
        expect(text).toEqual({ title: 'Chicken', state: 'Named automatically as a domestic bird you keep' });
        expect(gardenVisitIdentity(routed)).toBe('domestic:chicken');
    });

    it('asks a person about a pending animal whose species score missed the naming threshold', () => {
        const pending = capture({
            status: 'pending',
            frigate_label: 'dog',
            automatic_check: {
                outcome: 'animal',
                decision_reason: 'below_threshold',
                checked_at: '2026-10-31T09:00:00',
                naming_score: 0.72,
                naming_threshold: 0.8
            }
        });
        const view = gardenEntryView(pending);
        expect(view.review).toBe('presence');
        expect(gardenEntryText(pending, view, (_key, fallback) => fallback, 'owner').state).toBe(
            'Animal detected; species below the naming threshold'
        );
    });
});

describe('keptBirdCandidates', () => {
    const options = [
        { key: 'chicken' as const, declared: false, scientific_names: ['Gallus gallus domesticus', 'Gallus gallus'], species_ids: [472] },
        { key: 'turkey' as const, declared: true, scientific_names: ['Meleagris gallopavo'], species_ids: [] }
    ];

    it('names each flagged species that is a domestic bird, once per bird', () => {
        const rows = [
            { displayName: 'Red Junglefowl', scientificName: 'Gallus  gallus' },
            { displayName: 'Chicken', scientificName: 'Gallus gallus domesticus' },
            { displayName: 'Plateau Striped Whiptail', scientificName: 'Aspidoscelis velox' },
            { displayName: 'Unknown', scientificName: null }
        ];
        expect(keptBirdCandidates(rows, options)).toEqual([{ bird: 'chicken', species: 'Red Junglefowl', declared: false }]);
    });

    it('still offers a declared bird whose records remain in bird history', () => {
        expect(keptBirdCandidates([{ displayName: 'Wild Turkey', scientificName: 'Meleagris gallopavo' }], options)).toEqual([
            { bird: 'turkey', species: 'Wild Turkey', declared: true }
        ]);
    });
});
