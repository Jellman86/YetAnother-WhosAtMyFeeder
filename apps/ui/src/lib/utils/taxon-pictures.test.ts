import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchSpeciesInfo = vi.fn();
vi.mock('../api/species', () => ({ fetchSpeciesInfo: (...args: unknown[]) => fetchSpeciesInfo(...args) }));

describe('speciesPicture', () => {
    beforeEach(() => {
        vi.resetModules();
        fetchSpeciesInfo.mockReset();
    });

    it('asks for the species by its scientific name, so a mammal is not looked up as a bird', async () => {
        fetchSpeciesInfo.mockResolvedValue({ thumbnail_url: 'https://example.test/dog.jpg', source: 'Wikipedia' });
        const { speciesPicture } = await import('./taxon-pictures');
        await expect(speciesPicture('Canis familiaris')).resolves.toEqual({ url: 'https://example.test/dog.jpg', source: 'Wikipedia' });
        // Without the scientific-name hint the species route tries eBird first and finds nothing for a dog.
        expect(fetchSpeciesInfo).toHaveBeenCalledWith('Canis familiaris', undefined, 'Canis familiaris');
    });

    it('keeps the photograph but names no source when the lookup gives none', async () => {
        fetchSpeciesInfo.mockResolvedValue({ thumbnail_url: 'https://example.test/fox.jpg', source: '  ' });
        const { speciesPicture } = await import('./taxon-pictures');
        await expect(speciesPicture('Vulpes vulpes')).resolves.toEqual({ url: 'https://example.test/fox.jpg', source: null });
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
