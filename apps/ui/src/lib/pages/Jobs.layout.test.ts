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

    it('uses exact configured concurrency for active slots', () => {
        expect(jobsPageSource).not.toContain('Math.max(3, configured, activeJobs.length)');
        expect(jobsPageSource).toContain('return Math.max(1, effective, configured);');
    });

    it('sorts recent jobs by newest terminal event and renders job icons', () => {
        expect(jobsPageSource).toContain('let recentJobs = $derived.by(() =>');
        expect(jobsPageSource).toContain('const finishedDiff = rightFinishedAt - leftFinishedAt;');
        expect(jobsPageSource).toContain('{#each recentJobs as job (job.id)}');
        expect(jobsPageSource).toContain('presentJobKindIcon(job.kind)');
    });

    it('keeps lane count exact and surfaces active overflow separately', () => {
        expect(jobsPageSource).toContain('let visibleActiveJobs = $derived.by(() => activeJobs.slice(0, activeSlotCount));');
        expect(jobsPageSource).toContain('let hiddenActiveJobCount = $derived(Math.max(0, activeJobs.length - visibleActiveJobs.length));');
        expect(jobsPageSource).toContain("jobs.active_overflow', { values: { count: hiddenActiveJobCount }");
    });
});
