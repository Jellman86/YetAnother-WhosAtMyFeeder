import { describe, expect, it } from 'vitest';

import { REFRESH_CADENCE_MS } from './refresh-cadence';

describe('background refresh cadence', () => {
    it('reads far less often while the live stream announces changes than while it polls for them', () => {
        expect(REFRESH_CADENCE_MS.liveSafetyRead).toBeGreaterThanOrEqual(5 * REFRESH_CADENCE_MS.dashboardDay);
        expect(REFRESH_CADENCE_MS.liveSafetyRead).toBeGreaterThanOrEqual(5 * REFRESH_CADENCE_MS.recentAudio);
    });

    it('reads the Health chart no more than once a minute', () => {
        expect(REFRESH_CADENCE_MS.systemLoadHistory).toBeGreaterThanOrEqual(60_000);
    });
});
