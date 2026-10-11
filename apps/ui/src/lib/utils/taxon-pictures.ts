import { fetchSpeciesInfo } from '../api/species';

/**
 * A reference photograph for a species, from the same species information the record already
 * reads (Wikipedia, then iNaturalist). One request per species for the life of the page, so
 * hovering back and forth across a tree costs nothing after the first look.
 *
 * Species only: a family or genus has no reliable reference picture, and asking the species
 * information route about one would fill its cache with things that are not species.
 */
const pictures = new Map<string, Promise<string | null>>();

export function speciesPicture(scientificName: string): Promise<string | null> {
    const key = scientificName.trim();
    if (!key) return Promise.resolve(null);
    let picture = pictures.get(key);
    if (!picture) {
        picture = fetchSpeciesInfo(key)
            .then((info) => info.thumbnail_url ?? null)
            .catch(() => {
                // A failed lookup may succeed later in the session.
                pictures.delete(key);
                return null;
            });
        pictures.set(key, picture);
    }
    return picture;
}
