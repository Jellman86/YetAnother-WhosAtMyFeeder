import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchSpeciesInfo = vi.fn();
vi.mock('../api/species', () => ({ fetchSpeciesInfo: (...args: unknown[]) => fetchSpeciesInfo(...args) }));

describe('speciesReference', () => {
    beforeEach(() => {
        vi.resetModules();
        fetchSpeciesInfo.mockReset();
    });

    it('asks for the species by its scientific name, so a mammal is not looked up as a bird', async () => {
        fetchSpeciesInfo.mockResolvedValue({ thumbnail_url: 'https://example.test/dog.jpg' });
        const { speciesReference } = await import('./taxon-pictures');
        await expect(speciesReference('Canis familiaris')).resolves.toMatchObject({ state: 'ready', thumbnail: 'https://example.test/dog.jpg' });
        // Without the scientific-name hint the species route tries eBird first and finds nothing for a dog.
        expect(fetchSpeciesInfo).toHaveBeenCalledWith('Canis familiaris', undefined, 'Canis familiaris', undefined);
    });

    it('keeps the photograph apart from the summary provider the lookup reports', async () => {
        // The species route keeps the summary provider in `source` even when the photograph came from the fallback provider.
        fetchSpeciesInfo.mockResolvedValue({
            thumbnail_url: 'https://static.inaturalist.org/photos/123/medium.jpg',
            source: 'Wikipedia',
            summary_source: 'Wikipedia',
            extract: 'A small passerine.',
            conservation_status: 'LC'
        });
        const { speciesReference } = await import('./taxon-pictures');
        await expect(speciesReference('Prunella modularis')).resolves.toEqual({
            state: 'ready',
            thumbnail: 'https://static.inaturalist.org/photos/123/medium.jpg',
            extract: 'A small passerine.',
            summarySource: 'Wikipedia',
            conservation: 'LC'
        });
    });

    it('looks each taxon up once, says when a lookup failed, and tries again after a failure', async () => {
        fetchSpeciesInfo.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ thumbnail_url: null });
        const { speciesReference } = await import('./taxon-pictures');
        await expect(speciesReference(' Vulpes vulpes ')).resolves.toEqual({ state: 'failed' });
        await expect(speciesReference('Vulpes vulpes')).resolves.toMatchObject({ state: 'ready', thumbnail: null });
        await expect(speciesReference('Vulpes vulpes')).resolves.toMatchObject({ state: 'ready' });
        expect(fetchSpeciesInfo).toHaveBeenCalledTimes(2);
    });
});

describe('groupReference', () => {
    beforeEach(() => {
        vi.resetModules();
        fetchSpeciesInfo.mockReset();
    });

    it('binds a family to its rank and caches it apart from a species of the same text', async () => {
        fetchSpeciesInfo.mockResolvedValue({ extract: 'The accentors.' });
        const { groupReference, speciesReference } = await import('./taxon-pictures');
        await expect(groupReference('Prunellidae', 'family')).resolves.toMatchObject({ extract: 'The accentors.' });
        await groupReference('Prunellidae', 'family');
        await speciesReference('Prunellidae');
        expect(fetchSpeciesInfo.mock.calls).toEqual([
            ['Prunellidae', undefined, 'Prunellidae', 'family'],
            ['Prunellidae', undefined, 'Prunellidae', undefined]
        ]);
    });
});
