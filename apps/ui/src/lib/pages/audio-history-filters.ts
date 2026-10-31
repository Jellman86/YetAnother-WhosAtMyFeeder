/** The audio history filter form. The list shows the last applied copy, not the form as typed. */
export interface AudioHistoryFilters {
    days: number;
    species: string;
    source: string;
    minConfidence: number;
}

export const DEFAULT_AUDIO_HISTORY_FILTERS: Readonly<AudioHistoryFilters> = Object.freeze({
    days: 30,
    species: '',
    source: '',
    minConfidence: 0
});

/** The filters as the request sends them: trimmed text and numeric window and confidence. */
export function settledAudioHistoryFilters(filters: AudioHistoryFilters): AudioHistoryFilters {
    return {
        days: Number(filters.days),
        species: filters.species.trim(),
        source: filters.source.trim(),
        minConfidence: Number(filters.minConfidence)
    };
}

/** Whether applying the form would change the list. Whitespace alone changes nothing. */
export function audioHistoryFiltersDiffer(form: AudioHistoryFilters, applied: AudioHistoryFilters): boolean {
    const next = settledAudioHistoryFilters(form);
    const current = settledAudioHistoryFilters(applied);
    return (
        next.days !== current.days
        || next.species !== current.species
        || next.source !== current.source
        || next.minConfidence !== current.minConfidence
    );
}
