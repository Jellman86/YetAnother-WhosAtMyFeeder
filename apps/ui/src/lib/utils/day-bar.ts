export interface DayBarSlotInput {
    /** BirdNET is configured and this viewer may hear its calls. */
    audioConfigured: boolean;
    /** New captures are analysed to count birds; null while that configuration is unknown. */
    countingConfigured: boolean | null;
    /** Captures in the window that birds were counted in; null until the window is read. */
    countedCaptures: number | null;
}

export interface DayBarSlots {
    countedBirds: boolean;
    audio: boolean;
}

/**
 * Which optional figures the day bar holds. Configuration decides before any reading arrives, so the
 * bar is drawn at its final width and loading fills it in rather than inserting cells. A window that
 * still holds counts made before counting was turned off shows them.
 */
export function dayBarSlots({ audioConfigured, countingConfigured, countedCaptures }: DayBarSlotInput): DayBarSlots {
    return {
        countedBirds: countingConfigured === true || (countedCaptures ?? 0) > 0,
        audio: audioConfigured
    };
}
