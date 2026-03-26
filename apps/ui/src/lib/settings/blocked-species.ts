import type { SearchResult } from '../api/species';
import type { BlockedSpeciesEntry } from '../api/settings';

type SearchFn = (query: string) => Promise<SearchResult[]>;

function normalizeText(value: string | null | undefined): string | null {
    const text = String(value || '').trim();
    return text || null;
}

function normalizeCase(value: string): string {
    return value.toLocaleLowerCase();
}

function collapseTrailingParenthetical(value: string | null | undefined): string | null {
    const text = normalizeText(value);
    if (!text) return null;
    return text.replace(/\s*\([^()]*\)\s*$/, '').trim() || text;
}

function canonicalKey(entry: BlockedSpeciesEntry): string {
    if (entry.taxa_id != null) return `taxa:${entry.taxa_id}`;
    if (entry.scientific_name) return `scientific:${normalizeCase(entry.scientific_name)}`;
    if (entry.common_name) return `common:${normalizeCase(entry.common_name)}`;
    return 'empty';
}

function matchesLegacyLabel(result: SearchResult, label: string): boolean {
    const candidateValues = [
        result.id,
        result.display_name,
        result.scientific_name,
        result.common_name,
    ];
    const normalizedCandidates = new Set(
        candidateValues
            .flatMap((value) => [normalizeText(value), collapseTrailingParenthetical(value)])
            .filter((value): value is string => Boolean(value))
            .map((value) => normalizeCase(value))
    );
    const normalizedLabels = new Set(
        [normalizeText(label), collapseTrailingParenthetical(label)]
            .filter((value): value is string => Boolean(value))
            .map((value) => normalizeCase(value))
    );

    for (const candidate of normalizedCandidates) {
        if (normalizedLabels.has(candidate)) {
            return true;
        }
    }
    return false;
}

export function buildBlockedSpeciesEntry(result: SearchResult): BlockedSpeciesEntry | null {
    const entry: BlockedSpeciesEntry = {
        scientific_name: normalizeText(result.scientific_name),
        common_name: normalizeText(result.common_name),
        taxa_id: result.taxa_id ?? null,
    };

    if (entry.taxa_id == null && !entry.scientific_name && !entry.common_name) {
        return null;
    }
    return entry;
}

export function mergeBlockedSpeciesEntries(entries: BlockedSpeciesEntry[]): BlockedSpeciesEntry[] {
    const merged = new Map<string, BlockedSpeciesEntry>();

    for (const rawEntry of entries) {
        const entry = {
            scientific_name: normalizeText(rawEntry.scientific_name),
            common_name: normalizeText(rawEntry.common_name),
            taxa_id: rawEntry.taxa_id ?? null,
        };
        if (entry.taxa_id == null && !entry.scientific_name && !entry.common_name) {
            continue;
        }
        const key = canonicalKey(entry);
        if (!merged.has(key)) {
            merged.set(key, entry);
        }
    }

    return Array.from(merged.values());
}

export function formatBlockedSpeciesLabel(entry: BlockedSpeciesEntry): string {
    const commonName = normalizeText(entry.common_name);
    const scientificName = normalizeText(entry.scientific_name);
    if (commonName && scientificName && commonName !== scientificName) {
        return `${commonName} (${scientificName})`;
    }
    return commonName || scientificName || `Taxon ${entry.taxa_id}`;
}

export async function migrateLegacyBlockedLabels(
    legacyLabels: string[],
    searchFn: SearchFn
): Promise<{ blockedSpecies: BlockedSpeciesEntry[]; legacyBlockedLabels: string[] }> {
    const blockedSpecies: BlockedSpeciesEntry[] = [];
    const unresolved: string[] = [];

    for (const rawLabel of legacyLabels) {
        const label = normalizeText(rawLabel);
        if (!label) {
            continue;
        }

        try {
            const results = await searchFn(label);
            const exactMatches = mergeBlockedSpeciesEntries(
                results
                    .filter((result) => matchesLegacyLabel(result, label))
                    .map((result) => buildBlockedSpeciesEntry(result))
                    .filter((entry): entry is BlockedSpeciesEntry => entry !== null)
            );

            if (exactMatches.length === 1) {
                blockedSpecies.push(exactMatches[0]);
                continue;
            }
        } catch {
            // Keep unresolved legacy labels as-is if migration lookup fails.
        }

        unresolved.push(label);
    }

    return {
        blockedSpecies: mergeBlockedSpeciesEntries(blockedSpecies),
        legacyBlockedLabels: unresolved,
    };
}
