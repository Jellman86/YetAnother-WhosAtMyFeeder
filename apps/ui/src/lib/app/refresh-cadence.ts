/**
 * How often each background reading is taken while the tab is visible and nothing is happening.
 * A reading is refreshed no faster than its source changes. The owner's status (jobs, the analysis
 * queue, connections, cameras, the model and the sidebar's CPU line) is pushed over the live stream
 * and needs no reading at all (`stores/system_status.svelte.ts`). Every reader also stops while the
 * tab is hidden and reads once when it is shown again.
 */
export const REFRESH_CADENCE_MS = {
    /**
     * A visitor's sidebar CPU line. Visitors never receive the pushed status, so they sample it;
     * a decorative trace needs no more than a point a minute.
     */
    sidebarTelemetry: 60_000,
    /**
     * BirdNET-Go reports a call a few seconds after it happens; the Heard card follows closely. With the
     * live stream connected, an owner's card reads when a call is announced, no more often than this.
     */
    recentAudio: 15_000,
    /** The Dashboard's day: the 24-hour summary, visit log, species checks and the review queue. */
    dashboardDay: 60_000,
    /**
     * While the live stream announces every change to a reading, the one read it still takes: the
     * 24-hour window moving on, or an announcement lost on the way.
     */
    liveSafetyRead: 300_000,
    /** The Health page's chart. The backend keeps the whole half hour, so a minute loses no samples. */
    systemLoadHistory: 60_000
} as const;
