import { describe, expect, it, vi } from 'vitest';

import type { SearchResult } from '../api/species';
import {
    buildBlockedSpeciesEntry,
    formatBlockedSpeciesLabel,
    migrateLegacyBlockedLabels
} from './blocked-species';

describe('blocked species helpers', () => {
    it('builds a structured blocked species entry from a search result', () => {
        expect(
            buildBlockedSpeciesEntry({
                id: 'Columba livia',
                display_name: 'Columba livia',
                scientific_name: 'Columba livia',
                common_name: 'Rock Pigeon',
                taxa_id: 3017,
            })
        ).toEqual({
            scientific_name: 'Columba livia',
            common_name: 'Rock Pigeon',
            taxa_id: 3017,
        });
    });

    it('formats taxonomy filter entries with common and scientific names', () => {
        expect(
            formatBlockedSpeciesLabel({
                common_name: 'House Sparrow',
                scientific_name: 'Passer domesticus',
                taxa_id: 123,
            })
        ).toBe('House Sparrow (Passer domesticus)');
    });

    it('conservatively migrates only unambiguous legacy labels', async () => {
        const searchFn = vi.fn(async (query: string): Promise<SearchResult[]> => {
            if (query === 'Rock Pigeon') {
                return [
                    {
                        id: 'Columba livia',
                        display_name: 'Columba livia',
                        scientific_name: 'Columba livia',
                        common_name: 'Rock Pigeon',
                        taxa_id: 3017,
                    }
                ];
            }
            return [
                {
                    id: 'Unknown alias',
                    display_name: 'Unknown alias',
                    scientific_name: null,
                    common_name: null,
                    taxa_id: null,
                }
            ];
        });

        const migrated = await migrateLegacyBlockedLabels(['Rock Pigeon', 'background'], searchFn);

        expect(migrated.blockedSpecies).toEqual([
            {
                scientific_name: 'Columba livia',
                common_name: 'Rock Pigeon',
                taxa_id: 3017,
            }
        ]);
        expect(migrated.legacyBlockedLabels).toEqual(['background']);
    });
});
