import { fetchTaxonFacts, fetchTaxonNames, type TaxonFacts, type TaxonFactsPage, type TaxonNames } from '../api/taxonomy';
import { factsBatches, type FactEntry } from '../taxonomy/taxon-facts';
import { logger } from './logger';

/**
 * What this install recorded of the taxa on one surface: the lineage ladder, its card and the
 * family tree it opens share one. Each open level of the tree is asked for once, in batches the
 * route accepts, and a taxon already known or on its way is never asked for again; a failed one
 * only when the reader asks to try again.
 */
export class TaxonFactsStore {
    entries = $state.raw<ReadonlyMap<number, FactEntry>>(new Map());
    /** The window the facts describe, from the first answer: all history, or what is shared with visitors. */
    scope = $state.raw<Pick<TaxonFactsPage, 'scope' | 'shared_days'> | null>(null);

    get(taxonId: number): FactEntry | undefined {
        return this.entries.get(taxonId);
    }

    request(taxonIds: Iterable<number>, { retryFailed = false }: { retryFailed?: boolean } = {}): void {
        for (const batch of factsBatches(taxonIds, this.entries, { retryFailed })) void this.load(batch);
    }

    private mark(taxonIds: readonly number[], entry: (taxonId: number) => FactEntry): void {
        const next = new Map(this.entries);
        for (const taxonId of taxonIds) next.set(taxonId, entry(taxonId));
        this.entries = next;
    }

    private async load(batch: readonly number[]): Promise<void> {
        this.mark(batch, () => ({ state: 'loading' }));
        try {
            const page = await fetchTaxonFacts(batch);
            const found = new Map<number, TaxonFacts>(page.facts.map((facts) => [facts.taxon_id, facts]));
            this.scope = { scope: page.scope, shared_days: page.shared_days ?? null };
            this.mark(batch, (taxonId) => {
                const facts = found.get(taxonId);
                return facts ? { state: 'ready', facts } : { state: 'absent' };
            });
        } catch (error) {
            logger.warn('Family tree facts unavailable', { taxa: batch.length, error });
            this.mark(batch, () => ({ state: 'failed' }));
        }
    }
}

export type OtherNamesResult = { state: 'ready'; names: TaxonNames } | { state: 'failed' };

const otherNames = new Map<number, Promise<OtherNamesResult>>();

/** A species' names in the catalogue's other languages, read once per page and again after a failure. */
export function speciesOtherNames(taxonId: number): Promise<OtherNamesResult> {
    let found = otherNames.get(taxonId);
    if (!found) {
        found = fetchTaxonNames(taxonId)
            .then((names): OtherNamesResult => ({ state: 'ready', names }))
            .catch((): OtherNamesResult => {
                otherNames.delete(taxonId);
                return { state: 'failed' };
            });
        otherNames.set(taxonId, found);
    }
    return found;
}
