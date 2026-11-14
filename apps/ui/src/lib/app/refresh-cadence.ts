/**
 * How often each background reading is taken while the tab is visible and nothing is happening.
 * A reading is refreshed no faster than its source changes: a page left open on a quiet feeder
 * should cost the backend a handful of requests a minute, not dozens. Every reader also stops
 * while the tab is hidden and reads once when it is shown again.
 */
export const REFRESH_CADENCE_MS = {
    /** The sidebar's decorative CPU line. Settings > Health holds the detailed chart. */
    sidebarTelemetry: 15_000,
    /** Camera reachability changes when a camera or Frigate goes down, not second by second. */
    cameraHealth: 60_000,
    /** Running work is followed over the live stream; this only notices work it did not announce. */
    serverJobsIdle: 60_000,
    serverJobsActive: 5_000,
    analysisQueueIdle: 60_000,
    analysisQueueActive: 5_000,
    /** Backend health, the incident workspace, the owner's history counts, and the service connections. */
    ownerSystemChecks: 120_000,
    /** Whether the media folder is writable. It needs a storage measurement, so it is read rarely. */
    mediaStorageCheck: 600_000,
    /** BirdNET-Go reports a call a few seconds after it happens; the Heard card follows closely. */
    recentAudio: 15_000,
    /** The Dashboard's accelerator warning, and the faster rate while a one-off check is running. */
    providerWarning: 60_000,
    providerWarningChecking: 15_000,
    /** Settings > Detection: the runtime line under the model picker. */
    classifierRuntime: 15_000,
    /** Settings > Health: the backend keeps the whole window, so a slower read loses no samples. */
    systemLoadHistory: 15_000
} as const;

type Reading = keyof typeof REFRESH_CADENCE_MS;

/** The readings every owner page keeps current, whatever route is open. */
export const SHELL_READINGS: ReadonlyArray<{ reading: Reading; requests: number }> = [
    { reading: 'sidebarTelemetry', requests: 1 },
    { reading: 'cameraHealth', requests: 1 },
    { reading: 'serverJobsIdle', requests: 1 },
    { reading: 'analysisQueueIdle', requests: 1 },
    // Health, the incident workspace, the two history reads (list and count), and the broker and
    // Frigate connection reading, which the live stream also announces when it changes.
    { reading: 'ownerSystemChecks', requests: 5 },
    // A measurement is started, then collected.
    { reading: 'mediaStorageCheck', requests: 2 }
];

/**
 * Wraps a read so it runs at most once per interval however often it is asked for. A skipped call
 * resolves to the last value read, so the caller's reasoning about it does not change.
 */
export function readAtMostEvery<T>(
    read: () => Promise<T>,
    intervalMs: number,
    now: () => number = () => Date.now()
): () => Promise<T> {
    let last: { at: number; value: T } | null = null;
    let inFlight: Promise<T> | null = null;

    return (): Promise<T> => {
        if (inFlight) return inFlight;
        if (last && now() - last.at < intervalMs) return Promise.resolve(last.value);
        const request = read()
            .then((value) => {
                last = { at: now(), value };
                return value;
            })
            .finally(() => {
                inFlight = null;
            });
        inFlight = request;
        return request;
    };
}
