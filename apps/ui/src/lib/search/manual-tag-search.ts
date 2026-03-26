export type ManualTagSearchOptions = {
    limit: number;
    hydrateMissing: boolean;
};

export function getManualTagSearchOptions(query: string): ManualTagSearchOptions {
    const normalized = query.trim();

    return {
        limit: 50,
        hydrateMissing: normalized.length > 2
    };
}
