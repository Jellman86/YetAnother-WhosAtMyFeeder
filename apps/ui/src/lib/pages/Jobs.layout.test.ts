import { describe, expect, it } from 'vitest';

import jobsPageSource from './Jobs.svelte?raw';

describe('jobs page stable active slots', () => {
    it('renders active jobs from stable slots instead of direct updatedAt order', () => {
        expect(jobsPageSource).toContain("from '../jobs/active-slots'");
        expect(jobsPageSource).toContain("from '../stores/backfill_status.svelte'");
        expect(jobsPageSource).toContain('activeSlotAssignments');
        expect(jobsPageSource).toContain('buildStableActiveJobSlots');
        expect(jobsPageSource).toContain('sameActiveSlotAssignments');
        expect(jobsPageSource).toContain('presentedActiveSlots');
        expect(jobsPageSource).toContain('backfillStatusStore.retain()');
        expect(jobsPageSource).toContain("{#each presentedActiveSlots as item (item.slotIndex)}");
        expect(jobsPageSource).toContain("jobs.thread_slot', { default: 'Thread {index}'");
        expect(jobsPageSource).toContain("jobs.thread_idle', { default: 'Idle' }");
        expect(jobsPageSource).not.toContain('{#each presentedActiveJobs as item (item.job.id)}');
    });
});
