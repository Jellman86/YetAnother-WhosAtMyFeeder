/**
 * The media storage limit is stored in MiB, where 0 means no limit. Settings shows it as a switch
 * and a size in GB, so 0 never has to be typed or explained.
 */
const MEGABYTES_PER_GIGABYTE = 1024;
const SMALLEST_LIMIT_GB = 0.5;

export function storedMegabytesToGigabytes(megabytes: number): number {
    return Math.round((megabytes / MEGABYTES_PER_GIGABYTE) * 10) / 10;
}

export function gigabytesToStoredMegabytes(gigabytes: number): number {
    const safe = Number.isFinite(gigabytes) ? Math.max(SMALLEST_LIMIT_GB, gigabytes) : SMALLEST_LIMIT_GB;
    return Math.round(safe * MEGABYTES_PER_GIGABYTE);
}
