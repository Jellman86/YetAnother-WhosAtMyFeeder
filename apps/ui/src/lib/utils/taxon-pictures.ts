import { fetchSpeciesInfo } from '../api/species';

/**
 * A reference photograph for a species, from the same species information the record already
 * reads (Wikipedia, then iNaturalist). One request per species for the life of the page, so
 * hovering back and forth across a tree costs nothing after the first look.
 *
 * Species only: a family or genus has no reliable reference picture, and asking the species
 * information route about one would fill its cache with things that are not species.
 */
export interface ReferencePicture {
    url: string;
    /** Where the photograph comes from, such as Wikipedia, for its attribution. */
    source: string | null;
}

const pictures = new Map<string, Promise<ReferencePicture | null>>();

export function speciesPicture(scientificName: string): Promise<ReferencePicture | null> {
    const key = scientificName.trim();
    if (!key) return Promise.resolve(null);
    let picture = pictures.get(key);
    if (!picture) {
        // The scientific name doubles as the lookup hint: without it the species route tries
        // the bird sources first and finds nothing for a mammal, such as a dog.
        picture = fetchSpeciesInfo(key, undefined, key)
            .then((info) => (info.thumbnail_url ? { url: info.thumbnail_url, source: info.source?.trim() || null } : null))
            .catch(() => {
                // A failed lookup may succeed later in the session.
                pictures.delete(key);
                return null;
            });
        pictures.set(key, picture);
    }
    return picture;
}
