/**
 * The media storage limit is stored in MiB, where 0 means no limit. Settings shows it as a switch
 * and a size in GB, so 0 never has to be typed or explained.
 */
const MEGABYTES_PER_GIGABYTE = 1024;
const SMALLEST_LIMIT_GB = 0.5;
const LARGEST_LIMIT_GB = 1024;

export function storedMegabytesToGigabytes(megabytes: number): number {
    return Math.round((megabytes / MEGABYTES_PER_GIGABYTE) * 10) / 10;
}

export function gigabytesToStoredMegabytes(gigabytes: number): number {
    return Math.round(gigabytes * MEGABYTES_PER_GIGABYTE);
}

/**
 * A typed limit in GB, or null when it is empty or not a size the limit can be. A small limit
 * evicts media, so an unreadable entry is refused rather than replaced by the smallest size.
 */
export function parseStorageLimitGigabytes(text: string): number | null {
    const trimmed = text.trim();
    if (trimmed === '') return null;
    const value = Number(trimmed);
    if (!Number.isFinite(value) || value < SMALLEST_LIMIT_GB || value > LARGEST_LIMIT_GB) return null;
    return value;
}
