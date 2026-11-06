import { fetchClassifierLabels, type SearchResult } from '../api';
import { authStore } from './auth.svelte';

interface ClassifierLabelsDeps {
    fetchLabels: () => Promise<{ labels: string[] }>;
    canReadLabels: () => boolean;
}

/**
 * The classifier's label list: about 10,000 names and over 200 kB. It is only a fallback for the
 * owner's species search when the catalogue search fails, so it is read on that first need, once
 * per page load, and never for a visitor.
 */
export class ClassifierLabelsStore {
    labels = $state.raw<readonly string[]>([]);
    #deps: ClassifierLabelsDeps;
    #read: Promise<readonly string[]> | null = null;
    #loaded = false;

    constructor(deps: ClassifierLabelsDeps) {
        this.#deps = deps;
    }

    /** The labels, read on the first call; a failed read answers with none and is tried again next time. */
    load(): Promise<readonly string[]> {
        if (!this.#deps.canReadLabels()) return Promise.resolve([]);
        if (this.#loaded) return Promise.resolve(this.labels);
        if (this.#read) return this.#read;
        const read = this.#deps.fetchLabels().then(
            ({ labels }) => {
                this.labels = labels;
                this.#loaded = true;
                return this.labels;
            },
            (): readonly string[] => []
        );
        this.#read = read;
        void read.finally(() => {
            if (this.#read === read) this.#read = null;
        });
        return read;
    }

    /** The species pickers' fallback: labels containing the query, shaped as catalogue results. */
    async searchFallback(query: string, limit?: number): Promise<SearchResult[]> {
        const needle = query.trim().toLowerCase();
        const matches = (await this.load()).filter((label) => label.toLowerCase().includes(needle));
        return matches
            .slice(0, limit ?? matches.length)
            .map((label) => ({ id: label, display_name: label, common_name: null, scientific_name: null }));
    }
}

export const classifierLabelsStore = new ClassifierLabelsStore({
    fetchLabels: fetchClassifierLabels,
    canReadLabels: () => authStore.hasOwnerAccess
});
