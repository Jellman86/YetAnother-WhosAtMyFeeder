import { fetchSpeciesInfo } from '../api/species';

/**
 * Reference information for a taxon card: a species' photograph, summary and IUCN category, or a
 * family's or order's summary. One request per taxon for the life of the page, so hovering back
 * and forth across a tree costs nothing after the first look.
 *
 * Every lookup is bound to the scientific name, and a group to its rank as well, so the species
 * route never answers from a name search that could land on the wrong page (a "Bird Dog" is an
 * aircraft). Those bound lookups are cached apart from the name-only species cache, so asking
 * about a family never files it as a species. A genus is never asked about: its name can belong
 * to a plant as well as a bird.
 */
export type TaxonReference =
    | {
          state: 'ready';
          thumbnail: string | null;
          extract: string | null;
          summarySource: string | null;
          conservation: string | null;
      }
    | { state: 'failed' };

export type GroupRank = 'family' | 'order';

const references = new Map<string, Promise<TaxonReference>>();

function lookUp(scientificName: string, rank?: GroupRank): Promise<TaxonReference> {
    const name = scientificName.trim();
    if (!name) return Promise.resolve({ state: 'ready', thumbnail: null, extract: null, summarySource: null, conservation: null });
    const key = rank ? `${rank}:${name}` : name;
    let reference = references.get(key);
    if (!reference) {
        // The scientific name doubles as the lookup hint: without it the species route tries
        // the bird sources first and finds nothing for a mammal, such as a dog.
        reference = fetchSpeciesInfo(name, undefined, name, rank)
            .then((info): TaxonReference => ({
                state: 'ready',
                thumbnail: info.thumbnail_url ?? null,
                extract: info.extract ?? null,
                summarySource: info.summary_source ?? null,
                conservation: info.conservation_status ?? null
            }))
            .catch((): TaxonReference => {
                // A failed lookup may succeed later in the session.
                references.delete(key);
                return { state: 'failed' };
            });
        references.set(key, reference);
    }
    return reference;
}

/** A species' reference photograph, summary and IUCN category. */
export function speciesReference(scientificName: string): Promise<TaxonReference> {
    return lookUp(scientificName);
}

/** A family's or order's summary. Its photograph, if any, is not used: a group is pictured by its own members. */
export function groupReference(scientificName: string, rank: GroupRank): Promise<TaxonReference> {
    return lookUp(scientificName, rank);
}
