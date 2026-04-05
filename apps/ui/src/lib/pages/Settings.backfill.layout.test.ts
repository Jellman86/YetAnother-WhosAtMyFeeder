import { describe, expect, it } from 'vitest';

import settingsPageSource from './Settings.svelte?raw';

describe('settings backfill progress wiring', () => {
    it('passes scoped totals into both detection and weather backfill notifications', () => {
        expect(settingsPageSource).toContain("function reconcileBackfillNotification(kind: 'detections' | 'weather', status: BackfillJobStatus | null, scopedTotal = 0)");
        expect(settingsPageSource).toContain("reconcileBackfillNotification('detections', detections, scoped.total);");
        expect(settingsPageSource).toContain("reconcileBackfillNotification('weather', weather, scoped.total);");
    });
});
