import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchSpeciesInfo = vi.fn();
vi.mock('../api/species', () => ({ fetchSpeciesInfo: (...args: unknown[]) => fetchSpeciesInfo(...args) }));

describe('speciesPicture', () => {
    beforeEach(() => {
        vi.resetModules();
        fetchSpeciesInfo.mockReset();
    });

    it('asks for the species by its scientific name, so a mammal is not looked up as a bird', async () => {
        fetchSpeciesInfo.mockResolvedValue({ thumbnail_url: 'https://example.test/dog.jpg' });
        const { speciesPicture } = await import('./taxon-pictures');
        await expect(speciesPicture('Canis familiaris')).resolves.toBe('https://example.test/dog.jpg');
        // Without the scientific-name hint the species route tries eBird first and finds nothing for a dog.
        expect(fetchSpeciesInfo).toHaveBeenCalledWith('Canis familiaris', undefined, 'Canis familiaris');
    });

    it('returns only the photograph, never the unrelated provider the lookup reports', async () => {
        // The species route keeps the summary provider in `source` even when the photograph came from the fallback provider.
        fetchSpeciesInfo.mockResolvedValue({
            thumbnail_url: 'https://static.inaturalist.org/photos/123/medium.jpg',
            source: 'Wikipedia',
            summary_source: 'Wikipedia'
        });
        const { speciesPicture } = await import('./taxon-pictures');
        await expect(speciesPicture('Prunella modularis')).resolves.toBe('https://static.inaturalist.org/photos/123/medium.jpg');
    });

    it('looks each species up once, and again after a failure', async () => {
        fetchSpeciesInfo.mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ thumbnail_url: null });
        const { speciesPicture } = await import('./taxon-pictures');
        await expect(speciesPicture(' Vulpes vulpes ')).resolves.toBeNull();
        await expect(speciesPicture('Vulpes vulpes')).resolves.toBeNull();
        await expect(speciesPicture('Vulpes vulpes')).resolves.toBeNull();
        expect(fetchSpeciesInfo).toHaveBeenCalledTimes(2);
    });
});
